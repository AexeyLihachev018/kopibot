import os
import base64
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()


def _get_fernet() -> Fernet:
    """Возвращает Fernet-шифровальщик из ENCRYPTION_KEY в .env."""
    key = os.getenv("ENCRYPTION_KEY", "")
    if not key:
        # Если ключа нет — генерируем и подсказываем добавить
        raise RuntimeError(
            "ENCRYPTION_KEY не найден в .env\n"
            "Добавь строку: ENCRYPTION_KEY=" + Fernet.generate_key().decode()
        )
    return Fernet(key.encode())


def encrypt_token(token: str) -> str:
    """Шифрует токен бота. Возвращает строку для хранения в БД."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Расшифровывает токен бота из БД."""
    return _get_fernet().decrypt(encrypted.encode()).decode()


def generate_new_key() -> str:
    """Генерирует новый ключ шифрования (запусти один раз для настройки)."""
    return Fernet.generate_key().decode()
