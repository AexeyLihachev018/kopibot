from __future__ import annotations
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from tools.style_store import load_style_guide
from tools.plan_store import load_plan
from tools.post_cache import save_post, get_post, clear_post
from config import STYLE_GUIDE_PATH, CONTENT_PLAN_PATH
from orchestrator import Orchestrator, _extract_result
import json

router = Router()
orc = Orchestrator()

POST_ACTIONS_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✂️ Короче", callback_data="post_short"),
        InlineKeyboardButton(text="📝 Длиннее", callback_data="post_long"),
        InlineKeyboardButton(text="😊 Человечнее", callback_data="post_human"),
    ],
    [
        InlineKeyboardButton(text="⚡ Хлестче", callback_data="post_punch"),
        InlineKeyboardButton(text="✅ Грамматика", callback_data="post_grammar"),
        InlineKeyboardButton(text="🔄 Переписать", callback_data="post_regen"),
    ],
    [
        InlineKeyboardButton(text="👍 Готово", callback_data="post_done"),
    ],
])


# ─── Post action buttons ──────────────────────────────────────────────────────

async def _apply_edit(callback: CallbackQuery, command: str):
    """Apply editor command to cached post and update message."""
    cached = get_post(callback.from_user.id)
    post_text = cached.get("text", "")
    topic = cached.get("topic", "")

    if not post_text:
        await callback.answer("Пост не найден. Сгенерируй заново.", show_alert=True)
        return

    await callback.answer("Обрабатываю...")
    await callback.message.edit_reply_markup(reply_markup=None)  # hide buttons while loading

    try:
        style_guide = load_style_guide()
        edited = await orc.editor.edit(post_text, command, style_guide)
        new_text = _extract_result(edited) or edited
        # Update cache with new version
        save_post(callback.from_user.id, new_text, topic)
        await callback.message.edit_text(new_text, reply_markup=POST_ACTIONS_KEYBOARD)
    except Exception as e:
        await callback.message.edit_text(post_text, reply_markup=POST_ACTIONS_KEYBOARD)
        await callback.answer(f"Ошибка: {e}", show_alert=True)


@router.callback_query(lambda c: c.data == "post_short")
async def cb_post_short(callback: CallbackQuery):
    await _apply_edit(callback, "shorten")


@router.callback_query(lambda c: c.data == "post_long")
async def cb_post_long(callback: CallbackQuery):
    await _apply_edit(callback, "expand")


@router.callback_query(lambda c: c.data == "post_human")
async def cb_post_human(callback: CallbackQuery):
    await _apply_edit(callback, "humanize")


@router.callback_query(lambda c: c.data == "post_punch")
async def cb_post_punch(callback: CallbackQuery):
    await _apply_edit(callback, "punch")


@router.callback_query(lambda c: c.data == "post_grammar")
async def cb_post_grammar(callback: CallbackQuery):
    await _apply_edit(callback, "grammar")


@router.callback_query(lambda c: c.data == "post_regen")
async def cb_post_regen(callback: CallbackQuery):
    cached = get_post(callback.from_user.id)
    topic = cached.get("topic", "")
    if not topic:
        await callback.answer("Тема не найдена. Сгенерируй заново через кнопку.", show_alert=True)
        return
    await callback.answer("Переписываю...")
    await callback.message.edit_reply_markup(reply_markup=None)
    try:
        style_guide = load_style_guide()
        new_post = await orc._generate_post_only(topic, style_guide)
        save_post(callback.from_user.id, new_post, topic)
        await callback.message.edit_text(new_post, reply_markup=POST_ACTIONS_KEYBOARD)
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=POST_ACTIONS_KEYBOARD)


@router.callback_query(lambda c: c.data == "post_done")
async def cb_post_done(callback: CallbackQuery):
    """Remove buttons — post is ready to copy."""
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Готово! Текст выше можно копировать в канал.")
    clear_post(callback.from_user.id)


# ─── Settings buttons ─────────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "settings_status")
async def cb_status(callback: CallbackQuery):
    sg = load_style_guide()
    plan = load_plan()

    style_info = "❌ Не загружен"
    if sg:
        tone = sg.get("tone", "—")
        avg_len = sg.get("avg_post_length", "—")
        style_info = f"✅ Загружен\n   Тон: {tone}\n   Средняя длина: {avg_len} симв."

    plan_info = "❌ Пуст"
    if plan:
        total = len(plan)
        done = sum(1 for i in plan if i.get("status") == "done")
        plan_info = f"✅ {total} постов (выполнено {done})"

    await callback.message.edit_text(
        f"*Статус КопиБОТА*\n\n"
        f"🎨 Стиль:\n{style_info}\n\n"
        f"📋 Контент-план:\n{plan_info}",
        parse_mode="Markdown",
        reply_markup=callback.message.reply_markup,
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "settings_reset_style")
async def cb_reset_style(callback: CallbackQuery):
    if STYLE_GUIDE_PATH.exists():
        STYLE_GUIDE_PATH.unlink()
        await callback.answer("Стилевой профиль удалён", show_alert=True)
        await callback.message.edit_text(
            "🗑 Стилевой профиль удалён.\n\n"
            "Загрузи новый архив через «Мой стиль».",
            reply_markup=None,
        )
    else:
        await callback.answer("Стиль не был загружен", show_alert=True)


@router.callback_query(lambda c: c.data == "settings_reset_plan")
async def cb_reset_plan(callback: CallbackQuery):
    if CONTENT_PLAN_PATH.exists():
        CONTENT_PLAN_PATH.unlink()
        await callback.answer("Контент-план очищен", show_alert=True)
        await callback.message.edit_text(
            "🗑 Контент-план очищен.\n\n"
            "Загрузи новый план через файл или попроси создать: «создай план на месяц».",
            reply_markup=None,
        )
    else:
        await callback.answer("План был пуст", show_alert=True)


@router.callback_query(lambda c: c.data == "settings_about")
async def cb_about(callback: CallbackQuery):
    await callback.message.edit_text(
        "*КопиБОТ* — AI-копирайтер для Telegram\n\n"
        "Умеет:\n"
        "• Писать посты в твоём стиле\n"
        "• Создавать контент-планы\n"
        "• Редактировать тексты (короче, длиннее, живее, хлестче)\n"
        "• Исправлять грамматику\n"
        "• Оценивать тексты по шкале 1-10\n\n"
        "Работает на Claude (Anthropic) через OpenRouter.\n\n"
        "Для загрузки стиля: нажми «Мой стиль» и прикрепи .md или .json файл.",
        parse_mode="Markdown",
        reply_markup=None,
    )
    await callback.answer()
