import json
from agents.base import BaseAgent


SYSTEM_PROMPT = """Ты редактор текстов для Telegram. Применяй команду редактирования строго и точно.

Команды:
- humanize — сделай текст живее, по-человечески, убери канцелярит и сухость
- shorten — сократи текст на 30-40%, сохранив смысл
- punch — сделай текст хлёстче, резче, мощнее — каждое слово должно бить
- simplify — упрости язык, убери сложные конструкции, сделай понятным для всех
- hook — улучши первое предложение, сделай его цепляющим, заставляющим читать дальше
- casual — переведи в разговорный стиль, как будто говоришь другу
- expert — добавь экспертности, авторитетности, конкретики
- restructure — перестрой структуру текста для лучшего восприятия
- cut_half — сократи ровно вдвое, оставив только самое важное

Правила:
- Сохраняй смысл и позицию автора
- Не добавляй то, чего не было в оригинале (кроме команды expert)
- Пиши только на русском

Формат ответа:
ОРИГИНАЛ:
[исходный текст]

РЕЗУЛЬТАТ:
[отредактированный текст]

ПРАВКИ:
[одна строка — что именно было сделано]"""


COMMAND_DESCRIPTIONS = {
    "humanize": "очеловечить",
    "shorten": "сократить",
    "punch": "сделать хлёстче",
    "simplify": "упростить",
    "hook": "улучшить зацепку",
    "casual": "разговорный стиль",
    "expert": "добавить экспертности",
    "restructure": "реструктурировать",
    "cut_half": "сократить вдвое",
}


class Editor(BaseAgent):
    def __init__(self):
        super().__init__(model_key="sonnet")

    async def edit(self, text: str, command: str, style_guide: dict = None) -> str:
        system = SYSTEM_PROMPT
        if style_guide:
            system += f"\n\nСтилевой профиль автора (учитывай при редактуре):\n{json.dumps(style_guide, ensure_ascii=False, indent=2)}"

        cmd_desc = COMMAND_DESCRIPTIONS.get(command, command)
        user_content = f"Команда: {command} ({cmd_desc})\n\nТекст для редактирования:\n{text}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        try:
            return await self.call_llm(messages)
        except Exception as e:
            return f"_Ошибка редактирования: {e}_"
