"""Small shared helpers used by domain tools."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.cache.manager import cache_get, cache_set


def dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def cached(namespace: str, key: str) -> str | None:
    value = cache_get(namespace, key, 900)
    if value is None:
        return None
    try:
        payload = json.loads(value)
        if isinstance(payload, dict):
            payload["cache_hit"] = True
            return dump(payload)
    except (TypeError, json.JSONDecodeError):
        return value
    return value


def save(namespace: str, key: str, payload: str) -> str:
    cache_set(namespace, key, payload)
    return payload


def beijing_time(value: object) -> str | None:
    """Convert an ISO UTC/offset timestamp to Asia/Shanghai."""
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()
    except ValueError:
        return None
