from aiogram import Router
from aiogram.types import CallbackQuery
from tools.style_store import load_style_guide
from tools.plan_store import load_plan
from config import STYLE_GUIDE_PATH, CONTENT_PLAN_PATH
import json

router = Router()


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
        "• Редактировать тексты (короче, живее, хлестче)\n"
        "• Оценивать тексты по шкале 1-10\n\n"
        "Работает на Claude (Anthropic) через OpenRouter.\n\n"
        "Для загрузки стиля: нажми «Мой стиль» и прикрепи .md или .json файл.",
        parse_mode="Markdown",
        reply_markup=None,
    )
    await callback.answer()
