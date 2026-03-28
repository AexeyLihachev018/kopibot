"""
Роутер для клиентских ботов (те, кого видят клиенты копирайтера).
Каждый бот получает одинаковые команды, но с данными своего копирайтера.
"""
from aiogram import Router, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters.callback_data import CallbackData

from saas.db import get_db

CLIENT_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✍️ Написать текст"), KeyboardButton(text="📅 Контент-план")],
        [KeyboardButton(text="🛍 Каталог услуг"), KeyboardButton(text="📋 История текстов")],
        [KeyboardButton(text="🏠 Старт")],
    ],
    resize_keyboard=True
)


class ClientStates(StatesGroup):
    waiting_topic = State()
    waiting_plan_niche = State()


class OrderCallback(CallbackData, prefix="order"):
    item_title: str


class ImageCallback(CallbackData, prefix="img"):
    order_id: str


def create_client_router(bot_record: dict) -> Router:
    """
    Создаёт роутер для конкретного бота.
    bot_record — строка из таблицы bots.
    """
    router = Router()
    bot_id = bot_record["id"]
    copywriter_id = bot_record["copywriter_id"]
    welcome_msg = bot_record.get("welcome_message") or (
        "👋 Привет! Я помогу быстро создать профессиональный текст.\n\n"
        "Нажми *«✍️ Написать текст»* — опиши тему, и через несколько секунд "
        "получишь готовый пост для соцсетей, рассылки или сайта.\n\n"
        "Хочешь узнать что умею? Загляни в *«🛍 Каталог услуг»*."
    )

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

    # ─── Старт (сброс меню) ───────────────────────────────────────────────────
    @router.message(F.text == "🏠 Старт")
    async def client_home(message: Message, state: FSMContext):
        await state.clear()
        await message.answer(welcome_msg, reply_markup=CLIENT_KB)

    # ─── Написать текст ───────────────────────────────────────────────────────
    @router.message(F.text == "✍️ Написать текст")
    @router.message(Command("написать"))
    async def client_write(message: Message, state: FSMContext):
        await message.answer(
            "✍️ *Напиши тему — получишь готовый пост!*\n\n"
            "Например:\n"
            "• «5 причин начать бегать по утрам»\n"
            "• «Обзор новинок осень-зима 2025»\n"
            "• «Как мы помогли клиенту сэкономить 30%»\n\n"
            "Чем конкретнее тема — тем лучше текст:",
            parse_mode="Markdown"
        )
        await state.set_state(ClientStates.waiting_topic)

    # ─── Ввод темы → генерация ────────────────────────────────────────────────
    @router.message(ClientStates.waiting_topic)
    async def client_generate(message: Message, state: FSMContext):
        db = get_db()
        tg_id = message.from_user.id
        topic = message.text.strip() if message.text else ""
        data = await state.get_data()
        prefilled = data.get("prefilled_topic", "")

        # Если пользователь нажал команду вместо темы — сбрасываем
        if not topic or topic.startswith("/"):
            if prefilled:
                topic = prefilled  # используем выбранную услугу как тему
            else:
                await state.clear()
                await message.answer(
                    "Похоже, ты нажал команду вместо темы.\n"
                    "Нажми «✍️ Написать текст» и введи тему текстом.",
                    reply_markup=CLIENT_KB
                )
                return
        elif prefilled:
            topic = f"{prefilled}: {topic}"

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
            img_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🖼 Картинка",
                    callback_data=ImageCallback(order_id=str(order_id)).pack(),
                )
            ]])
            await message.answer(text, reply_markup=img_kb)
        except Exception as e:
            db.table("orders").update({"status": "failed"}).eq("id", order_id).execute()
            await message.answer(f"❌ Ошибка при генерации: {e}", reply_markup=CLIENT_KB)

    # ─── Каталог услуг ────────────────────────────────────────────────────────
    @router.message(F.text == "🛍 Каталог услуг")
    @router.message(Command("каталог"))
    async def client_catalog(message: Message):
        db = get_db()
        # Загружаем актуальный каталог из БД по bot_id этого бота
        bot_data = db.table("bots").select("catalog, bot_name").eq("id", bot_id).execute()
        if not bot_data.data:
            await message.answer("Каталог недоступен.")
            return

        catalog = bot_data.data[0].get("catalog") or []
        bot_name = bot_data.data[0].get("bot_name", "")

        if not catalog:
            await message.answer("📋 Каталог услуг пока пуст.\nНапиши «✍️ Написать текст» чтобы сделать заказ.")
            return

        lines = [f"🛍 *Каталог услуг {bot_name}:*\n"]
        buttons = []
        for item in catalog:
            lines.append(
                f"• *{item['title']}*\n"
                f"  {item.get('description', '')}\n"
                f"  💰 {item.get('price', '')}\n"
            )
            buttons.append([InlineKeyboardButton(
                text=f"📝 Заказать: {item['title'][:30]}",
                callback_data=OrderCallback(item_title=item["title"]).pack()
            )])

        inline_kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=inline_kb)

    # ─── Контент-план ─────────────────────────────────────────────────────────
    @router.message(F.text == "📅 Контент-план")
    @router.message(Command("plan"))
    async def client_plan_start(message: Message, state: FSMContext):
        await message.answer(
            "📅 *Контент-план на неделю*\n\n"
            "Напиши нишу или тему своего блога/бизнеса.\n\n"
            "Например:\n"
            "• «Фитнес и здоровое питание»\n"
            "• «Продажа детской одежды»\n"
            "• «Личный бренд коуча»",
            parse_mode="Markdown"
        )
        await state.set_state(ClientStates.waiting_plan_niche)

    @router.message(ClientStates.waiting_plan_niche)
    async def client_plan_generate(message: Message, state: FSMContext):
        niche = message.text.strip() if message.text else ""
        if not niche or niche.startswith("/"):
            await state.clear()
            await message.answer("Введи нишу текстом, например: «Фитнес».", reply_markup=CLIENT_KB)
            return

        await state.clear()
        await message.answer("⏳ Составляю контент-план на 7 дней...")

        try:
            plan = await _generate_content_plan(niche, bot_record)
            await message.answer(plan + "\n\n_Что сделать дальше?_", parse_mode="Markdown", reply_markup=CLIENT_KB)
        except Exception as e:
            await message.answer(f"❌ Ошибка при генерации: {e}", reply_markup=CLIENT_KB)

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

    # ─── Заказать услугу из каталога ─────────────────────────────────────────
    @router.callback_query(OrderCallback.filter())
    async def order_item(callback: CallbackQuery, callback_data: OrderCallback, state: FSMContext):
        await callback.answer()
        await state.update_data(prefilled_topic=callback_data.item_title)
        await state.set_state(ClientStates.waiting_topic)
        await callback.message.answer(
            f"✅ Услуга выбрана: *{callback_data.item_title}*\n\n"
            "Уточни детали или просто отправь любое сообщение чтобы начать:",
            parse_mode="Markdown"
        )

    # ─── Генерация картинки по посту ─────────────────────────────────────────
    @router.callback_query(ImageCallback.filter())
    async def generate_image(callback: CallbackQuery, callback_data: ImageCallback):
        from aiogram.types import BufferedInputFile
        await callback.answer()
        db = get_db()
        order_row = db.table("orders").select("topic").eq("id", callback_data.order_id).execute()
        if not order_row.data:
            await callback.message.answer("❌ Заказ не найден.")
            return

        topic = order_row.data[0]["topic"]
        status_msg = await callback.message.answer("⏳ Генерирую картинку (~15 сек)...")
        try:
            image_bytes = await _generate_image(topic)
            await status_msg.delete()
            await callback.message.answer_photo(
                photo=BufferedInputFile(image_bytes, filename="image.jpg"),
                caption=f"🖼 {topic[:100]}",
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ Не удалось сгенерировать картинку: {e}")

    return router


async def _generate_content_plan(niche: str, bot_record: dict) -> str:
    """Генерирует контент-план на 7 дней через OpenRouter."""
    import os
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )
    response = await client.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        messages=[
            {
                "role": "system",
                "content": "Ты эксперт по контент-маркетингу. Составляй чёткие контент-планы."
            },
            {
                "role": "user",
                "content": (
                    f"Составь контент-план на 7 дней для ниши: {niche}\n\n"
                    "Формат каждого дня:\n"
                    "📅 День N (День недели): [Тема поста]\n"
                    "Тип: [обучение/продажа/развлечение/кейс/вопрос]\n\n"
                    "В конце добавь 2-3 совета по публикации."
                )
            }
        ],
        max_tokens=1000,
    )
    return response.choices[0].message.content


async def _generate_image(topic: str) -> bytes:
    """Генерирует изображение через HuggingFace Inference API (SDXL, бесплатно)."""
    import os
    import asyncio
    import httpx

    prompt = (
        f"Professional social media post illustration: {topic[:200]}. "
        "High quality, vibrant colors, cinematic composition, no text, no watermarks."
    )
    headers = {}
    hf_token = os.getenv("HF_TOKEN", "")
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(3):
            response = await client.post(
                "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
                headers=headers,
                json={"inputs": prompt, "parameters": {"width": 1344, "height": 768}},
            )
            if response.status_code == 503:
                # Модель загружается, ждём и повторяем
                await asyncio.sleep(20)
                continue
            response.raise_for_status()
            return response.content
    raise RuntimeError("Модель недоступна, попробуй позже.")


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
