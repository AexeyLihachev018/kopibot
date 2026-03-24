"""
Роутер для клиентских ботов (те, кого видят клиенты копирайтера).
Каждый бот получает одинаковые команды, но с данными своего копирайтера.
"""
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from saas.db import get_db

CLIENT_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✍️ Написать текст")],
        [KeyboardButton(text="📋 История текстов")],
    ],
    resize_keyboard=True
)


class ClientStates(StatesGroup):
    waiting_topic = State()


def create_client_router(bot_record: dict) -> Router:
    """
    Создаёт роутер для конкретного бота.
    bot_record — строка из таблицы bots.
    """
    router = Router()
    bot_id = bot_record["id"]
    copywriter_id = bot_record["copywriter_id"]
    welcome_msg = bot_record.get("welcome_message", "Привет! Я помогу создать отличный контент.")

    # ─── /start ───────────────────────────────────────────────────────────────
    @router.message(CommandStart())
    async def client_start(message: Message):
        db = get_db()
        tg_id = message.from_user.id

        # Регистрируем клиента если ещё нет
        existing = db.table("clients").select("id").eq("bot_id", bot_id).eq("telegram_user_id", tg_id).execute()
        if not existing.data:
            db.table("clients").insert({
                "bot_id": bot_id,
                "copywriter_id": copywriter_id,
                "telegram_user_id": tg_id,
                "telegram_username": message.from_user.username,
                "first_name": message.from_user.first_name,
            }).execute()

        await message.answer(welcome_msg, reply_markup=CLIENT_KB)

    # ─── Написать текст ───────────────────────────────────────────────────────
    @router.message(F.text == "✍️ Написать текст")
    @router.message(Command("написать"))
    async def client_write(message: Message, state: FSMContext):
        await message.answer("О чём написать текст? Введи тему:")
        await state.set_state(ClientStates.waiting_topic)

    # ─── Ввод темы → генерация ────────────────────────────────────────────────
    @router.message(ClientStates.waiting_topic)
    async def client_generate(message: Message, state: FSMContext):
        db = get_db()
        tg_id = message.from_user.id
        topic = message.text.strip()

        await state.clear()
        await message.answer("⏳ Генерирую текст...")

        # Получаем клиента
        client = db.table("clients").select("id").eq("bot_id", bot_id).eq("telegram_user_id", tg_id).execute()
        if not client.data:
            await message.answer("Ошибка: клиент не найден. Напиши /start")
            return
        client_id = client.data[0]["id"]

        # Проверяем лимит копирайтера
        cw = db.table("copywriters").select("plan, generations_used").eq("id", copywriter_id).execute().data[0]
        limits = {"free": 10, "basic": 100, "pro": 99999}
        if cw["generations_used"] >= limits.get(cw["plan"], 10):
            await message.answer(
                "😔 К сожалению, лимит генераций на этот месяц исчерпан.\n"
                "Попробуй позже."
            )
            return

        # Создаём заказ
        order = db.table("orders").insert({
            "client_id": client_id,
            "bot_id": bot_id,
            "copywriter_id": copywriter_id,
            "topic": topic,
            "status": "pending",
        }).execute().data[0]
        order_id = order["id"]

        # Генерируем текст
        try:
            text = await _generate_text(topic, bot_record)
            db.table("orders").update({
                "generated_text": text,
                "status": "done",
            }).eq("id", order_id).execute()
            db.table("copywriters").update({
                "generations_used": cw["generations_used"] + 1
            }).eq("id", copywriter_id).execute()
            await message.answer(text)
        except Exception as e:
            db.table("orders").update({"status": "failed"}).eq("id", order_id).execute()
            await message.answer(f"❌ Ошибка при генерации: {e}")

    # ─── История текстов ──────────────────────────────────────────────────────
    @router.message(F.text == "📋 История текстов")
    @router.message(Command("история"))
    async def client_history(message: Message):
        db = get_db()
        tg_id = message.from_user.id

        client = db.table("clients").select("id").eq("bot_id", bot_id).eq("telegram_user_id", tg_id).execute()
        if not client.data:
            await message.answer("История пуста. Напиши /start чтобы начать.")
            return

        orders = db.table("orders")\
            .select("topic, status, created_at")\
            .eq("client_id", client.data[0]["id"])\
            .eq("status", "done")\
            .order("created_at", desc=True)\
            .limit(10)\
            .execute()

        if not orders.data:
            await message.answer("История пуста. Нажми «✍️ Написать текст» чтобы создать первый текст.")
            return

        lines = []
        for i, o in enumerate(orders.data, 1):
            date = o["created_at"][:10]
            lines.append(f"{i}. [{date}] {o['topic'][:50]}")

        await message.answer("📋 Последние 10 текстов:\n\n" + "\n".join(lines))

    return router


async def _generate_text(topic: str, bot_record: dict) -> str:
    """Генерирует текст через OpenRouter с учётом стиля копирайтера."""
    import os
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )

    style_guide = bot_record.get("style_guide") or {}
    style_note = ""
    if style_guide:
        tone = style_guide.get("tone", "")
        style_note = f"\nСтиль: {tone}" if tone else ""

    response = await client.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        messages=[
            {
                "role": "system",
                "content": f"Ты профессиональный копирайтер. Пиши качественные тексты для соцсетей.{style_note}"
            },
            {
                "role": "user",
                "content": f"Напиши пост на тему: {topic}"
            }
        ],
        max_tokens=800,
    )
    return response.choices[0].message.content
