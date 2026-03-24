import os
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_client: Optional[Client] = None


def get_db() -> Client:
    """Возвращает Supabase клиент (service_role — обходит RLS)."""
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL и SUPABASE_SERVICE_KEY должны быть в .env")
        _client = create_client(url, key)
    return _client
