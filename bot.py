import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands
from config import TELEGRAM_BOT_TOKEN
from handlers import commands, messages, files, callbacks

logging.basicConfig(level=logging.INFO)

BOT_COMMANDS = [
    BotCommand(command="napisat", description="✍️ Написать пост"),
    BotCommand(command="plan", description="📋 Контент-план"),
    BotCommand(command="style", description="🎨 Мой стиль"),
    BotCommand(command="settings", description="⚙️ Настройки"),
    BotCommand(command="help", description="❓ Помощь"),
    BotCommand(command="start", description="🏠 Главное меню"),
]


async def main():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(files.router)
    dp.include_router(messages.router)

    # Register commands → shows Menu button in Telegram
    await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
