import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from saas.db import get_db
from saas.encryption import encrypt_token
from saas.platform_bot.states import RegisterStates, AddBotStates

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
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="💳 Подписка")],
    ],
    resize_keyboard=True
)


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
        "Введи токен своего бота от @BotFather.\n\n"
        "Выглядит так: `1234567890:AABBcc...`\n\n"
        "Токен будет зашифрован и надёжно сохранён.",
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
        "Для подключения платной подписки обратись к администратору."
    )


# ─── Вспомогательная функция ─────────────────────────────────────────────────
def _get_copywriter(telegram_user_id: int):
    db = get_db()
    result = db.table("copywriters").select("*").eq("telegram_user_id", telegram_user_id).execute()
    return result.data[0] if result.data else None
