import asyncio
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)
from aiogram.filters import Command, CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext

from saas.db import get_db
from saas.encryption import encrypt_token
from saas.platform_bot.states import RegisterStates, AddBotStates, CatalogStates

router = Router()

# ─── Лимиты по тарифам ───────────────────────────────────────────────────────
PLAN_LIMITS = {
    "free":  {"generations": 10,  "bots": 1,  "clients": 5},
    "basic": {"generations": 100, "bots": 5,  "clients": 50},
    "pro":   {"generations": 99999, "bots": 99, "clients": 99999},
}

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🤖 Мои боты"), KeyboardButton(text="➕ Добавить бота")],
        [KeyboardButton(text="📋 Мой каталог"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="💳 Подписка"), KeyboardButton(text="🏠 Старт")],
    ],
    resize_keyboard=True
)

CATALOG_KB = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить услугу")],
        [KeyboardButton(text="Очистить каталог")],
        [KeyboardButton(text="Назад в меню")],
    ],
    resize_keyboard=True
)


class DeleteServiceCallback(CallbackData, prefix="del_svc"):
    bot_id: str
    item_idx: int


async def _show_catalog_for_bot(message: Message, bot_id: str):
    """Показывает каталог конкретного бота с inline-кнопками удаления."""
    db = get_db()
    bot_row = db.table("bots").select("bot_username, catalog").eq("id", bot_id).execute()
    if not bot_row.data:
        await message.answer("Бот не найден.", reply_markup=MAIN_KB)
        return

    bot_rec = bot_row.data[0]
    catalog = bot_rec.get("catalog") or []

    if not catalog:
        await message.answer(
            f"Каталог бота @{bot_rec['bot_username']} пока пуст.\n\n"
            "Нажми «Добавить услугу» чтобы добавить первую.",
            reply_markup=CATALOG_KB,
        )
        return

    lines = [f"🛍 Каталог бота @{bot_rec['bot_username']}:\n"]
    inline_buttons = []
    for idx, item in enumerate(catalog):
        lines.append(
            f"{idx + 1}. *{item['title']}* — {item.get('price', '?')}\n"
            + (f"   {item['description']}\n" if item.get('description') else "")
        )
        inline_buttons.append([
            InlineKeyboardButton(
                text=f"❌ Удалить: {item['title'][:25]}",
                callback_data=DeleteServiceCallback(bot_id=bot_id, item_idx=idx).pack(),
            )
        ])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    lines.append("\nНажми кнопку ниже чтобы удалить услугу, или используй меню.")
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=CATALOG_KB)
    await message.answer("Управление услугами:", reply_markup=inline_kb)


# ─── /start ──────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    db = get_db()
    tg_id = message.from_user.id

    # Проверяем, зарегистрирован ли уже
    result = db.table("copywriters").select("id, display_name").eq("telegram_user_id", tg_id).execute()

    if result.data:
        name = result.data[0]["display_name"]
        await message.answer(
            f"👋 С возвращением, {name}!\n\n"
            "Используй меню для управления своими ботами.",
            reply_markup=MAIN_KB
        )
    else:
        await message.answer(
            "👋 Добро пожаловать в КопиБот Платформу!\n\n"
            "Здесь ты можешь подключить своего Telegram-бота и "
            "автоматически генерировать тексты для своих клиентов.\n\n"
            "Как тебя зовут? Введи своё имя:"
        )
        await state.set_state(RegisterStates.waiting_name)


# ─── Регистрация: ввод имени ──────────────────────────────────────────────────
@router.message(RegisterStates.waiting_name)
async def process_name(message: Message, state: FSMContext):
    db = get_db()
    name = message.text.strip()

    if len(name) < 2:
        await message.answer("Имя слишком короткое. Введи ещё раз:")
        return

    tg_id = message.from_user.id

    # Создаём запись копирайтера (без auth.users — просто по telegram_user_id)
    db.table("copywriters").insert({
        "telegram_user_id": tg_id,
        "display_name": name,
        "plan": "free",
    }).execute()

    await state.clear()
    await message.answer(
        f"✅ Отлично, {name}! Ты зарегистрирован на платформе.\n\n"
        f"🎁 Тариф: Free (10 генераций/месяц, 1 бот, до 5 клиентов)\n\n"
        "Нажми «➕ Добавить бота» чтобы подключить своего Telegram-бота.",
        reply_markup=MAIN_KB
    )


# ─── Мои боты ────────────────────────────────────────────────────────────────
@router.message(F.text == "🤖 Мои боты")
async def my_bots(message: Message):
    db = get_db()
    tg_id = message.from_user.id

    cw = _get_copywriter(tg_id)
    if not cw:
        await message.answer("Сначала зарегистрируйся — нажми /start")
        return

    bots = db.table("bots").select("bot_username, bot_name, is_active").eq("copywriter_id", cw["id"]).execute()

    if not bots.data:
        await message.answer("У тебя пока нет ботов. Нажми «➕ Добавить бота»")
        return

    lines = []
    for b in bots.data:
        status = "✅ активен" if b["is_active"] else "⏸ не активен"
        lines.append(f"• @{b['bot_username']} ({b['bot_name']}) — {status}")

    await message.answer("🤖 Твои боты:\n\n" + "\n".join(lines))


# ─── Добавить бота ────────────────────────────────────────────────────────────
@router.message(F.text == "➕ Добавить бота")
async def add_bot_start(message: Message, state: FSMContext):
    db = get_db()
    tg_id = message.from_user.id
    cw = _get_copywriter(tg_id)

    if not cw:
        await message.answer("Сначала зарегистрируйся — нажми /start")
        return

    # Проверяем лимит по тарифу
    limit = PLAN_LIMITS[cw["plan"]]["bots"]
    existing = db.table("bots").select("id", count="exact").eq("copywriter_id", cw["id"]).execute()
    if existing.count >= limit:
        await message.answer(
            f"❌ По тарифу {cw['plan'].upper()} можно подключить не более {limit} бота.\n"
            "Обнови подписку для добавления большего числа ботов."
        )
        return

    await message.answer(
        "📌 *Как получить токен:*\n\n"
        "1. Открой Telegram и найди @BotFather\n"
        "2. Напиши ему `/newbot`\n"
        "3. Придумай имя и username для бота\n"
        "4. BotFather пришлёт токен — строку вида:\n"
        "   `1234567890:AABBccDDee...`\n\n"
        "Скопируй этот токен и отправь сюда.\n"
        "Он будет зашифрован и надёжно сохранён.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(AddBotStates.waiting_token)


# ─── Добавить бота: ввод токена ───────────────────────────────────────────────
@router.message(AddBotStates.waiting_token)
async def process_bot_token(message: Message, state: FSMContext):
    token = message.text.strip()

    # Базовая проверка формата токена
    if ":" not in token or len(token) < 30:
        await message.answer("❌ Это не похоже на токен бота. Скопируй его точно из @BotFather:")
        return

    # Проверяем токен через Telegram API
    await message.answer("⏳ Проверяю токен...")
    try:
        test_bot = Bot(token=token)
        bot_info = await test_bot.get_me()
        await test_bot.session.close()
    except Exception:
        await message.answer(
            "❌ Токен недействителен. Убедись, что скопировал его правильно из @BotFather."
        )
        return

    # Сохраняем данные во временное хранилище FSM
    await state.update_data(
        token=token,
        bot_username=bot_info.username,
        bot_name=bot_info.full_name
    )

    await message.answer(
        f"✅ Бот @{bot_info.username} ({bot_info.full_name}) найден!\n\n"
        "Введи приветственное сообщение, которое клиенты увидят при /start:\n"
        "(или напиши «стандартное» чтобы использовать текст по умолчанию)"
    )
    await state.set_state(AddBotStates.waiting_welcome)


# ─── Добавить бота: ввод приветствия ─────────────────────────────────────────
@router.message(AddBotStates.waiting_welcome)
async def process_welcome(message: Message, state: FSMContext):
    db = get_db()
    tg_id = message.from_user.id
    cw = _get_copywriter(tg_id)
    data = await state.get_data()

    welcome = (
        "Привет! Я помогу создать отличный контент. Напишите /написать чтобы начать."
        if message.text.strip().lower() == "стандартное"
        else message.text.strip()
    )

    # Сохраняем бот в БД
    encrypted = encrypt_token(data["token"])
    result = db.table("bots").insert({
        "copywriter_id": cw["id"],
        "bot_token_encrypted": encrypted,
        "bot_username": data["bot_username"],
        "bot_name": data["bot_name"],
        "welcome_message": welcome,
        "is_active": False,
    }).execute()

    bot_id = result.data[0]["id"]
    await state.clear()

    # Активируем бота сразу
    await message.answer("⏳ Запускаю бота...", reply_markup=MAIN_KB)

    # Импортируем manager здесь чтобы избежать циклических импортов
    from saas.bot_manager.manager import start_bot_by_id
    try:
        await start_bot_by_id(bot_id)
        await message.answer(
            f"🚀 Бот @{data['bot_username']} успешно запущен!\n\n"
            "Клиенты уже могут писать в него.",
            reply_markup=MAIN_KB
        )
    except Exception as e:
        await message.answer(
            f"⚠️ Бот добавлен, но не удалось запустить: {e}\n"
            "Попробуй снова через «🤖 Мои боты»",
            reply_markup=MAIN_KB
        )


# ─── Статистика ───────────────────────────────────────────────────────────────
@router.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    db = get_db()
    tg_id = message.from_user.id
    cw = _get_copywriter(tg_id)

    if not cw:
        await message.answer("Сначала зарегистрируйся — нажми /start")
        return

    clients_count = db.table("clients").select("id", count="exact").eq("copywriter_id", cw["id"]).execute()
    orders_count = db.table("orders").select("id", count="exact").eq("copywriter_id", cw["id"]).eq("status", "done").execute()
    limit = PLAN_LIMITS[cw["plan"]]["generations"]
    used = cw.get("generations_used", 0)

    await message.answer(
        f"📊 Твоя статистика:\n\n"
        f"📋 Тариф: {cw['plan'].upper()}\n"
        f"⚡ Генераций: {used} / {limit if limit < 9999 else '∞'}\n"
        f"👥 Клиентов: {clients_count.count}\n"
        f"✅ Текстов создано: {orders_count.count}"
    )


# ─── Подписка ─────────────────────────────────────────────────────────────────
@router.message(F.text == "💳 Подписка")
async def show_subscription(message: Message):
    await message.answer(
        "💳 Тарифные планы:\n\n"
        "🆓 Free — 0 ₽/мес\n"
        "   • 10 генераций, 1 бот, до 5 клиентов\n\n"
        "⚡ Basic — 990 ₽/мес\n"
        "   • 100 генераций, 5 ботов, до 50 клиентов\n\n"
        "🚀 Pro — 2 990 ₽/мес\n"
        "   • Безлимит генераций, ботов и клиентов\n\n"
        "👉 Для подключения платного тарифа напиши администратору:\n"
        "@Alexey_Li_copy"
    )


# ─── Каталог услуг ───────────────────────────────────────────────────────────
@router.message(F.text.contains("каталог") | F.text.contains("Каталог"))
async def show_catalog(message: Message, state: FSMContext):
    import logging
    logger = logging.getLogger(__name__)
    try:
        db = get_db()
        tg_id = message.from_user.id
        cw = _get_copywriter(tg_id)

        if not cw:
            await message.answer("Сначала зарегистрируйся — нажми /start")
            return

        bots_row = db.table("bots").select("id, bot_username").eq("copywriter_id", cw["id"]).execute()
        if not bots_row.data:
            await message.answer("У тебя пока нет бота. Нажми «Добавить бота»", reply_markup=MAIN_KB)
            return

        if len(bots_row.data) == 1:
            # Один бот — сразу показываем каталог
            bot_id = bots_row.data[0]["id"]
            await state.update_data(catalog_bot_id=bot_id)
            await _show_catalog_for_bot(message, bot_id)
        else:
            # Несколько ботов — предлагаем выбор
            await state.set_state(CatalogStates.waiting_bot_choice)
            bot_buttons = [[KeyboardButton(text=f"@{b['bot_username']}")] for b in bots_row.data]
            bot_buttons.append([KeyboardButton(text="Назад в меню")])
            choose_kb = ReplyKeyboardMarkup(keyboard=bot_buttons, resize_keyboard=True)
            await message.answer("У тебя несколько ботов. Выбери, каталог какого редактировать:", reply_markup=choose_kb)
    except Exception as e:
        logger.error(f"Ошибка в show_catalog: {e}", exc_info=True)
        await message.answer(f"Ошибка: {e}", reply_markup=MAIN_KB)


@router.message(CatalogStates.waiting_bot_choice)
async def catalog_choose_bot(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "Назад в меню":
        await state.clear()
        await message.answer("Главное меню:", reply_markup=MAIN_KB)
        return

    # Ищем бот по username (текст вида "@username")
    username = text.lstrip("@")
    db = get_db()
    tg_id = message.from_user.id
    cw = _get_copywriter(tg_id)
    bot_row = db.table("bots").select("id").eq("copywriter_id", cw["id"]).eq("bot_username", username).execute()
    if not bot_row.data:
        await message.answer("Бот не найден. Выбери из кнопок выше.")
        return

    bot_id = bot_row.data[0]["id"]
    await state.set_state(None)
    await state.update_data(catalog_bot_id=bot_id)
    await _show_catalog_for_bot(message, bot_id)


@router.message(F.text == "Добавить услугу")
async def catalog_add_start(message: Message, state: FSMContext):
    await message.answer(
        "Введи название услуги:\n(например: SEO-статья, Пост для Instagram)",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CatalogStates.waiting_title)


@router.message(CatalogStates.waiting_title)
async def catalog_add_title(message: Message, state: FSMContext):
    await state.update_data(catalog_title=message.text.strip())
    await message.answer("Введи краткое описание услуги (или «-» если не нужно):")
    await state.set_state(CatalogStates.waiting_description)


@router.message(CatalogStates.waiting_description)
async def catalog_add_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    await state.update_data(catalog_description="" if desc == "-" else desc)
    await message.answer("Введи цену услуги (например: «2000 ₽» или «от 500 ₽»):")
    await state.set_state(CatalogStates.waiting_price)


@router.message(CatalogStates.waiting_price)
async def catalog_add_price(message: Message, state: FSMContext):
    db = get_db()
    tg_id = message.from_user.id
    cw = _get_copywriter(tg_id)
    data = await state.get_data()
    await state.clear()

    bot_id = data.get("catalog_bot_id")
    if not bot_id:
        # Если потерялся ID бота — берём первый
        bot_row = db.table("bots").select("id, catalog").eq("copywriter_id", cw["id"]).limit(1).execute()
        if not bot_row.data:
            await message.answer("Бот не найден.", reply_markup=MAIN_KB)
            return
        bot_id = bot_row.data[0]["id"]
        catalog = bot_row.data[0].get("catalog") or []
    else:
        bot_row = db.table("bots").select("catalog").eq("id", bot_id).execute()
        catalog = bot_row.data[0].get("catalog") or [] if bot_row.data else []

    new_item = {
        "id": len(catalog) + 1,
        "title": data["catalog_title"],
        "description": data.get("catalog_description", ""),
        "price": message.text.strip(),
    }
    catalog.append(new_item)

    db.table("bots").update({"catalog": catalog}).eq("id", bot_id).execute()

    await message.answer(f"✅ Услуга «{new_item['title']}» добавлена!")

    # Показываем обновлённый каталог сразу
    await state.update_data(catalog_bot_id=bot_id)
    await _show_catalog_for_bot(message, bot_id)


@router.message(F.text == "Очистить каталог")
async def catalog_clear(message: Message, state: FSMContext):
    db = get_db()
    data = await state.get_data()
    bot_id = data.get("catalog_bot_id")
    if bot_id:
        db.table("bots").update({"catalog": []}).eq("id", bot_id).execute()
        await message.answer("Каталог очищен.", reply_markup=MAIN_KB)
    else:
        await message.answer("Бот не найден. Попробуй заново через Мой каталог.", reply_markup=MAIN_KB)
    await state.clear()


@router.message(F.text == "Назад в меню")
async def catalog_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=MAIN_KB)


@router.callback_query(DeleteServiceCallback.filter())
async def catalog_delete_item(callback: CallbackQuery, callback_data: DeleteServiceCallback, state: FSMContext):
    await callback.answer()
    db = get_db()
    bot_id = callback_data.bot_id
    item_idx = callback_data.item_idx

    bot_row = db.table("bots").select("catalog").eq("id", bot_id).execute()
    if not bot_row.data:
        await callback.message.answer("Бот не найден.", reply_markup=MAIN_KB)
        return

    catalog = bot_row.data[0].get("catalog") or []
    if item_idx < 0 or item_idx >= len(catalog):
        await callback.message.answer("Услуга уже удалена или не найдена.")
        return

    removed = catalog.pop(item_idx)
    db.table("bots").update({"catalog": catalog}).eq("id", bot_id).execute()

    await callback.message.edit_text(f"✅ Услуга «{removed['title']}» удалена.")
    await state.update_data(catalog_bot_id=bot_id)
    await _show_catalog_for_bot(callback.message, bot_id)


@router.message(F.text == "🏠 Старт")
async def btn_start(message: Message, state: FSMContext):
    await state.clear()
    name = message.from_user.first_name or "друг"
    cw = _get_copywriter(message.from_user.id)
    if cw:
        name = cw.get("display_name") or name
    await message.answer(f"👋 Привет, {name}!\nГлавное меню:", reply_markup=MAIN_KB)


# ─── Fallback: любое неизвестное сообщение ───────────────────────────────────
@router.message()
async def fallback_handler(message: Message, state: FSMContext):
    """Если пользователь потерял меню — возвращаем его."""
    tg_id = message.from_user.id
    cw = _get_copywriter(tg_id)
    if cw:
        await message.answer("Используй кнопки меню:", reply_markup=MAIN_KB)
    else:
        await message.answer("Напиши /start чтобы начать.")


# ─── Вспомогательная функция ─────────────────────────────────────────────────
def _get_copywriter(telegram_user_id: int):
    db = get_db()
    result = db.table("copywriters").select("*").eq("telegram_user_id", telegram_user_id).execute()
    return result.data[0] if result.data else None
