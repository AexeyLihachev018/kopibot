import json
import re
from agents.base import BaseAgent


SYSTEM_PROMPT = """Ты диспетчер запросов Telegram-бота копирайтера. Анализируй сообщение пользователя и возвращай JSON с намерением.

ВАЖНО: Если сообщение похоже на тему поста (вопрос, утверждение, идея, история — особенно короткая фраза без команды редактирования) — это generate_post. Сомневаешься между generate_post и unknown — выбирай generate_post.

ВАЖНО: Если сообщение содержит тему + период/длительность (например "продажи, 1 неделя", "маркетинг, месяц", "бизнес 2 недели", "личный бренд на месяц") — это create_plan.

Возможные намерения:
- generate_post — пользователь хочет написать пост (любая тема, идея, вопрос, короткая фраза)
- edit_post — пользователь хочет отредактировать СУЩЕСТВУЮЩИЙ текст с командой (живее/короче/хлестче и т.д.)
- create_plan — пользователь хочет создать контент-план (явная просьба создать план, или формат "тема, период")
- generate_from_plan — пользователь хочет посты из существующего плана
- analyze_style — пользователь спрашивает о своём стиле
- critique — пользователь хочет оценку текста (есть слово "оцени")
- research — пользователь хочет факты по теме
- show_plan — пользователь хочет увидеть текущий план
- plan_done — пользователь отмечает пост как готовый (извлеки id)
- next_post — пользователь спрашивает что писать следующим
- unknown — только если явно не относится ни к чему из списка

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


def _local_classify(text: str) -> dict | None:
    """Fast local classifier — no API needed. Returns None if uncertain."""
    t = text.lower().strip()

    # Show plan
    if any(kw in t for kw in ["покажи план", "показать план", "мой план", "текущий план"]):
        return {"intent": "show_plan", "topic": None, "command": None, "text": None, "plan_id": None}

    # Next post
    if any(kw in t for kw in ["следующий пост", "что дальше", "следующий по плану"]):
        return {"intent": "next_post", "topic": None, "command": None, "text": None, "plan_id": None}

    # Plan done
    done_match = re.search(r'готово\s+(\d+)', t)
    if done_match:
        return {"intent": "plan_done", "topic": None, "command": None, "text": None, "plan_id": done_match.group(1).zfill(3)}

    # Create plan — explicit keywords
    plan_keywords = ["создай план", "создать план", "контент-план", "контент план", "план на месяц",
                     "план на неделю", "план публикаций", "план постов", "сделай план"]
    if any(kw in t for kw in plan_keywords):
        # Extract topic: remove plan keywords
        topic = text
        for kw in plan_keywords:
            topic = re.sub(kw, "", topic, flags=re.IGNORECASE).strip(" :,-")
        return {"intent": "create_plan", "topic": topic or text, "command": None, "text": None, "plan_id": None}

    # Create plan — "тема, период" pattern
    period_pattern = r'(\d+\s*(?:день|дня|дней|неделя|недели|недель|неделю)|месяц|месяца|два месяца|полмесяца)'
    if re.search(period_pattern, t):
        return {"intent": "create_plan", "topic": text, "command": None, "text": None, "plan_id": None}

    # Analyze style
    if any(kw in t for kw in ["мой стиль", "стилевой профиль", "покажи стиль"]):
        return {"intent": "analyze_style", "topic": None, "command": None, "text": None, "plan_id": None}

    # Edit commands (require a command word + text)
    edit_map = {
        "humanize": ["живее", "очеловечь", "по-человечески"],
        "shorten": ["короче", "сократи", "сокращение"],
        "punch": ["хлестче", "жёстче", "резче", "мощнее"],
        "simplify": ["проще", "упрости"],
        "hook": ["зацепка", "зацепи", "крюк"],
        "casual": ["разговорно", "по-разговорному", "неформально"],
        "expert": ["экспертно", "профессионально"],
        "restructure": ["реструктурируй", "перестрой"],
        "cut_half": ["вдвое короче", "урежь вдвое", "половину убери"],
    }
    for cmd, keywords in edit_map.items():
        for kw in keywords:
            if t.startswith(kw):
                rest = text[len(kw):].strip(" :,")
                if rest:
                    return {"intent": "edit_post", "topic": None, "command": cmd, "text": rest, "plan_id": None}

    # Critique
    if t.startswith("оцени") or "оцени этот" in t or "оцени пост" in t:
        post_text = re.sub(r'^оцени[:\s]*', '', text, flags=re.IGNORECASE).strip()
        return {"intent": "critique", "topic": None, "command": None, "text": post_text or text, "plan_id": None}

    # Generate post — explicit keywords
    if any(kw in t for kw in ["напиши пост", "написать пост", "пост о ", "пост про ", "напиши о "]):
        topic = re.sub(r'напиши пост[:\s]*о?|написать пост[:\s]*о?|пост о|пост про|напиши о', '', text, flags=re.IGNORECASE).strip(" :,")
        return {"intent": "generate_post", "topic": topic or text, "command": None, "text": None, "plan_id": None}

    return None  # uncertain — let LLM decide


class Dispatcher(BaseAgent):
    def __init__(self):
        super().__init__(model_key="haiku")

    async def classify(self, user_message: str) -> dict:
        # Try local classifier first (no API cost, instant)
        local = _local_classify(user_message)
        if local is not None:
            return local

        # Fall back to LLM for ambiguous cases
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]
        try:
            raw = await self.call_llm(messages)
            raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
            raw = re.sub(r"\s*```$", "", raw.strip())
            result = json.loads(raw)
            return result
        except Exception:
            # If API fails — default to generate_post for short messages, unknown for long
            if len(user_message) < 200:
                return {"intent": "generate_post", "topic": user_message, "command": None, "text": None, "plan_id": None}
            return {"intent": "unknown", "topic": None, "command": None, "text": None, "plan_id": None}
