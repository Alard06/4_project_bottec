import asyncio
import os
import openai
import dotenv
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db import Database
from datetime import datetime
import subprocess
from pathlib import Path

dotenv.load_dotenv()

db = Database()
bot_settings = db.execute('SELECT * FROM administration_bot WHERE name="@Gsg_smart_bot"')
api_token = db.execute('SELECT * FROM settings_bot')

bot = Bot(token=bot_settings[0][4], default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

print(api_token)
client = openai.OpenAI(api_key=api_token[0][1])
ASSISTANT_ID = db.execute('SELECT assistant_token FROM administration_bot WHERE name="@Gsg_smart_bot"')[0][0]


print(bot_settings)
print(ASSISTANT_ID)
if not ASSISTANT_ID:
    raise ValueError("Ошибка: переменная окружения HASSP_ASSISTANT не загружена!")

user_threads = {}

class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_company = State()

async def delete_webhook(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)


async def convert_voice_to_text(file_id):
    ogg_file = f"temp_{file_id}.ogg"
    mp3_file = f"temp_{file_id}.mp3"

    file = await bot.get_file(file_id)
    downloaded_file = await bot.download_file(file.file_path)

    with open(ogg_file, 'wb') as f:
        f.write(downloaded_file.read())

    subprocess.run(['ffmpeg', '-y', '-i', ogg_file, '-acodec', 'libmp3lame', '-q:a', '2', mp3_file], check=True)

    with open(mp3_file, 'rb') as audio_file:
        transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ru")

    Path(ogg_file).unlink(missing_ok=True)
    Path(mp3_file).unlink(missing_ok=True)

    return transcript.text

async def wait_for_assistant_response(thread_id, run_id, timeout=120):
    end_time = time.time() + timeout
    while time.time() < end_time:
        run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        if run_status.status == 'completed':
            return True
        await asyncio.sleep(2)
    return False

def get_user_thread(user_id):
    if user_id not in user_threads:
        thread = client.beta.threads.create()
        user_threads[user_id] = thread.id
    return user_threads[user_id]


async def send_message_to_assistant(message, user_id, content, file=None):
    thread_id = get_user_thread(user_id)

    if file:
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content or "Пожалуйста, проанализируй этот файл",
            file_ids=file.id
        )
    else:
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )

    prompt = db.execute('SELECT prompt FROM administration_bot WHERE name="@Gsg_smart_bot"')[0][0]
    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID, instructions=prompt)

    if not await wait_for_assistant_response(thread_id, run.id):
        await message.reply("Превышено время ожидания ответа от ассистента.")
        return

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    assistant_messages = [msg for msg in messages.data if msg.role == 'assistant']
    if assistant_messages:
        #await message.reply(repr(thread_id), parse_mode='None')
        #await message.reply(repr(assistant_messages), parse_mode='None')
        await message.reply(assistant_messages[0].content[0].text.value)
    else:
        await message.reply("Ассистент не предоставил ответ.")



@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    user_request = db.execute('SELECT * FROM user_request WHERE user_id = ? AND status = "approved"', (user_id,))
    
    if user_request:
        await message.answer("Добро пожаловать обратно! Вы уже прошли проверку и можете пользоваться ботом.")
        return
    
    pending_request = db.execute('SELECT * FROM user_request WHERE user_id = ? AND status = "pending"', (user_id,))
    
    if pending_request:
        await message.answer("Ваша заявка уже находится на рассмотрении. Пожалуйста, подождите.")
        return
    
    await message.answer("Добро пожаловать! Для доступа к боту необходимо пройти регистрацию.")
    await message.answer("Пожалуйста, укажите ваше ФИО:")
    await state.set_state(RegistrationStates.waiting_for_full_name)

@dp.message(RegistrationStates.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext):
    full_name = message.text
    await state.update_data(full_name=full_name)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поделиться номером телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await message.answer("Теперь укажите ваш номер телефона:", reply_markup=keyboard)
    await state.set_state(RegistrationStates.waiting_for_phone)

@dp.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    
    await message.answer("Укажите название вашей компании и должность (можно пропустить):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegistrationStates.waiting_for_company)

@dp.message(RegistrationStates.waiting_for_phone)
async def process_phone_text(message: Message, state: FSMContext):
    await message.answer("Пожалуйста, поделитесь номером телефона с помощью кнопки ниже.")

@dp.message(RegistrationStates.waiting_for_company)
async def process_company(message: Message, state: FSMContext):
    data = await state.get_data()
    full_name = data.get('full_name')
    phone = data.get('phone')
    company_info = message.text if message.text else None
    
    company = None
    position = None
    if company_info:
        parts = company_info.split(',')
        company = parts[0].strip()
        if len(parts) > 1:
            position = parts[1].strip()
    
    db.execute(
        'INSERT INTO user_request (user_id, full_name, phone, company, position, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (message.from_user.id, full_name, phone, company, position, 'pending', datetime.now())
    )
    
    await message.answer("Спасибо! Ваша заявка отправлена на модерацию. Мы уведомим вас о результате.")
    
    await state.clear()


@dp.message(F.content_type.in_({'voice'}))
async def handle_voice(message: Message):
    user_id = message.from_user.id
    user_request = db.execute('SELECT * FROM user_request WHERE user_id = ? AND status = "approved"', (user_id,))

    if not user_request:
        await message.answer("Доступ к боту ограничен. Пожалуйста, пройдите регистрацию с помощью команды /start.")
        return

    try:
        text_content = await convert_voice_to_text(message.voice.file_id)
#        await message.reply(f"Голосовое сообщение успешно преобразовано в текст: {text_content}")
        await send_message_to_assistant(message, user_id, text_content)
    except Exception as e:
        print(f"Ошибка: {e}")
        await message.reply(f"Произошла ошибка при обработке голосового сообщения.")


@dp.message(F.content_type.in_({'document', 'photo'}))
async def handle_files(message: Message):
    user_id = message.from_user.id
    await message.reply(f'Загружен файл')
    user_request = db.execute('SELECT * FROM user_request WHERE user_id = ? AND status = "approved"', (user_id,))
    if not user_request:
        await message.answer("Доступ к боту ограничен. Пожалуйста, пройдите регистрацию с помощью команды /start.")
        return
    
    try:
        if user_id not in user_threads:
            thread = client.beta.threads.create()
            user_threads[user_id] = thread.id
        thread_id = user_threads[user_id]
        
        file_ids = []
        temp_files = []  
        
        if message.document:
            allowed_mime_types = [
                'application/pdf', 
                'text/plain',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/vnd.ms-powerpoint',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            ]
            
            if message.document.mime_type not in allowed_mime_types:
                await message.reply("Извините, этот тип документа не поддерживается. Пожалуйста, отправьте PDF, Word, Excel или текстовый файл.")
                return
                
            file = await bot.get_file(message.document.file_id)
            downloaded_file = await bot.download_file(file.file_path)
            
            temp_file = f"temp_{message.document.file_id}"
            with open(temp_file, 'wb') as f:
                f.write(downloaded_file.read())
            
            with open(temp_file, 'rb') as f:
                uploaded_file = client.files.create(file=f, purpose='assistants')
            os.remove(temp_file)
            
        elif message.photo:
            photo = message.photo[-1] 
            file = await bot.get_file(photo.file_id)
            downloaded_file = await bot.download_file(file.file_path)
            
            temp_file = f"temp_{photo.file_id}.jpg"
            with open(temp_file, 'wb') as f:
                f.write(downloaded_file.read())
            
            with open(temp_file, 'rb') as f:
                uploaded_file = client.files.create(file=f, purpose='assistants')

            os.remove(temp_file)
        await send_message_to_assistant(message, user_id, "Пожалуйста, проанализируй этот файл", uploaded_file)

    except Exception as e:
        print(f"Ошибка при обработке файла: {str(e)}")
        await message.reply(f"{e}")
        await message.reply(f"Произошла ошибка при обработке файла. Пожалуйста, попробуйте еще раз.")

@dp.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    
    user_request = db.execute('SELECT * FROM user_request WHERE user_id = ? AND status = "approved"', (user_id,))
    
    if not user_request:
        await message.answer("Доступ к боту ограничен. Пожалуйста, пройдите регистрацию с помощью команды /start.")
        return
    
    try:
        if user_id not in user_threads:
            thread = client.beta.threads.create()
            user_threads[user_id] = thread.id

        thread_id = user_threads[user_id]

        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message.text
        )
        prompt = db.execute('SELECT prompt FROM administration_bot WHERE name="@Gsg_smart_bot"')[0][0]
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID,
            instructions=prompt
        )

        timeout = time.time() + 160 
        while time.time() < timeout:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == 'completed':
                break
            await asyncio.sleep(1)
        else:
            await message.reply("Превышено время ожидания ответа от ассистента.")
            return

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        if not messages.data:
            await message.reply("Я не получил ответ от ассистента.")
            return

        assistant_messages = sorted(
            [msg for msg in messages.data if msg.role == 'assistant'],
            key=lambda msg: msg.created_at
        )

        if assistant_messages:
            await message.reply(assistant_messages[-1].content[0].text.value)
        else:
            await message.reply("Я не получил ответ от ассистента.")

    except Exception as e:
        await message.reply(f"{e}")
        await message.reply("Произошла ошибка при обработке запроса.")

async def main():
    await delete_webhook(bot)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())


