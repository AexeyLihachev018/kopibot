import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from config import TELEGRAM_BOT_TOKEN
from handlers import commands, messages, files, callbacks

logging.basicConfig(level=logging.INFO)


async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(files.router)
    dp.include_router(messages.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
