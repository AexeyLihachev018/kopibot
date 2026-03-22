from __future__ import annotations
import json
from config import STYLE_GUIDE_PATH


def load_style_guide() -> dict | None:
    if STYLE_GUIDE_PATH.exists():
        return json.loads(STYLE_GUIDE_PATH.read_text(encoding="utf-8"))
    return None


def save_style_guide(guide: dict):
    STYLE_GUIDE_PATH.write_text(
        json.dumps(guide, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def style_guide_summary(guide: dict) -> str:
    """Return compact string summary for LLM prompts."""
    if not guide:
        return ""
    return json.dumps(guide, ensure_ascii=False)
