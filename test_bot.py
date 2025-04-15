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


dotenv.load_dotenv()

db = Database()
bot_settings = db.execute('SELECT * FROM administration_bot WHERE name="@"')
api_token = db.execute('SELECT * FROM settings_bot')
print(
    f'api_token: {api_token}\n'
    f'assistant_id: {bot_settings[0][3]}\n'
    f'bot_settings: {bot_settings[0][4]}\n'
)
bot = Bot(token=bot_settings[0][4], default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()
try:
    client = openai.OpenAI(api_key=api_token[0][1])
except Exception as e:
    print(f"Ошибка: {e}")
ASSISTANT_ID = bot_settings[0][3]

if not ASSISTANT_ID:
    raise ValueError("Ошибка: переменная окружения RU_ASSISTANT не загружена!")

user_threads = {}

class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_company = State()

async def delete_webhook(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)

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

@dp.callback_query(lambda c: c.data.startswith(('approve_', 'reject_')))
async def process_moderation(callback: types.CallbackQuery):
    action, user_id = callback.data.split('_')
    user_id = int(user_id)
    
    if action == 'approve':
        db.execute('UPDATE user_request SET status = "approved" WHERE user_id = ?', (user_id,))
        await callback.message.edit_text(f"✅ Заявка пользователя {user_id} одобрена.")
        
        try:
            await bot.send_message(user_id, "Ваша заявка одобрена! Теперь вы можете пользоваться ботом.")
        except Exception as e:
            print(f"Error notifying user {user_id}: {e}")
            
    elif action == 'reject':
        db.execute('UPDATE user_request SET status = "rejected" WHERE user_id = ?', (user_id,))
        await callback.message.edit_text(f"❌ Заявка пользователя {user_id} отклонена.")
        
        try:
            await bot.send_message(user_id, "К сожалению, ваша заявка была отклонена.")
        except Exception as e:
            print(f"Error notifying user {user_id}: {e}")
    
    await callback.answer()

@dp.message(F.content_type.in_({'voice', 'audio', 'document'}))
async def handle_voice_files(message: Message):
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
        
        if message.voice:
            file_id = message.voice.file_id
        elif message.audio:
            file_id = message.audio.file_id
        elif message.document:
            file_id = message.document.file_id
        else:
            await message.reply("Неподдерживаемый тип файла.")
            return
        
        file = await bot.get_file(file_id)
        file_path = file.file_path
        downloaded_file = await bot.download_file(file_path)
        
        temp_file = f"temp_{file_id}"
        with open(temp_file, 'wb') as f:
            f.write(downloaded_file.read())
        
        with open(temp_file, 'rb') as f:
            uploaded_file = client.files.create(file=f, purpose='assistants')
        
        os.remove(temp_file)
        
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content="",
            file_ids=[uploaded_file.id]
        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID,
            instructions=bot_settings[0][4]
        )

        timeout = time.time() + 70 
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
        print(f"Ошибка: {e}")
        await message.reply("Произошла ошибка при обработке файла.")

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

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID,
            instructions=bot_settings[0][4]
        )

        timeout = time.time() + 70 
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
        print(f"Ошибка: {e}")
        await message.reply("Произошла ошибка при обработке запроса.")

async def main():
    await delete_webhook(bot)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())