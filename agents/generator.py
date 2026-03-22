import json
from agents.base import BaseAgent


SYSTEM_PROMPT_WITH_STYLE = """Ты копирайтер, пишущий в точном стиле автора, описанном в стилевом профиле.

Правила:
- Строго следуй стилевому профилю: тон, ритм, словарный запас, структура
- Никаких клише ИИ: "В мире где...", "Давайте поговорим о...", "Безусловно", "Несомненно"
- Никакого наполнителя — каждое слово должно работать
- Пиши живо, как настоящий человек
- Соблюдай среднюю длину поста из профиля
- Используй эмодзи так же, как описано в профиле
- Не добавляй хэштеги если в профиле hashtag_usage: false

Верни ТОЛЬКО текст поста. Без пояснений, без заголовков типа "Пост:" или "Вот пост:"."""

SYSTEM_PROMPT_DEFAULT = """Ты копирайтер для Telegram-канала. Пишешь прямо, без воды, без клише.

Правила:
- Пиши коротко и хлёстко
- Первое предложение должно захватить внимание
- Никаких клише ИИ: "В мире где...", "Давайте поговорим о...", "Безусловно"
- Никакого наполнителя — каждое слово должно работать
- Пиши как умный человек, которому есть что сказать
- Длина поста: 200-400 символов для short, 400-800 для medium, 800-1500 для long

Верни ТОЛЬКО текст поста. Без пояснений, без заголовков."""


class Generator(BaseAgent):
    def __init__(self):
        super().__init__(model_key="sonnet")

    async def generate(
        self,
        topic: str,
        brief: str = None,
        style_guide: dict = None,
        format: str = "short",
        variants: int = 1,
    ) -> str:
        if style_guide:
            system = SYSTEM_PROMPT_WITH_STYLE + f"\n\nСтилевой профиль автора:\n{json.dumps(style_guide, ensure_ascii=False, indent=2)}"
        else:
            system = SYSTEM_PROMPT_DEFAULT

        user_parts = [f"Тема поста: {topic}"]
        user_parts.append(f"Формат: {format}")

        if brief:
            user_parts.append(f"\nБриф от ресёрчера:\n{brief}")

        if variants > 1:
            user_parts.append(
                f"\nНапиши {variants} варианта поста. Разделяй их строкой: ---ВАРИАНТ---"
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n".join(user_parts)},
        ]
        try:
            return await self.call_llm(messages)
        except Exception as e:
            return f"_Ошибка генерации поста: {e}_"
