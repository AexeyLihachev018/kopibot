# In-memory cache for the last generated post per user
# Stores: {user_id: {"text": str, "topic": str}}

_cache: dict = {}


def save_post(user_id: int, text: str, topic: str = "") -> None:
    _cache[user_id] = {"text": text, "topic": topic}


def get_post(user_id: int) -> dict:
    return _cache.get(user_id, {})


def clear_post(user_id: int) -> None:
    _cache.pop(user_id, None)
