import json
import re
from datetime import date
from agents.base import BaseAgent


SYSTEM_PROMPT = """Ты лингвист, анализирующий авторский стиль письма. Изучи предоставленные посты и составь детальный стилевой профиль.

Возвращай ТОЛЬКО валидный JSON в следующем формате:
{
  "version": "дата в формате ГГГГ-ММ-ДД",
  "tone": "описание тона (например: деловой, саркастичный, дружелюбный, провокационный)",
  "sentence_rhythm": "описание ритма предложений (короткие рубленые / длинные разворачивающиеся / смешанный)",
  "typical_openers": ["пример зачина 1", "пример зачина 2", "пример зачина 3"],
  "vocabulary": {
    "preferred": ["слово1", "слово2", "слово3"],
    "forbidden": ["слово1", "слово2"]
  },
  "structure_patterns": ["описание паттерна 1", "описание паттерна 2"],
  "avg_post_length": 320,
  "emoji_usage": "описание использования эмодзи (не использует / редко / активно)",
  "hashtag_usage": false,
  "signature_moves": ["фирменный приём 1", "фирменный приём 2"]
}

Анализируй внимательно: как автор начинает посты, какие слова предпочитает, как строит аргументы, как заканчивает. Не добавляй пояснений — только JSON."""


class StyleAnalyst(BaseAgent):
    def __init__(self):
        super().__init__(model_key="opus")

    async def analyze(self, texts: list[str]) -> dict:
        posts_block = "\n\n---\n\n".join(texts)
        today = date.today().isoformat()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Проанализируй следующие {len(texts)} постов и составь стилевой профиль автора:\n\n{posts_block}",
            },
        ]
        try:
            raw = await self.call_llm(messages)
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            guide = json.loads(raw)
            guide.setdefault("version", today)
            return guide
        except Exception as e:
            return {
                "version": today,
                "tone": "нейтральный",
                "sentence_rhythm": "смешанный",
                "typical_openers": [],
                "vocabulary": {"preferred": [], "forbidden": []},
                "structure_patterns": [],
                "avg_post_length": 300,
                "emoji_usage": "не определено",
                "hashtag_usage": False,
                "signature_moves": [],
                "_error": str(e),
            }
