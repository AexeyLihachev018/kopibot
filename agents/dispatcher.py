import json
import re
from agents.base import BaseAgent


SYSTEM_PROMPT = """Ты диспетчер запросов. Анализируй сообщение пользователя и возвращай JSON с намерением и маршрутом.

Возможные намерения:
- upload_archive — пользователь загрузил файл MD/JSON с архивом канала
- upload_plan — пользователь загрузил файл контент-плана
- generate_post — пользователь хочет написать пост (извлеки тему)
- edit_post — пользователь хочет отредактировать текст (извлеки команду: humanize/shorten/punch/simplify/hook/casual/expert/restructure/cut_half)
- create_plan — пользователь хочет создать контент-план
- generate_from_plan — пользователь хочет посты из существующего плана
- analyze_style — пользователь спрашивает о своём стиле
- critique — пользователь хочет оценку текста
- research — пользователь хочет факты по теме
- show_plan — пользователь хочет увидеть текущий план
- plan_done — пользователь отмечает пост как готовый (извлеки id)
- next_post — пользователь спрашивает что писать следующим
- unknown — непонятный запрос

Маппинг команд редактирования:
- "живее", "очеловечь", "по-человечески" → humanize
- "короче", "сократи", "сокращение" → shorten
- "хлестче", "жёстче", "резче", "мощнее" → punch
- "проще", "упрости" → simplify
- "зацепка", "зацепи", "крюк" → hook
- "разговорно", "по-разговорному", "неформально" → casual
- "экспертно", "профессионально" → expert
- "реструктурируй", "перестрой" → restructure
- "вдвое короче", "урежь вдвое", "половину убери" → cut_half

Возвращай ТОЛЬКО валидный JSON в следующем формате:
{
  "intent": "generate_post",
  "topic": "извлечённая тема или null",
  "command": "команда редактирования или null",
  "text": "текст для редактирования или null",
  "plan_id": "id пункта плана или null"
}

Не добавляй никаких пояснений. Только JSON."""


class Dispatcher(BaseAgent):
    def __init__(self):
        super().__init__(model_key="haiku")

    async def classify(self, user_message: str) -> dict:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        try:
            raw = await self.call_llm(messages)
            # Strip markdown code block if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            return json.loads(raw)
        except Exception:
            return {
                "intent": "unknown",
                "topic": None,
                "command": None,
                "text": None,
                "plan_id": None,
            }
