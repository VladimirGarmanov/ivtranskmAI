import configparser
import time
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ChatType
import openai
import httpx

# Чтение файла config.ini
config = configparser.ConfigParser()
config.read('config.ini')

# Загрузка конфигурации из файла
assistant_id = config.get('Config', 'assistant_id')
openai_api_key = config.get('Config', 'openai_api_key')
telegram_token = config.get('Config', 'telegram_token')

# Инициализация бота и диспетчера
bot = Bot(token=telegram_token)
dp = Dispatcher(bot)
client = openai.OpenAI(api_key=openai_api_key)
Assistant_ID = assistant_id

# Локальная БД пользователей для хранения thread_id
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    thread TEXT
)''')
conn.commit()

async def send_text(login: str, message: str):
    url = "https://heliosai.ru/api/send_req"
    data = {"login": login, "message": message}
    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(url, data=data)
        return response.json()

# Получить или создать thread для чата
def add_user(chat_id: int) -> str:
    cursor.execute('SELECT thread FROM users WHERE chat_id = ?', (chat_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    thread = client.beta.threads.create()
    cursor.execute('INSERT INTO users (chat_id, thread) VALUES (?, ?)', (chat_id, thread.id))
    conn.commit()
    print(f"New thread created: {thread.id} for chat {chat_id}")
    return thread.id

# Обработка сообщений в группах
@dp.message_handler(lambda message: message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP], content_types=types.ContentTypes.TEXT)
async def handle_group_message(message: types.Message):
    chat_id = message.chat.id
    thread_id = add_user(chat_id)

    # Отправляем запрос в AI
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message.text
    )
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=Assistant_ID,
    )

    # Ждем завершения
    while True:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == 'completed':
            break
        await asyncio.sleep(2)

    # Получаем ответ
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    response = messages.data[0].content[0].text.value

    # Отправляем ответ в группу
    await bot.send_message(chat_id=chat_id, text=response)

# Стартовый ответ на команду /start в группах
@dp.message_handler(commands=['start'], chat_type=[ChatType.GROUP, ChatType.SUPERGROUP])
async def start_command(message: types.Message):
    thread_id = add_user(message.chat.id)
    await message.reply("Бот активирован в этой группе. Чем могу помочь?")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
