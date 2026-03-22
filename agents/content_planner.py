from __future__ import annotations
import json
import re
from datetime import date, timedelta
from agents.base import BaseAgent


SYSTEM_PROMPT_PARSE = """Ты парсер контент-планов. Прочитай текст и извлеки список постов в виде JSON-массива.

Каждый пункт плана должен иметь формат:
{
  "id": "001",
  "date": "ГГГГ-ММ-ДД или пустая строка если нет даты",
  "topic": "тема поста",
  "format": "short/medium/long",
  "rubric": "рубрика или категория",
  "status": "planned",
  "notes": "заметки или пустая строка"
}

Если каких-то полей нет — ставь разумные значения по умолчанию.
Нумерацию id делай с ведущими нулями: 001, 002, 003...
Возвращай ТОЛЬКО валидный JSON-массив. Без пояснений."""

SYSTEM_PROMPT_CREATE = """Ты стратег контент-планирования для Telegram-каналов.

Создай детальный контент-план на заданный период. Учитывай:
- Разнообразие форматов (короткие мысли, разборы, истории, кейсы, списки)
- Баланс между развлечением, пользой и продажами
- Естественный ритм публикаций
- Если дан стилевой профиль — учитывай типичные темы и форматы автора
- Если даны существующие посты — не повторяй уже освещённые темы

Возвращай JSON-массив постов:
[
  {
    "id": "001",
    "date": "ГГГГ-ММ-ДД",
    "topic": "конкретная тема поста",
    "format": "short/medium/long",
    "rubric": "рубрика",
    "status": "planned",
    "notes": "подсказки для копирайтера"
  }
]

Возвращай ТОЛЬКО валидный JSON. Без пояснений."""


class ContentPlanner(BaseAgent):
    def __init__(self):
        super().__init__(model_key="sonnet")

    async def parse_plan(self, text: str) -> list[dict]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_PARSE},
            {"role": "user", "content": f"Извлеки контент-план из текста:\n\n{text}"},
        ]
        try:
            raw = await self.call_llm(messages)
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            plan = json.loads(raw)
            if not isinstance(plan, list):
                return []
            return self._normalize_plan(plan)
        except Exception:
            return []

    async def create_plan(
        self,
        period: str,
        topic: str,
        style_guide: dict = None,
        existing_posts: list[str] = None,
    ) -> list[dict]:
        today = date.today()
        user_parts = [
            f"Период: {period}",
            f"Основная тема/направление: {topic}",
            f"Дата начала: {today.isoformat()}",
        ]

        if style_guide:
            user_parts.append(
                f"\nСтилевой профиль автора:\n{json.dumps(style_guide, ensure_ascii=False, indent=2)}"
            )

        if existing_posts:
            sample = existing_posts[:10]
            user_parts.append(
                f"\nПоследние посты автора (не повторяй темы):\n" + "\n---\n".join(sample)
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_CREATE},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        try:
            raw = await self.call_llm(messages)
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            plan = json.loads(raw)
            if not isinstance(plan, list):
                return []
            return self._normalize_plan(plan)
        except Exception as e:
            # Fallback: return a minimal plan
            return [
                {
                    "id": "001",
                    "date": today.isoformat(),
                    "topic": topic,
                    "format": "short",
                    "rubric": "основное",
                    "status": "planned",
                    "notes": f"Ошибка генерации плана: {e}",
                }
            ]

    async def get_next(self, plan: list[dict]) -> dict | None:
        for item in plan:
            if item.get("status") == "planned":
                return item
        return None

    async def format_plan_message(self, plan: list[dict]) -> str:
        if not plan:
            return "Контент-план пуст."

        lines = ["*Контент-план*\n"]
        status_icons = {"planned": "⬜", "done": "✅", "in_progress": "🔄"}

        for item in plan:
            icon = status_icons.get(item.get("status", "planned"), "⬜")
            item_id = item.get("id", "—")
            topic = item.get("topic", "—")
            fmt = item.get("format", "")
            rubric = item.get("rubric", "")
            item_date = item.get("date", "")
            notes = item.get("notes", "")

            meta_parts = []
            if item_date:
                meta_parts.append(item_date)
            if fmt:
                meta_parts.append(fmt)
            if rubric:
                meta_parts.append(rubric)

            meta = " | ".join(meta_parts)
            line = f"{icon} `{item_id}` {topic}"
            if meta:
                line += f"\n    _{meta}_"
            if notes and item.get("status") != "done":
                line += f"\n    💡 {notes}"
            lines.append(line)

        total = len(plan)
        done = sum(1 for i in plan if i.get("status") == "done")
        lines.append(f"\n_Готово: {done}/{total}_")

        return "\n".join(lines)

    def _normalize_plan(self, plan: list[dict]) -> list[dict]:
        normalized = []
        for i, item in enumerate(plan):
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "id": item.get("id", str(i + 1).zfill(3)),
                    "date": item.get("date", ""),
                    "topic": item.get("topic", ""),
                    "format": item.get("format", "short"),
                    "rubric": item.get("rubric", ""),
                    "status": item.get("status", "planned"),
                    "notes": item.get("notes", ""),
                }
            )
        return normalized
