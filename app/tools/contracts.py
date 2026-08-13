"""Normalize heterogeneous NBA endpoint payloads at the Agent boundary."""

import json
from typing import Any, TypedDict


class ToolResult(TypedDict, total=False):
    """Stable result envelope shared by legacy and native tool callers."""

    source: str
    data_type: str
    records: list[dict[str, Any]]
    game_ids: list[str]
    cache_hit: bool
    ok: bool
    error: str
    error_type: str
    raw: str


def normalize_tool_result(raw: str, data_type: str) -> ToolResult:
    def failure(error: str, error_type: str, raw_value: object = "") -> ToolResult:
        return {
            "source": "unknown",
            "data_type": data_type,
            "records": [],
            "game_ids": [],
            "cache_hit": False,
            "ok": False,
            "error": error,
            "error_type": error_type,
            "raw": str(raw_value),
        }

    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return failure("invalid_json", "parse_error", raw)
    if not isinstance(payload, dict):
        return failure("invalid_payload", "schema_error", payload)
    if isinstance(payload.get("records"), list):
        records = payload["records"]
    elif isinstance(payload.get("matches"), list):
        records = payload["matches"]
    elif isinstance(payload.get("players"), list):
        records = payload["players"]
    elif isinstance(payload.get("events"), list):
        records = payload["events"]
    else:
        records = [payload] if not payload.get("error") else []
    game_ids: list[str] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        game_id = item.get("game_id") or item.get("gameId")
        if game_id is not None and str(game_id) not in game_ids:
            game_ids.append(str(game_id))
    direct_game_id = payload.get("game_id") or payload.get("gameId")
    if direct_game_id is not None and str(direct_game_id) not in game_ids:
        game_ids.insert(0, str(direct_game_id))
    error = str(payload.get("error") or "")
    result = {
        **payload,
        "data_type": data_type,
        "records": records,
        "game_ids": game_ids,
        "cache_hit": bool(payload.get("cache_hit")),
        "ok": not bool(error) and bool(records),
        "error_type": "tool_error" if error else "",
    }
    return result
