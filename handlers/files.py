from aiogram import Router, Bot, F
from aiogram.types import Message
from orchestrator import Orchestrator

router = Router()
orc = Orchestrator()


@router.message(F.document)
async def handle_document(message: Message, bot: Bot):

    doc = message.document
    filename = doc.file_name or "file.txt"

    if not (
        filename.endswith(".md")
        or filename.endswith(".json")
        or filename.endswith(".txt")
    ):
        await message.answer("Поддерживаются файлы: .md, .json, .txt")
        return

    msg = await message.answer(f"Получил файл {filename}, обрабатываю...")

    try:
        file = await bot.get_file(doc.file_id)
        downloaded = await bot.download_file(file.file_path)
        content = downloaded.read().decode("utf-8", errors="ignore")
        result = await orc.handle_file(filename, content)
        await msg.edit_text(result, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"Ошибка при обработке файла: {e}")
