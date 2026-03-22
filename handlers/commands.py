from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from orchestrator import Orchestrator

router = Router()
orc = Orchestrator()

# Главная клавиатура с кнопками
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✍️ Написать пост"), KeyboardButton(text="📋 Контент-план")],
        [KeyboardButton(text="🎨 Мой стиль"),    KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="❓ Помощь")],
    ],
    resize_keyboard=True,
    persistent=True,
)


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я КопиБОТ — твой AI-копирайтер для Telegram.\n\n"
        "Я умею:\n"
        "✍️ Писать посты в твоём стиле\n"
        "📋 Создавать контент-планы\n"
        "✂️ Редактировать тексты\n\n"
        "Для начала загрузи примеры своих постов через «Мой стиль», и я "
        "научусь писать как ты.",
        reply_markup=MAIN_KEYBOARD,
    )


@router.message(Command("помощь", "help"))
async def cmd_help(message: Message):
    await message.answer(
        "*Что я умею:*\n\n"
        "✍️ *Написать пост* — укажи тему, напишу в твоём стиле\n"
        "📋 *Контент-план* — создам или покажу план постов\n"
        "🎨 *Мой стиль* — загрузи архив канала (.md или .json)\n"
        "✂️ Редактура — вставь текст и скажи: *короче / живее / хлестче*\n"
        "⭐ Оценка — *оцени: [текст]* — критика по шкале 1-10\n\n"
        "*Команды:*\n"
        "/план — текущий контент-план\n"
        "/следующий — следующий пост по плану\n"
        "/стиль — стилевой профиль\n"
        "/start — главное меню",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


@router.message(Command("план"))
async def cmd_plan(message: Message):
    msg = await message.answer("Загружаю план...")
    result = await orc.handle_message("покажи план")
    await msg.edit_text(result, parse_mode="Markdown")


@router.message(Command("следующий"))
async def cmd_next(message: Message):
    msg = await message.answer("Ищу следующий пост...")
    result = await orc.handle_message("следующий пост по плану")
    await msg.edit_text(result, parse_mode="Markdown")


@router.message(Command("стиль"))
async def cmd_style(message: Message):
    msg = await message.answer("Загружаю стилевой профиль...")
    result = await orc.handle_message("покажи стиль")
    await msg.edit_text(result, parse_mode="Markdown")
