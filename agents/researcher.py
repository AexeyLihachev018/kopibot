import json
from agents.base import BaseAgent


SYSTEM_PROMPT = """Ты ресёрчер, готовящий бриф для копирайтера.

По заданной теме:
1. Найди релевантные факты, примеры, статистику
2. Проверь, не освещалась ли тема уже в архиве автора
3. Предложи несколько углов подачи материала
4. Укажи на что стоит обратить особое внимание

Возвращай структурированный бриф на русском языке в формате Markdown.
Структура брифа:
## Тема
## Ключевые факты и данные
## Возможные углы подачи
## Что уже было в архиве (если релевантно)
## Рекомендации для копирайтера

Пиши кратко и по делу. Бриф должен помочь написать сильный пост."""


class Researcher(BaseAgent):
    def __init__(self):
        super().__init__(model_key="sonnet")

    async def research(
        self,
        topic: str,
        archive_posts: list[str] = None,
        style_guide: dict = None,
    ) -> str:
        user_content_parts = [f"Тема: {topic}"]

        if archive_posts:
            sample = archive_posts[:10]
            archive_block = "\n\n---\n\n".join(sample)
            user_content_parts.append(
                f"\nАрхив постов автора (последние {len(sample)}):\n\n{archive_block}"
            )

        if style_guide:
            user_content_parts.append(
                f"\nСтилевой профиль автора:\n{json.dumps(style_guide, ensure_ascii=False, indent=2)}"
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(user_content_parts)},
        ]
        try:
            return await self.call_llm(messages)
        except Exception as e:
            return f"## Тема\n{topic}\n\n_Ошибка при подготовке брифа: {e}_"
