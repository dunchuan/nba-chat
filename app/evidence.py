"""Generic evidence checks for the native ReAct loop.

The checker does not decide which endpoint to call.  It only reports whether
the observations collected so far cover the user's requested scope, so the
model can choose the next action.
"""

import re
from typing import Any


def _query_text(query: str) -> str:
    return (query or "").lower()


def _is_finals_query(query: str) -> bool:
    text = _query_text(query)
    return any(token in text for token in ("nba finals", "finals", "总决赛", "总决"))


def _has_records(payload: dict[str, Any]) -> bool:
    for key in ("records", "matches", "players", "events"):
        if isinstance(payload.get(key), list) and payload[key]:
            return True
    return False


def evaluate_tool_evidence(query: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate coverage without selecting or ordering tools.

    A broad Playoffs game log is useful evidence, but it is not evidence for
    a Finals-only question.  The returned feedback is deliberately written
    for the model and is stored in graph state for the next ReAct step.
    """
    if not payloads:
        return {"complete": True, "missing": [], "feedback": ""}
    latest = payloads[-1]
    if latest.get("error") or not latest.get("ok", _has_records(latest)):
        return {
            "complete": False,
            "missing": ["reliable_data"],
            "feedback": "最近一次工具没有返回可用数据。请检查参数或选择能直接覆盖用户问题的 NBA 数据工具，不要猜测。",
        }

    coverage = latest.get("coverage") or {}
    if _is_finals_query(query) and coverage.get("scope") == "full_playoffs":
        return {
            "complete": False,
            "missing": ["finals_series_scope"],
            "feedback": (
                "当前结果只是该赛季全部季后赛，不能当作 NBA 总决赛。"
                "请继续调用能返回比赛系列赛标签/比赛 ID 的 NBA 赛程工具，"
                "并确认 gameLabel 或等价字段为 NBA Finals 后再回答。"
            ),
        }
    if coverage.get("complete") is False:
        return {
            "complete": False,
            "missing": list(coverage.get("missing") or ["requested_scope"]),
            "feedback": "工具结果尚未覆盖用户请求的范围，请继续选择合适的 NBA 数据工具补齐证据。",
        }
    return {"complete": True, "missing": [], "feedback": "已获得覆盖当前请求范围的工具证据。"}

