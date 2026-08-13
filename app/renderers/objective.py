"""Render objective tool payloads without another model call."""

import json
import re
from typing import Any


OBJECTIVE_HINTS = (
    "比分", "赛果", "结果", "球员统计", "技术统计", "数据", "统计", "statistics", "stats", "time", "时间", "几点",
    "排名", "战绩", "play-by-play", "回合", "box score", "boxscore",
)
ANALYSIS_HINTS = (
    "分析", "为什么", "原因", "差距", "优势", "劣势", "比较", "对比", "预测",
    "机会", "表现如何", "赢点", "重要",
)


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in value)
    return str(value or "")


def _payload(message: object) -> dict[str, Any]:
    try:
        value = json.loads(_text(getattr(message, "content", message)))
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _human_query(messages: list[object]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            return _text(getattr(message, "content", ""))
    return ""


def is_objective_query(query: str) -> bool:
    text = query.lower()
    return bool(any(hint.lower() in text for hint in OBJECTIVE_HINTS)) and not any(
        hint.lower() in text for hint in ANALYSIS_HINTS
    )


def _value(row: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return "-"


def _game_table(payload: dict[str, Any]) -> str:
    matches = payload.get("matches") or []
    if not matches:
        return ""
    lines = ["| 日期 | 对阵 | 比分 | 赛果 |", "|---|---|---:|---|"]
    for row in matches:
        home = _value(row, "home_team")
        away = _value(row, "away_team")
        home_score = _value(row, "home_score")
        away_score = _value(row, "away_score")
        result = "主队胜" if str(row.get("home_result", "")).upper() == "W" else "客队胜"
        lines.append(f"| {_value(row, 'game_date')} | {home} vs {away} | {home_score} - {away_score} | {result} |")
    return "\n".join(lines)


def _player_table(payload: dict[str, Any]) -> str:
    players = payload.get("players") or []
    if not players:
        return ""
    fields = [
        ("球员", ("name", "nameI", "playerName", "PLAYER_NAME")),
        ("球队", ("teamTricode", "team", "TEAM_ABBREVIATION")),
        ("时间", ("minutes", "MIN")),
        ("得分", ("points", "pts", "PTS")),
        ("投篮", ("fieldGoalsMade", "fgm", "FGM")),
        ("三分", ("threePointersMade", "fg3m", "FG3M")),
        ("罚球", ("freeThrowsMade", "ftm", "FTM")),
        ("篮板", ("reboundsTotal", "reb", "REB")),
        ("助攻", ("assists", "ast", "AST")),
        ("抢断", ("steals", "stl", "STL")),
        ("盖帽", ("blocks", "blk", "BLK")),
        ("失误", ("turnovers", "tov", "TOV")),
    ]
    lines = ["| " + " | ".join(label for label, _ in fields) + " |", "|" + "---|" * len(fields)]
    for row in players:
        lines.append("| " + " | ".join(str(_value(row, *keys)) for _, keys in fields) + " |")
    return "\n".join(lines)


def _player_table(payload: dict[str, Any]) -> str:
    """Render box score players as one clean table per team."""
    players = payload.get("players") or []
    if not players:
        return ""
    fields = [
        ("球员", ("name", "nameI", "playerName", "PLAYER_NAME", "DISPLAY_FIRST_LAST")),
        ("时间", ("minutes", "MIN", "min")),
        ("得分", ("points", "pts", "PTS")),
        ("投篮", ("fieldGoalsMade", "fgm", "FGM")),
        ("三分", ("threePointersMade", "fg3m", "FG3M")),
        ("罚球", ("freeThrowsMade", "ftm", "FTM")),
        ("篮板", ("reboundsTotal", "reb", "REB")),
        ("助攻", ("assists", "ast", "AST")),
        ("抢断", ("steals", "stl", "STL")),
        ("盖帽", ("blocks", "blk", "BLK")),
        ("失误", ("turnovers", "tov", "TOV")),
        ("正负值", ("plusMinusPoints", "plusMinus", "PLUS_MINUS")),
    ]
    valid_players = []
    for row in players:
        if not isinstance(row, dict):
            continue
        name = _value(row, *fields[0][1])
        if name == "-":
            first = row.get("firstName") or row.get("FIRST_NAME") or ""
            last = row.get("familyName") or row.get("lastName") or row.get("LAST_NAME") or ""
            name = f"{first} {last}".strip() or "-"
            if name != "-":
                row = {**row, "name": name}
        if name not in ("-", "", None):
            valid_players.append(row)
    if not valid_players:
        return ""

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in valid_players:
        team = str(_value(row, "teamTricode", "team", "TEAM_ABBREVIATION", "teamAbbreviation"))
        groups.setdefault(team, []).append(row)

    sections = []
    for team, team_players in groups.items():
        team_name = str(_value(team_players[0], "teamName", "TEAM_NAME"))
        heading = team_name if team_name != "-" else team
        if team and team != "-" and team not in heading:
            heading = f"{heading} ({team})"
        lines = [
            f"### {heading}",
            "| " + " | ".join(label for label, _ in fields) + " |",
            "|" + "---|" * len(fields),
        ]
        for row in team_players:
            lines.append("| " + " | ".join(str(_value(row, *keys)) for _, keys in fields) + " |")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _time_table(payload: dict[str, Any]) -> str:
    data = payload.get("time") or {}
    if not data:
        return ""
    lines = ["| 时间类型 | 时间 |", "|---|---|"]
    labels = {
        "gameDateTimeEst": "美国东部时间",
        "gameDateTimeUTC": "UTC",
        "gameDateTimeBeijing": "北京时间",
    }
    for key, label in labels.items():
        if data.get(key):
            lines.append(f"| {label} | {data[key]} |")
    return "\n".join(lines)


def render_objective_response(messages: list[object]) -> str | None:
    """Return a Markdown template only for simple objective questions."""
    query = _human_query(messages)
    if not is_objective_query(query):
        return None
    tool_messages = [message for message in messages if getattr(message, "type", "") == "tool"]
    for message in reversed(tool_messages):
        payload = _payload(message)
        name = str(getattr(message, "name", ""))
        if name == "lookup_boxscore_data":
            table = _player_table(payload)
            if table:
                return table
        if name in {"lookup_game_data", "lookup_game_log_data"}:
            table = _game_table(payload)
            if table:
                return table
        if name == "lookup_game_time_data":
            table = _time_table(payload)
            if table:
                return table
    return None
