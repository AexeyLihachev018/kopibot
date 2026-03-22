import json
import re
from agents.base import BaseAgent


SYSTEM_PROMPT = """Ты суровый, но справедливый литературный критик для Telegram-контента.

Оценивай пост по пяти критериям (каждый от 1 до 10):
- style — соответствие авторскому стилю и голосу
- structure — логика и построение текста
- hook — сила первого предложения / зацепки
- content — качество фактуры, глубина, ценность для читателя
- length — соответствие длины формату Telegram

Итоговая оценка (score) — среднее по пяти критериям, округлённое до целого.

Решение:
- "publish" — если score 8-10 (публиковать как есть)
- "revise" — если score 5-7 (доработать)
- "rewrite" — если score 1-4 (переписать с нуля)

Для "revise" обязательно укажи edit_commands (список из: humanize, shorten, punch, simplify, hook, casual, expert, restructure, cut_half).

Возвращай ТОЛЬКО валидный JSON:
{
  "score": 7,
  "breakdown": {
    "style": 8,
    "structure": 6,
    "hook": 7,
    "content": 8,
    "length": 6
  },
  "issues": ["проблема 1", "проблема 2"],
  "decision": "revise",
  "edit_commands": ["shorten", "punch"],
  "comment": "краткий комментарий критика"
}

Будь честным. Не льсти. Если текст плохой — скажи прямо."""


class Critic(BaseAgent):
    def __init__(self):
        super().__init__(model_key="opus")

    async def critique(self, text: str, style_guide: dict = None) -> dict:
        system = SYSTEM_PROMPT
        if style_guide:
            system += f"\n\nСтилевой профиль автора (используй для оценки критерия style):\n{json.dumps(style_guide, ensure_ascii=False, indent=2)}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Оцени этот пост:\n\n{text}"},
        ]
        try:
            raw = await self.call_llm(messages)
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            result = json.loads(raw)
            # Validate required fields
            result.setdefault("score", 5)
            result.setdefault("breakdown", {})
            result.setdefault("issues", [])
            result.setdefault("decision", "revise")
            result.setdefault("edit_commands", [])
            result.setdefault("comment", "")
            return result
        except Exception as e:
            return {
                "score": 5,
                "breakdown": {
                    "style": 5,
                    "structure": 5,
                    "hook": 5,
                    "content": 5,
                    "length": 5,
                },
                "issues": [f"Ошибка получения оценки: {e}"],
                "decision": "revise",
                "edit_commands": [],
                "comment": "Не удалось получить оценку критика.",
            }
