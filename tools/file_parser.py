import json
import re
from pathlib import Path


def parse_md_archive(content: str) -> list[str]:
    """Extract post texts from MD file. Split by --- or ## headers."""
    # Try splitting by --- separator
    posts = re.split(r'\n---+\n', content)
    # Also try ## Post or ## headers
    if len(posts) <= 1:
        posts = re.split(r'\n#{1,3} ', content)
    return [p.strip() for p in posts if p.strip() and len(p.strip()) > 50]


def parse_json_archive(content: str) -> list[str]:
    """Extract texts from JSON export (Telegram Desktop format or TGStat)."""
    data = json.loads(content)
    texts = []
    # Telegram Desktop export format
    if isinstance(data, dict) and "messages" in data:
        for msg in data["messages"]:
            if isinstance(msg.get("text"), str) and len(msg["text"]) > 50:
                texts.append(msg["text"])
            elif isinstance(msg.get("text"), list):
                text = "".join(
                    p if isinstance(p, str) else p.get("text", "")
                    for p in msg["text"]
                )
                if len(text) > 50:
                    texts.append(text)
    # Simple list of strings
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str) and len(item) > 50:
                texts.append(item)
            elif isinstance(item, dict):
                for key in ["text", "content", "body", "message"]:
                    if isinstance(item.get(key), str) and len(item[key]) > 50:
                        texts.append(item[key])
                        break
    return texts


def parse_file(filename: str, content: str) -> list[str]:
    """Auto-detect format and parse."""
    if filename.endswith(".json"):
        try:
            return parse_json_archive(content)
        except Exception:
            return []
    elif filename.endswith(".md") or filename.endswith(".txt"):
        return parse_md_archive(content)
    return []
