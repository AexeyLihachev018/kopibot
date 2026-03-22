from __future__ import annotations
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from orchestrator import Orchestrator

router = Router()
orc = Orchestrator()

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


# ─── Menu button commands (дублируют кнопки клавиатуры) ──────────────────────

@router.message(Command("napisat"))
async def cmd_napisat(message: Message, state: FSMContext):
    """Написать пост — через меню бота."""
    from handlers.messages import btn_write_post
    await btn_write_post(message, state)


@router.message(Command("plan"))
async def cmd_plan_menu(message: Message, state: FSMContext):
    """Контент-план — через меню бота."""
    from handlers.messages import btn_content_plan
    await btn_content_plan(message, state)


@router.message(Command("style"))
async def cmd_style_menu(message: Message, state: FSMContext):
    """Мой стиль — через меню бота."""
    from handlers.messages import btn_my_style
    await btn_my_style(message, state)


@router.message(Command("settings"))
async def cmd_settings_menu(message: Message, state: FSMContext):
    """Настройки — через меню бота."""
    from handlers.messages import btn_settings
    await btn_settings(message, state)


@router.message(Command("help", "помощь"))
async def cmd_help(message: Message, state: FSMContext):
    """Помощь — через меню бота."""
    from handlers.messages import btn_help
    await btn_help(message, state)


# ─── Прочие команды ───────────────────────────────────────────────────────────

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
