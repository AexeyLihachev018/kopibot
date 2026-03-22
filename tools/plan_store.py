import json
from config import CONTENT_PLAN_PATH


def load_plan() -> list[dict]:
    if CONTENT_PLAN_PATH.exists():
        return json.loads(CONTENT_PLAN_PATH.read_text(encoding="utf-8"))
    return []


def save_plan(plan: list[dict]):
    CONTENT_PLAN_PATH.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def mark_done(plan: list[dict], item_id: str) -> list[dict]:
    for item in plan:
        if item.get("id") == item_id:
            item["status"] = "done"
    return plan
