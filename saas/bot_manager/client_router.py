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
        [KeyboardButton(text="🔥 Тренды"), KeyboardButton(text="🏠 Старт")],
    ],
    resize_keyboard=True
)


class ClientStates(StatesGroup):
    waiting_topic = State()
    waiting_plan_niche = State()
    waiting_trend_niche = State()
    waiting_trend_topic = State()
    waiting_trend_multi = State()
    waiting_audience_query = State()
    waiting_apify_trend = State()


class OrderCallback(CallbackData, prefix="order"):
    item_idx: int


class ImageCallback(CallbackData, prefix="img"):
    order_id: str


class TrendTypeCallback(CallbackData, prefix="ttype"):
    search_type: str  # "niche", "topic", "audience"


class WriteFromTrendCallback(CallbackData, prefix="wtren"):
    idx: int  # 0, 1, 2


def create_client_router(bot_record: dict) -> Router:
    """
    Создаёт роутер для конкретного бота.
    bot_record — строка из таблицы bots.
    """
    router = Router()
    bot_id = bot_record["id"]
    copywriter_id = bot_record["copywriter_id"]
    welcome_msg = bot_record.get("welcome_message") or (
        "👋 Привет! Я — бот-копирайтер. Пишу готовые тексты для соцсетей за 10-15 секунд.\n\n"
        "Как это работает:\n"
        "1️⃣ Нажми *«✍️ Написать текст»*\n"
        "2️⃣ Опиши тему одним предложением\n"
        "3️⃣ Получи готовый пост + картинку\n\n"
        "Это бесплатно. Тексты сохраняются в *«📋 История текстов»*.\n\n"
        "Хочешь узнать все возможности? Загляни в *«🛍 Каталог услуг»*."
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
    @router.message(Command("write"))
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
        await message.answer("⏳ Генерирую текст... обычно 10-15 секунд")

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
            await message.answer(
                "💾 Текст сохранён в истории.\n"
                "Хочешь картинку к нему — нажми 🖼 Картинка.\n"
                "Или напиши новую тему.",
                reply_markup=CLIENT_KB,
            )
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
        for idx, item in enumerate(catalog):
            lines.append(
                f"• *{item['title']}*\n"
                f"  {item.get('description', '')}\n"
                f"  💰 {item.get('price', '')}\n"
            )
            buttons.append([InlineKeyboardButton(
                text=f"📝 Заказать: {item['title'][:30]}",
                callback_data=OrderCallback(item_idx=idx).pack()
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
            topic = o['topic'][:50].replace("*", "").replace("_", "").replace("`", "")
            lines.append(f"{i}. [{date}] {topic}")

        await message.answer("📋 *Последние 10 текстов:*\n\n" + "\n".join(lines), parse_mode="Markdown")

    # ─── Заказать услугу из каталога ─────────────────────────────────────────
    @router.callback_query(OrderCallback.filter())
    async def order_item(callback: CallbackQuery, callback_data: OrderCallback, state: FSMContext):
        await callback.answer()
        db = get_db()
        bot_data = db.table("bots").select("catalog").eq("id", bot_id).execute()
        catalog = bot_data.data[0].get("catalog") or [] if bot_data.data else []
        if callback_data.item_idx >= len(catalog):
            await callback.message.answer("❌ Услуга не найдена.")
            return
        item_title = catalog[callback_data.item_idx]["title"]
        await state.update_data(prefilled_topic=item_title)
        await state.set_state(ClientStates.waiting_topic)
        await callback.message.answer(
            f"✅ Услуга выбрана: *{item_title}*\n\n"
            "Уточни детали или просто отправь любое сообщение чтобы начать:",
            parse_mode="Markdown"
        )

    # ─── Тренды ───────────────────────────────────────────────────────────────
    @router.message(F.text == "🔥 Тренды")
    async def client_trends(message: Message, state: FSMContext):
        await state.clear()
        trend_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Поиск по нише", callback_data=TrendTypeCallback(search_type="niche").pack())],
            [InlineKeyboardButton(text="🔍 Поиск по теме", callback_data=TrendTypeCallback(search_type="topic").pack())],
            [InlineKeyboardButton(text="👥 Анализ аудитории", callback_data=TrendTypeCallback(search_type="audience").pack())],
        ])
        await message.answer(
            "🔥 *Поиск трендов*\n\n"
            "Выбери тип поиска:",
            parse_mode="Markdown",
            reply_markup=trend_kb,
        )

    @router.callback_query(TrendTypeCallback.filter())
    async def trend_type_selected(callback: CallbackQuery, callback_data: TrendTypeCallback, state: FSMContext):
        await callback.answer()
        if callback_data.search_type == "niche":
            await callback.message.answer(
                "🎯 *Поиск по нише*\n\n"
                "Введи нишу для поиска трендов.\n\n"
                "Например: «Фитнес», «Онлайн-образование», «Ремонт квартир»:",
                parse_mode="Markdown",
            )
            await state.set_state(ClientStates.waiting_trend_niche)
        elif callback_data.search_type == "topic":
            await callback.message.answer(
                "🔍 *Поиск по теме*\n\n"
                "Введи конкретную тему для поиска трендов.\n\n"
                "Например: «ChatGPT», «маркетплейсы», «пассивный доход»:",
                parse_mode="Markdown",
            )
            await state.set_state(ClientStates.waiting_trend_topic)
        elif callback_data.search_type == "multi":
            await callback.message.answer(
                "🌐 *Мульти-платформный поиск трендов*\n\n"
                "Введи тему — я проверю Google Trends, Reddit и соцсети одновременно и выберу 3 самые горячие идеи.\n\n"
                "Например: «искусственный интеллект», «фитнес», «маркетплейсы»:",
                parse_mode="Markdown",
            )
            await state.set_state(ClientStates.waiting_trend_multi)
        elif callback_data.search_type == "apify":
            await callback.message.answer(
                "📊 *Apify Google Trends*\n\n"
                "Введи тему — я получу реальные данные о популярности запросов через Apify Google Trends актор "
                "и предложу 3 горячие темы для постов.\n\n"
                "Например: «гидравлика», «фитнес», «ремонт квартир»:",
                parse_mode="Markdown",
            )
            await state.set_state(ClientStates.waiting_apify_trend)
        else:
            await callback.message.answer(
                "👥 *Анализ аудитории*\n\n"
                "Введи хэштег или нишу для анализа аудитории в Instagram.\n\n"
                "Например: «фитнес», «ремонт», «косметика» (без #):",
                parse_mode="Markdown",
            )
            await state.set_state(ClientStates.waiting_audience_query)

    @router.message(ClientStates.waiting_trend_niche)
    async def client_trend_niche_input(message: Message, state: FSMContext):
        query = message.text.strip() if message.text else ""
        if not query or query.startswith("/"):
            await state.clear()
            await message.answer("Введи нишу текстом.", reply_markup=CLIENT_KB)
            return
        await state.clear()
        status_msg = await message.answer(f"🔍 Ищу тренды в нише «{query}»...")
        try:
            topics = await _search_trends(query, search_type="niche")
            await _send_trend_results(message, status_msg, topics, state)
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка поиска трендов: {e}")

    @router.message(ClientStates.waiting_trend_topic)
    async def client_trend_topic_input(message: Message, state: FSMContext):
        query = message.text.strip() if message.text else ""
        if not query or query.startswith("/"):
            await state.clear()
            await message.answer("Введи тему текстом.", reply_markup=CLIENT_KB)
            return
        await state.clear()
        status_msg = await message.answer(f"🔍 Ищу тренды по теме «{query}»...")
        try:
            topics = await _search_trends(query, search_type="topic")
            await _send_trend_results(message, status_msg, topics, state)
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка поиска трендов: {e}")

    @router.message(ClientStates.waiting_trend_multi)
    async def client_trend_multi_input(message: Message, state: FSMContext):
        query = message.text.strip() if message.text else ""
        if not query or query.startswith("/"):
            await state.clear()
            await message.answer("Введи тему текстом.", reply_markup=CLIENT_KB)
            return
        await state.clear()
        status_msg = await message.answer(
            f"🌐 Анализирую тренды по «{query}» через Google Trends + Reddit + AI...\n"
            "_Это займёт 15-20 секунд_",
            parse_mode="Markdown",
        )
        try:
            topics = await _search_trends_multi_platform(query)
            await _send_trend_results(message, status_msg, topics, state)
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка мульти-поиска трендов: {e}")

    @router.message(ClientStates.waiting_apify_trend)
    async def client_apify_trend_input(message: Message, state: FSMContext):
        query = message.text.strip() if message.text else ""
        if not query or query.startswith("/"):
            await state.clear()
            await message.answer("Введи тему текстом.", reply_markup=CLIENT_KB)
            return
        await state.clear()
        status_msg = await message.answer(
            f"📊 Анализирую тренды по «{query}» через Apify Google Trends...\n"
            "_Это займёт 20-30 секунд_",
            parse_mode="Markdown",
        )
        try:
            topics = await _search_trends_apify(query)
            await _send_trend_results(message, status_msg, topics, state)
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка Apify трендов: {e}")

    @router.callback_query(WriteFromTrendCallback.filter())
    async def write_from_trend(callback: CallbackQuery, callback_data: WriteFromTrendCallback, state: FSMContext):
        await callback.answer()
        data = await state.get_data()
        trend_topics = data.get("trend_topics", [])
        if not trend_topics or callback_data.idx >= len(trend_topics):
            await callback.message.answer("❌ Темы не найдены. Попробуй поиск заново.", reply_markup=CLIENT_KB)
            return
        topic = trend_topics[callback_data.idx]
        await state.clear()
        await callback.message.answer(f"⏳ Пишу пост на тему:\n«{topic}»...")

        db = get_db()
        tg_id = callback.from_user.id
        client = db.table("clients").select("id").eq("bot_id", bot_id).eq("telegram_user_id", tg_id).execute()
        if not client.data:
            await callback.message.answer("Ошибка: клиент не найден. Напиши /start")
            return
        client_id = client.data[0]["id"]

        cw = db.table("copywriters").select("plan, generations_used").eq("id", copywriter_id).execute().data[0]
        limits = {"free": 10, "basic": 100, "pro": 99999}
        if cw["generations_used"] >= limits.get(cw["plan"], 10):
            await callback.message.answer("😔 Лимит генераций исчерпан. Попробуй позже.")
            return

        order = db.table("orders").insert({
            "client_id": client_id,
            "bot_id": bot_id,
            "copywriter_id": copywriter_id,
            "topic": topic,
            "status": "pending",
        }).execute().data[0]
        order_id = order["id"]

        try:
            text = await _generate_text(topic, bot_record)
            db.table("orders").update({"generated_text": text, "status": "done"}).eq("id", order_id).execute()
            db.table("copywriters").update({"generations_used": cw["generations_used"] + 1}).eq("id", copywriter_id).execute()
            img_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🖼 Картинка", callback_data=ImageCallback(order_id=str(order_id)).pack())
            ]])
            await callback.message.answer(text, reply_markup=img_kb)
            await callback.message.answer("✅ Готово! Выбери следующее действие:", reply_markup=CLIENT_KB)
        except Exception as e:
            db.table("orders").update({"status": "failed"}).eq("id", order_id).execute()
            await callback.message.answer(f"❌ Ошибка генерации: {e}", reply_markup=CLIENT_KB)

    # ─── Анализ аудитории через Apify ────────────────────────────────────────
    @router.message(ClientStates.waiting_audience_query)
    async def client_audience_input(message: Message, state: FSMContext):
        query = message.text.strip() if message.text else ""
        if not query or query.startswith("/"):
            await state.clear()
            await message.answer("Введи хэштег или нишу текстом.", reply_markup=CLIENT_KB)
            return
        await state.clear()
        status_msg = await message.answer(f"👥 Анализирую аудиторию по «{query}»... ~30 сек")
        try:
            topics = await _analyze_audience(query)
            await _send_trend_results(message, status_msg, topics, state)
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка анализа аудитории: {e}")

    # ─── Генерация картинки по посту ─────────────────────────────────────────
    @router.callback_query(ImageCallback.filter())
    async def generate_image(callback: CallbackQuery, callback_data: ImageCallback):
        import os
        from aiogram.types import BufferedInputFile
        await callback.answer()
        db = get_db()
        order_row = db.table("orders").select("topic").eq("id", callback_data.order_id).execute()
        if not order_row.data:
            await callback.message.answer("❌ Заказ не найден.")
            return

        topic = order_row.data[0]["topic"]
        wait_hint = "~10–20 сек" if os.getenv("OPENROUTER_API_KEY") else "~1–3 мин (бесплатный сервер)"
        status_msg = await callback.message.answer(f"🖼 Генерирую картинку... {wait_hint}")
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
    """Генерирует изображение: Gemini 2.5 Flash Image через OpenRouter или Stable Horde (бесплатно)."""
    import os
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if api_key:
        return await _generate_with_openrouter(topic, api_key)
    return await _generate_with_horde(topic)


async def _generate_with_openrouter(topic: str, api_key: str) -> bytes:
    """Gemini 2.5 Flash Image (NanoBanana Flash) через OpenRouter — ~$0.039/img, 16:9."""
    import base64
    import httpx

    prompt = (
        f"Professional social media post illustration for the topic: {topic[:200]}. "
        "Vibrant colors, cinematic composition. "
        "IMPORTANT: absolutely no text, no letters, no words, no labels, no captions, no watermarks anywhere in the image. "
        "Pure visual illustration only."
    )
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemini-2.5-flash-image",
                "messages": [{"role": "user", "content": prompt}],
                "modalities": ["image", "text"],
                "image_config": {"aspect_ratio": "16:9"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        # Изображение может быть в images[] или в content[]
        images = message.get("images", [])
        if not images:
            content = message.get("content", [])
            if isinstance(content, list):
                images = [i for i in content if isinstance(i, dict) and i.get("type") == "image_url"]
        if not images:
            raise RuntimeError("Изображение не получено от OpenRouter")
        img_url = images[0]["image_url"]["url"]
        if img_url.startswith("data:"):
            _, b64 = img_url.split(",", 1)
            return base64.b64decode(b64)
        img_resp = await client.get(img_url)
        return img_resp.content


async def _generate_with_horde(topic: str) -> bytes:
    """Stable Horde — бесплатно, любая SD-модель (1–3 мин)."""
    import asyncio
    import base64
    import httpx

    prompt = (
        f"Professional social media post illustration: {topic[:200]}. "
        "High quality, vibrant colors, cinematic composition, no text, no watermarks."
    )
    headers = {"apikey": "0000000000", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://stablehorde.net/api/v2/generate/async",
            headers=headers,
            json={
                "prompt": prompt,
                "params": {
                    "width": 512,
                    "height": 512,
                    "steps": 15,
                    "cfg_scale": 7,
                    "sampler_name": "k_euler",
                    "karras": True,
                    "n": 1,
                },
                "r2": False,
                "nsfw": False,
                "slow_workers": True,
                "censor_nsfw": True,
            },
        )
        resp.raise_for_status()
        gen_id = resp.json()["id"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(72):  # до 6 минут
            await asyncio.sleep(5)
            check = await client.get(
                f"https://stablehorde.net/api/v2/generate/check/{gen_id}",
                headers=headers,
            )
            data = check.json()
            if data.get("faulted"):
                raise RuntimeError("Ошибка на сервере генерации, попробуй ещё раз")
            if data.get("done"):
                status = await client.get(
                    f"https://stablehorde.net/api/v2/generate/status/{gen_id}",
                    headers=headers,
                )
                generations = status.json().get("generations", [])
                if not generations:
                    raise RuntimeError("Изображение не получено")
                return base64.b64decode(generations[0]["img"])

    raise RuntimeError("Превышено время ожидания. Попробуй ещё раз.")


async def _send_trend_results(message: Message, status_msg, topics: list, state: FSMContext):
    """Отправляет результаты поиска трендов с кнопками написания постов."""
    await state.update_data(trend_topics=topics)
    await status_msg.delete()
    lines = ["🔥 *Топ-3 трендовых темы:*\n"]
    for i, t in enumerate(topics, 1):
        lines.append(f"{i}. {t}")
    buttons = [[
        InlineKeyboardButton(
            text=f"✍️ Написать пост {i + 1}",
            callback_data=WriteFromTrendCallback(idx=i).pack(),
        )
    ] for i in range(len(topics))]
    trend_result_kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=trend_result_kb)
    await message.answer("✅ Выбери тему и нажми кнопку чтобы написать пост:", reply_markup=CLIENT_KB)


async def _search_trends(query: str, search_type: str) -> list:
    """Поиск трендовых тем через Perplexity (TrendScout) via OpenRouter."""
    import os
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )

    disambiguation_note = (
        "КРИТИЧЕСКИ ВАЖНО: понимай запрос буквально и строго оставайся в указанной нише.\n"
        "НЕ переключайся на омонимы, смежные отрасли или случайные ассоциации.\n"
        "Примеры правильного понимания:\n"
        "  • «гидростанции» / «гидравлика» = промышленная и мобильная гидравлика "
        "(гидроцилиндры, гидромоторы, гидравлические агрегаты для спецтехники и оборудования) "
        "— НЕ ГЭС, НЕ водоснабжение, НЕ вода.\n"
        "  • «насосы» = промышленные насосы — НЕ медицина.\n"
        "  • «турбины» = промышленные турбины — НЕ авиация, если не сказано явно.\n"
        "Если ниша технически специализированная — ищи аудиторию внутри этой специализации "
        "(инженеры, операторы, закупщики, владельцы техники), а не массовый рынок.\n"
    )

    if search_type == "niche":
        prompt = (
            f"Ниша для поиска трендов: «{query}».\n\n"
            f"{disambiguation_note}\n"
            "Найди 3 самых актуальных и трендовых темы для постов в соцсетях именно в этой нише.\n"
            "Темы должны быть конкретными, цепляющими и актуальными прямо сейчас.\n"
            "Верни ровно 3 темы, каждую с новой строки, без нумерации и без пояснений. Только темы."
        )
    else:
        prompt = (
            f"Тема для поиска трендов: «{query}».\n\n"
            f"{disambiguation_note}\n"
            "Найди 3 актуальных угла подачи для постов в соцсетях строго по этой теме.\n"
            "Каждый угол — конкретная, цепляющая тема поста.\n"
            "Верни ровно 3 темы, каждую с новой строки, без нумерации и без пояснений. Только темы."
        )

    response = await client.chat.completions.create(
        model="perplexity/sonar",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты эксперт по трендам в B2B и промышленных нишах в социальных сетях. "
                    "Отвечай только на русском языке. "
                    "Строго держись заданной ниши — не делай вольных интерпретаций запроса."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=400,
    )
    raw = response.choices[0].message.content.strip()
    topics = [line.strip("•-– ").strip() for line in raw.splitlines() if line.strip()]
    return topics[:3]


async def _search_trends_multi_platform(query: str) -> list:
    """Мульти-платформный поиск трендов: Google Trends + Reddit + Perplexity.

    Реализует скилл social-media-trends-research:
    - pytrends: реальный интерес и растущие запросы из Google Trends
    - Reddit JSON API: горячие посты без авторизации
    - Perplexity: кросс-платформенный AI-анализ (Twitter/X, TikTok, YouTube)
    """
    import asyncio
    import os
    import httpx
    from openai import AsyncOpenAI

    google_topics: list[str] = []
    reddit_topics: list[str] = []

    # ── 1. Google Trends (pytrends — синхронная, запускаем в executor) ──────────
    def _get_google_trends() -> list[str]:
        try:
            from pytrends.request import TrendReq
            pt = TrendReq(hl="ru-RU", tz=180, timeout=(10, 25))
            # Ограничиваем keyword до 100 символов (лимит API)
            kw = query[:100]
            pt.build_payload([kw], timeframe="now 7-d", geo="RU")
            related = pt.related_queries()
            rising = related.get(kw, {}).get("rising")
            if rising is not None and not rising.empty:
                return rising["query"].head(5).tolist()
            top = related.get(kw, {}).get("top")
            if top is not None and not top.empty:
                return top["query"].head(3).tolist()
        except Exception:
            pass
        return []

    loop = asyncio.get_event_loop()
    google_topics = await loop.run_in_executor(None, _get_google_trends)

    # ── 2. Reddit JSON API (без авторизации, rate limit: 60 req/час) ───────────
    async with httpx.AsyncClient(
        timeout=15.0,
        headers={"User-Agent": "KopiBot/1.0 (content research bot)"},
        follow_redirects=True,
    ) as http:
        try:
            resp = await http.get(
                "https://www.reddit.com/search.json",
                params={"q": query, "sort": "hot", "limit": 8, "t": "week"},
            )
            if resp.status_code == 200:
                posts = resp.json().get("data", {}).get("children", [])
                for post in posts[:5]:
                    title = post.get("data", {}).get("title", "").strip()
                    if title:
                        reddit_topics.append(title)
        except Exception:
            pass

    # ── 3. Perplexity — Twitter/X, TikTok, YouTube, LinkedIn ──────────────────
    perplexity_topics = await _search_trends(query, search_type="topic")

    # ── Агрегация и синтез ─────────────────────────────────────────────────────
    all_raw = google_topics + reddit_topics + perplexity_topics
    if not all_raw:
        return perplexity_topics

    # Убираем дубли, оставляем до 15 строк
    seen: set[str] = set()
    unique_raw = []
    for t in all_raw:
        key = t.lower()[:60]
        if key not in seen:
            seen.add(key)
            unique_raw.append(t)
    unique_raw = unique_raw[:15]

    # Просим модель выбрать 3 лучших и переформулировать по-русски
    topics_block = "\n".join(f"- {t}" for t in unique_raw)
    synthesis_prompt = (
        f"Ниша / тема запроса: «{query}»\n\n"
        "КРИТИЧЕСКИ ВАЖНО: оставайся строго в этой нише. Не делай вольных интерпретаций.\n"
        "Примеры: «гидростанции»/«гидравлика» = промышленная гидравлика для спецтехники и оборудования "
        "(НЕ ГЭС, НЕ вода). Держись буквального смысла запроса.\n\n"
        f"Данные из Google Trends, Reddit и соцсетей:\n{topics_block}\n\n"
        "Из приведённых данных выбери и переформулируй 3 самые сильные и актуальные темы "
        "для поста строго в указанной нише. "
        "Каждую тему сформулируй по-русски одним предложением (цепляющий заголовок). "
        "Верни ровно 3 строки, без нумерации и без пояснений."
    )

    oai = AsyncOpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )
    response = await oai.chat.completions.create(
        model="perplexity/sonar",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты эксперт по трендам в B2B и промышленных нишах. "
                    "Отвечай только на русском языке. "
                    "Строго держись заданной ниши — не делай вольных интерпретаций запроса."
                ),
            },
            {"role": "user", "content": synthesis_prompt},
        ],
        max_tokens=400,
    )
    raw = response.choices[0].message.content.strip()
    final = [line.strip("•-–1234567890. ").strip() for line in raw.splitlines() if line.strip()]
    return final[:3] if final else perplexity_topics[:3]


async def _search_trends_apify(query: str) -> list:
    """Поиск трендов через Apify Google Trends актор."""
    import os
    import asyncio
    import httpx
    from openai import AsyncOpenAI

    apify_token = os.getenv("APIFY_API_TOKEN", "")
    if not apify_token:
        # Fallback на Perplexity если токен не настроен
        return await _search_trends(query, search_type="topic")

    actor_id = "emastra~google-trends-scraper"
    trending_keywords: list[str] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            run_resp = await client.post(
                f"https://api.apify.com/v2/acts/{actor_id}/runs?token={apify_token}",
                json={
                    "searchTerms": [query],
                    "geo": "RU",
                    "timeRange": "now 7-d",
                    "resultsCount": 10,
                },
            )
            run_resp.raise_for_status()
            run_id = run_resp.json()["data"]["id"]

            for _ in range(15):
                await asyncio.sleep(4)
                status_resp = await client.get(
                    f"https://api.apify.com/v2/actor-runs/{run_id}?token={apify_token}"
                )
                status = status_resp.json()["data"]["status"]
                if status == "SUCCEEDED":
                    break
                if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                    break

            dataset_id = status_resp.json()["data"]["defaultDatasetId"]
            items_resp = await client.get(
                f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={apify_token}&limit=20"
            )
            items = items_resp.json() if items_resp.status_code == 200 else []

            for item in items:
                # Google Trends scraper возвращает relatedQueries или title
                if item.get("query"):
                    trending_keywords.append(item["query"])
                elif item.get("title"):
                    trending_keywords.append(item["title"])
                for rq in item.get("relatedQueries", [])[:3]:
                    if isinstance(rq, dict):
                        trending_keywords.append(rq.get("query", ""))
                    elif isinstance(rq, str):
                        trending_keywords.append(rq)
        except Exception:
            pass

    # Если Apify не дал данных — fallback на Perplexity
    if not trending_keywords:
        return await _search_trends(query, search_type="topic")

    trending_keywords = [k for k in trending_keywords if k][:15]
    keywords_block = "\n".join(f"- {k}" for k in trending_keywords)

    oai = AsyncOpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )
    response = await oai.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты эксперт по контент-маркетингу. "
                    "На основе реальных данных Google Trends предлагай конкретные темы для постов. "
                    "Строго держись указанной ниши. Отвечай только на русском языке."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Ниша: «{query}»\n\n"
                    f"Реальные трендовые запросы из Google Trends (Россия, последние 7 дней):\n{keywords_block}\n\n"
                    f"На основе этих данных сформулируй 3 конкретные цепляющие темы для постов в Instagram строго по нише «{query}». "
                    "Верни ровно 3 темы, каждую с новой строки, без нумерации и без пояснений."
                ),
            },
        ],
        max_tokens=300,
    )
    raw = response.choices[0].message.content.strip()
    topics = [line.strip("•-– ").strip() for line in raw.splitlines() if line.strip()]
    return topics[:3]


async def _analyze_audience(query: str) -> list:
    """Анализ аудитории Instagram через Apify + генерация тем через OpenRouter."""
    import os
    import httpx
    from openai import AsyncOpenAI

    apify_token = os.getenv("APIFY_API_TOKEN", "")
    if not apify_token:
        raise RuntimeError("APIFY_API_TOKEN не настроен")

    # Запускаем Apify актор для Instagram hashtag скрапинга
    actor_id = "apify~instagram-hashtag-scraper"
    hashtag = query.strip("#").replace(" ", "").lower()

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Запускаем актор
        run_resp = await client.post(
            f"https://api.apify.com/v2/acts/{actor_id}/runs?token={apify_token}",
            json={
                "hashtags": [hashtag],
                "resultsLimit": 20,
            },
        )
        run_resp.raise_for_status()
        run_id = run_resp.json()["data"]["id"]

        # Ждём завершения (до 60 сек)
        import asyncio
        for _ in range(12):
            await asyncio.sleep(5)
            status_resp = await client.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}?token={apify_token}"
            )
            status = status_resp.json()["data"]["status"]
            if status == "SUCCEEDED":
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Apify завершился со статусом: {status}")

        # Получаем результаты
        dataset_id = status_resp.json()["data"]["defaultDatasetId"]
        items_resp = await client.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={apify_token}&limit=20"
        )
        items = items_resp.json()

    # Собираем популярные хэштеги и темы из постов
    hashtags_found = []
    captions = []
    for item in items:
        if item.get("caption"):
            captions.append(item["caption"][:200])
        for tag in item.get("hashtags", [])[:5]:
            hashtags_found.append(tag)

    top_tags = ", ".join(list(dict.fromkeys(hashtags_found))[:15])
    sample_captions = "\n".join(captions[:5])

    # Передаём в OpenRouter для анализа и генерации тем
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    ai_client = AsyncOpenAI(
        api_key=openrouter_key,
        base_url="https://openrouter.ai/api/v1",
    )
    response = await ai_client.chat.completions.create(
        model="anthropic/claude-haiku-4-5",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты эксперт по контент-маркетингу для B2B и промышленных ниш. "
                    "Твоя задача — предлагать темы постов строго в рамках указанной ниши, не расширяя её и не смешивая с похожими темами. "
                    "Если ниша — гидравлическое оборудование, пиши только про гидроцилиндры, гидростанции, гидравлические системы, мобильную и промышленную гидравлику. "
                    "Отвечай только на русском языке."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Ниша: «{query}».\n\n"
                    + (f"Популярные хэштеги в этой нише: {top_tags}\n\n" if top_tags else "")
                    + (f"Примеры популярных постов:\n{sample_captions}\n\n" if sample_captions else "")
                    + f"Придумай 3 конкретные цепляющие темы для постов в Instagram строго по теме «{query}». "
                    "Темы должны быть практичными, полезными для целевой аудитории этой ниши и вызывать желание прочитать пост. "
                    "Верни ровно 3 темы, каждую с новой строки, без нумерации и без пояснений. Только сами темы."
                ),
            },
        ],
        max_tokens=300,
    )
    raw = response.choices[0].message.content.strip()
    topics = [line.strip("•-– ").strip() for line in raw.splitlines() if line.strip()]
    return topics[:3]


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
