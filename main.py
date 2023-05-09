from datetime import date, timedelta, datetime
import datetime
import chardet
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import sqlite3
from config import token

# Ініціалізуємо бота та диспетчера
bot = Bot(token=token)
dp = Dispatcher(bot, storage=MemoryStorage())

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Створюємо таблицю, якщо вона ще не існує
cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY,
        telegram_id INTEGER,
        group_code TEXT
    )
""")
conn.commit()


class ReedStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_date = State()



def get_user_group(user_id):
    cursor.execute('SELECT group_code FROM students WHERE telegram_id=?', (user_id,))
    result = cursor.fetchone()
    conn.commit()
    if result:
        return result[0]
    else:
        return None


def parse(sdate, edate, group ):
    
    payload = {
    "group": group.encode("cp1251"),
    "sdate": sdate,
    "edate": edate,
}
    response = requests.post('https://dekanat.nung.edu.ua/cgi-bin/timetable.cgi?n=700', data=payload)
    encoding = chardet.detect(response.content)["encoding"] # windows-1251
    html = response.content.decode(encoding)
    soup = BeautifulSoup(html, "html.parser")
    trs = soup.find_all("tr")
    tst = [i.text for i in soup.find_all("h4")][4:]
    result = [None] * len(trs)
    ind = 0
    for tr in trs:
        tds = tr.find_all("td")
        i = 1 
        for td in tds:
            if i == 1:
                result[ind] = f"{td.text} пара \n"
            if i == 2:
                result[ind] =  result[ind] + f" {td.text[:5]}-{td.text[5:]} " 
            else:
                result[ind] = result[ind] + td.text
            i += 1
        ind += 1
    return  result if result else "Запланованики занять немає"



async def send_today(message: types.Message):
    # Відправляємо запит на сайт та отримуємо HTML код
    day = date.today().strftime("%d.%m.%Y")
    try:
        lessons_list = parse(day, day, get_user_group(message.from_user.id))
    except AttributeError:
        await message.answer("Ви ще не зареєстрованикися в боті. для реєстрації використайте функцію /group")
        return
    lsn = "\n".join(lessons_list) if type(lessons_list) == list else lessons_list
    await message.answer(f"Дата: {day}\n{lsn}")


async def send_tomorrow(message: types.Message):
    # Відправляємо запит на сайт та отримуємо HTML код
    day = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
    try:
        lessons_list = parse(day, day, get_user_group(message.from_user.id))
    except AttributeError:
        await message.answer("Ви ще не зареєстрованикися в боті. для реєстрації використайте функцію /group")
        return
    lsn = "\n".join(lessons_list) if type(lessons_list) == list else lessons_list
    await message.answer(f"Дата: {day}\n{lsn}")

async def send_week(message: types.Message):
    days = [(date.today() + timedelta(days=i)).strftime("%d.%m.%Y") for i in range(7)]
    for day in days:
        try:
            lessons_list = parse(day, day, get_user_group(message.from_user.id))
        except AttributeError:
            await message.answer("Ви ще не зареєстрованикися в боті. для реєстрації використайте функцію /group")
            return
        lsn = "\n".join(lessons_list) if type(lessons_list) == list else lessons_list
        await message.answer(f"Дата: {day}\n{lsn}")

async def reed_day(message: types.Message):
    await message.answer(f'Введіть дату в форматі: дд.мм.ррр \nприклад /day {date.today().strftime("%d.%m.%Y")}')
    await ReedStates.waiting_for_date.set()   

@dp.message_handler(state=ReedStates.waiting_for_date)
async def send_day(message: types.Message, state: FSMContext):
    try:
        date_str = message.text
        day = datetime.datetime.strptime(date_str, "%d.%m.%Y").strftime("%d.%m.%Y")
        try:
            lessons_list = parse(day, day, get_user_group(message.from_user.id))
        except AttributeError:
            await message.answer("Ви ще не зареєстрованикися в боті. для реєстрації використайте функцію /group")
            return
        lsn = "\n".join(lessons_list) if type(lessons_list) == list else lessons_list
        await message.answer(f"Дата: {day}\n{lsn}")
    except ValueError:
        await message.answer(f'Неправильний формат дати [{message.text}]. Введіть дату в форматі: дд.мм.рррр \nПриклад {date.today().strftime("%d.%m.%Y")} ')
    await state.finish()


async def reed_group(message: types.Message):
    await message.answer("Введіть Шифр групи приклад(AA-11-1):")
    await ReedStates.waiting_for_text.set()      

@dp.message_handler(state=ReedStates.waiting_for_text)
async def save_group(message: types.Message, state: FSMContext):
    # Отримуємо номер групи введений користувачем
    group_code = message.text
    if not group_code:
        await message.reply("Ви не ввели <b>Шифр групи</b>")
        await reed_group()
        return
    # Перевіряємо, чи користувач уже є в базі даних
    cursor.execute("SELECT * FROM students WHERE telegram_id=?", (message.from_user.id,))
    user = cursor.fetchone()
    if user:
        # Оновлюємо існуючого користувача з новою групою
        cursor.execute("UPDATE students SET group_code=? WHERE telegram_id=?", (group_code, message.from_user.id))
        conn.commit()
        await message.answer(f'Групу "{group_code}" змінено для користувача  {message.from_user.username}')
    else:
        # Додаємо нового користувача до бази даних
        cursor.execute("INSERT INTO students (telegram_id, group_code) VALUES (?, ?)", (message.from_user.id, group_code))
        conn.commit()
        await message.answer(f'Групу "{group_code}" збережено для користувача {message.from_user.username}')
    await state.finish()



async def help_cmd_handler(message: types.Message):
    commands=[
        types.BotCommand("today", "Розклад за сьогодні"),
        types.BotCommand("tomorrow", "Розклад за завтра"),
        types.BotCommand("week", "Розклад за тиждень"),
        types.BotCommand("group", "Група за якою буде йти пошук"),
        types.BotCommand("day", "Розклад за певний день"),
        types.BotCommand("help", "Список всіх команд"),
        
        ]
    await bot.set_my_commands(commands)
    await message.answer(f'⚙️ <b>Мої команди:</b>\n➖ /group - Група за яким будемо шукати\n➖ /tomorrow - розклад на завтра\n➖ /today - розклад на сьогодні\n➖ /week - розклад за тиждень\n➖ /day - розклад за певнима датою\n➖ /help - Список команд\n ', parse_mode="HTML")
    

async def start_handler(message: types.Message):
    await message.answer(f'Привіт, <b>{message.from_user.username}</b>!\nОрганізуй свій розклад за допомогою мене', parse_mode="HTML")
    await message.answer(f'Керуйте своїм щоденним розкладом за допомогою @schadule_bot.\n За допомогою кількох простих команд ви можете швидко отримати доступ до розкладу на <i>день, тиждень, тощо!</i>\nСпробуйте це сьогодні та будьте організовані!', parse_mode="HTML")
    await message.answer(f'⚙️ <b>Мої команди:</b>\n➖ /group - Група за яким будемо шукати\n➖ /today - розклад за сьогодні\n➖ /week - розклад за тиждень\n➖ /day - розклад за певнима датою\n➖ /help - Список команд\n ', parse_mode="HTML")
    keyboard = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton(text="group", callback_data="group")
    keyboard.add(button)
    await message.answer(f'Потрібно вказати 🔐 <b>Шифр Групи</b> (прикл. АА-11-1)\n виконавши командой /group', reply_markup=keyboard, parse_mode='HTML')


# Створюємо обробник команди /group, /today, /week, /day

dp.register_message_handler(start_handler, commands=['start'])
dp.register_message_handler(help_cmd_handler, commands=['help'])
dp.register_message_handler(reed_group, commands=['group'])
dp.register_message_handler(send_today, commands=['today'])
dp.register_message_handler(send_tomorrow, commands=['tomorrow'])
dp.register_message_handler(send_week, commands=['week'])
dp.register_message_handler(reed_day, commands=['day'])
dp.register_callback_query_handler(reed_group, text="group")

# Запускаємо Бота
if __name__ == '__main__':
    executor.start_polling(dp)