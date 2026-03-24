"""
run_platform.py — точка входа SaaS платформы для копирайтеров.

Запуск:  python3 run_platform.py
"""
import asyncio
import logging
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    platform_token = os.getenv("PLATFORM_BOT_TOKEN", "")
    if not platform_token:
        logger.error(
            "PLATFORM_BOT_TOKEN не задан в .env\n"
            "Создай бота через @BotFather и добавь токен в .env:\n"
            "PLATFORM_BOT_TOKEN=1234567890:AABBcc..."
        )
        return

    # Подключаем обработчики платформенного бота
    from saas.platform_bot.handlers import router as platform_router
    from saas.bot_manager.manager import load_all_bots

    platform_bot = Bot(token=platform_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(platform_router)

    # Загружаем уже существующие активные боты из БД
    logger.info("Загружаю активные боты из базы данных...")
    await load_all_bots()

    logger.info("Платформа запущена! Ожидаю сообщений...")
    await dp.start_polling(platform_bot)


if __name__ == "__main__":
    asyncio.run(main())
