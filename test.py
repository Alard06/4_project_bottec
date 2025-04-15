import asyncio
import os
import openai
import dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message

dotenv.load_dotenv()

bot = Bot(token=os.getenv('API_TOKEN_BOT_HASSP'), default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY") )
ASSISTANT_ID = os.getenv('HASSP_ASSISTANT')

user_threads = {}

async def delete_webhook(bot: Bot):
    await bot.delete_webhook(drop_pending_updates=True)


@dp.message()
async def handle_message(message: Message):
    try:
        thread = client.beta.threads.create()

        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message.text
        )

        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID,
            instructions="Please respond to the user's query helpfully and professionally."
        )

        while True:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

            if run_status.status == 'completed':
                break
            await asyncio.sleep(1)

        messages = client.beta.threads.messages.list(
            thread_id=thread.id
        )

        assistant_messages = [
            msg.content[0].text.value
            for msg in messages.data
            if msg.role == 'assistant'
        ]

        if assistant_messages:
            await message.reply(assistant_messages[-1])
        else:
            await message.reply("I didn't get a response from the assistant.")

    except Exception as e:
        print(f"Error: {e}")
        await message.reply("Sorry, I encountered an error processing your request.")


async def main():
    await delete_webhook(bot)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
