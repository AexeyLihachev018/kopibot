"""
Bot Manager — управляет всеми клиентскими ботами одновременно.
Один процесс, N ботов, каждый в своей asyncio-задаче.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from saas.db import get_db
from saas.encryption import decrypt_token
from saas.bot_manager.client_router import create_client_router

logger = logging.getLogger(__name__)

# Хранилище активных ботов: {bot_id: {"bot": Bot, "dp": Dispatcher, "task": Task}}
_active_bots: dict = {}


async def load_all_bots():
    """Загружает и запускает все активные боты из БД при старте платформы."""
    db = get_db()
    bots = db.table("bots").select("*").eq("is_active", True).execute()

    if not bots.data:
        logger.info("Активных ботов не найдено")
        return

    logger.info(f"Загружаю {len(bots.data)} ботов...")
    for bot_record in bots.data:
        try:
            await _start_bot(bot_record)
            logger.info(f"Бот @{bot_record['bot_username']} запущен")
        except Exception as e:
            logger.error(f"Не удалось запустить бот {bot_record['bot_username']}: {e}")


async def start_bot_by_id(bot_id: str):
    """Запускает один бот по его ID (вызывается когда копирайтер добавляет бот)."""
    db = get_db()
    result = db.table("bots").select("*").eq("id", bot_id).execute()
    if not result.data:
        raise ValueError(f"Бот {bot_id} не найден")

    bot_record = result.data[0]
    await _start_bot(bot_record)

    # Помечаем бот как активный в БД
    db.table("bots").update({"is_active": True}).eq("id", bot_id).execute()
    logger.info(f"Бот @{bot_record['bot_username']} активирован")


async def stop_bot_by_id(bot_id: str):
    """Останавливает бот по его ID."""
    if bot_id not in _active_bots:
        return

    entry = _active_bots.pop(bot_id)
    entry["task"].cancel()
    try:
        await entry["task"]
    except asyncio.CancelledError:
        pass
    await entry["bot"].session.close()

    db = get_db()
    db.table("bots").update({"is_active": False}).eq("id", bot_id).execute()
    logger.info(f"Бот {bot_id} остановлен")


async def _start_bot(bot_record: dict):
    """Внутренняя функция запуска одного бота."""
    bot_id = bot_record["id"]

    if bot_id in _active_bots:
        logger.warning(f"Бот {bot_id} уже запущен")
        return

    token = decrypt_token(bot_record["bot_token_encrypted"])
    bot = Bot(token=token)
    dp = Dispatcher(storage=MemoryStorage())

    # Подключаем роутер с обработчиками для клиентов
    dp.include_router(create_client_router(bot_record))

    # Запускаем polling в отдельной задаче
    task = asyncio.create_task(
        dp.start_polling(bot, handle_signals=False),
        name=f"bot_{bot_record['bot_username']}"
    )

    _active_bots[bot_id] = {"bot": bot, "dp": dp, "task": task}


def get_active_bots() -> list:
    """Возвращает список ID активных ботов."""
    return list(_active_bots.keys())
