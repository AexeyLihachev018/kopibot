from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from orchestrator import Orchestrator
from tools.style_store import load_style_guide
from tools.plan_store import load_plan
from config import STYLE_GUIDE_PATH, CONTENT_PLAN_PATH

router = Router()
orc = Orchestrator()


class BotStates(StatesGroup):
    waiting_for_post_topic = State()
    waiting_for_edit_text = State()
    waiting_for_plan_params = State()


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✍️ Написать пост"), KeyboardButton(text="📋 Контент-план")],
        [KeyboardButton(text="🎨 Мой стиль"),    KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="❓ Помощь")],
    ],
    resize_keyboard=True,
    persistent=True,
)

SETTINGS_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Статус бота", callback_data="settings_status")],
    [InlineKeyboardButton(text="🗑 Сбросить стиль", callback_data="settings_reset_style")],
    [InlineKeyboardButton(text="🗑 Очистить план", callback_data="settings_reset_plan")],
    [InlineKeyboardButton(text="ℹ️ О боте", callback_data="settings_about")],
])


@router.message(F.text == "✍️ Написать пост")
async def btn_write_post(message: Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_post_topic)
    await message.answer(
        "О чём написать пост? Напиши тему — например:\n\n"
        "_«почему я перестал откладывать решения»_\n"
        "_«3 ошибки при найме первых сотрудников»_\n"
        "_«как я нашёл первых клиентов»_",
        parse_mode="Markdown",
    )


@router.message(BotStates.waiting_for_post_topic)
async def handle_post_topic(message: Message, state: FSMContext):
    await state.clear()
    topic = message.text
    msg = await message.answer(f"Пишу пост на тему «{topic}»... ✍️\n\n_Это займёт 15-30 секунд_", parse_mode="Markdown")
    try:
        style_guide = load_style_guide()
        result = await orc._generate_flow(topic, style_guide)
        await msg.edit_text(result, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"Ошибка при генерации: {e}")


@router.message(F.text == "📋 Контент-план")
async def btn_content_plan(message: Message, state: FSMContext):
    plan = load_plan()
    if plan:
        msg = await message.answer("Загружаю контент-план...")
        try:
            result = await orc.handle_message("покажи план")
            await msg.edit_text(result, parse_mode="Markdown")
        except Exception as e:
            await msg.edit_text(f"Ошибка: {e}")
    else:
        await state.set_state(BotStates.waiting_for_plan_params)
        await message.answer(
            "Контент-план пуст.\n\n"
            "Напиши тему и период — например:\n\n"
            "_«личный бренд, 2 недели»_\n"
            "_«продажи и экспертность, месяц»_",
            parse_mode="Markdown",
        )


@router.message(BotStates.waiting_for_plan_params)
async def handle_plan_params(message: Message, state: FSMContext):
    await state.clear()
    params = message.text
    msg = await message.answer(f"Создаю контент-план... ⏳", parse_mode="Markdown")
    try:
        result = await orc.handle_message(f"создай контент-план: {params}")
        await msg.edit_text(result, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")


@router.message(F.text == "🎨 Мой стиль")
async def btn_my_style(message: Message):
    sg = load_style_guide()
    if sg:
        tone = sg.get("tone", "—")
        rhythm = sg.get("sentence_rhythm", "—")
        emoji_use = sg.get("emoji_usage", "—")
        await message.answer(
            "*Стилевой профиль загружен* ✅\n\n"
            f"• Тон: {tone}\n"
            f"• Ритм предложений: {rhythm}\n"
            f"• Эмодзи: {emoji_use}\n\n"
            "Чтобы обновить — прикрепи новый файл архива (.md или .json).\n\n"
            "_Как выгрузить архив: Telegram Desktop → канал → три точки → Экспорт истории чата → только текст, формат JSON_",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "*Стилевой профиль не загружен* ❌\n\n"
            "Загрузи архив своего Telegram-канала — файл .md или .json.\n\n"
            "Я проанализирую твои посты и запомню стиль.\n\n"
            "_Как выгрузить: Telegram Desktop → канал → три точки → Экспорт истории чата → только текст, формат JSON_",
            parse_mode="Markdown",
        )


@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message):
    sg = load_style_guide()
    plan = load_plan()
    style_status = "✅ Загружен" if sg else "❌ Не загружен"
    plan_status = f"✅ {len(plan)} постов" if plan else "❌ Пуст"
    done = sum(1 for i in plan if i.get("status") == "done") if plan else 0

    await message.answer(
        f"*Настройки КопиБОТА*\n\n"
        f"🎨 Стилевой профиль: {style_status}\n"
        f"📋 Контент-план: {plan_status}"
        + (f" (выполнено {done})" if plan else "")
        + "\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=SETTINGS_KEYBOARD,
    )


@router.message(F.text == "❓ Помощь")
async def btn_help(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "*Что я умею:*\n\n"
        "✍️ *Написать пост* — нажми кнопку, напиши тему — готово\n"
        "📋 *Контент-план* — покажу план или создам новый\n"
        "🎨 *Мой стиль* — прикрепи файл архива (.md или .json)\n\n"
        "*Текстовые команды:*\n"
        "• _короче [текст]_ — сократить\n"
        "• _живее [текст]_ — сделать живее\n"
        "• _хлестче [текст]_ — сделать хлестче\n"
        "• _оцени: [текст]_ — критика 1-10\n"
        "• _создай план на месяц_ — новый контент-план\n\n"
        "*Команды:*\n"
        "/план — текущий контент-план\n"
        "/следующий — следующий пост по плану\n"
        "/стиль — стилевой профиль",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


@router.message()
async def handle_text(message: Message):
    if not message.text:
        return
    msg = await message.answer("Обрабатываю...")
    try:
        result = await orc.handle_message(message.text)
        await msg.edit_text(result, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"Ошибка: {e}")
