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
    "analysis", "analyze", "why", "compare", "comparison", "predict", "prediction",
    "advantage", "disadvantage", "chance", "performance",
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


def _player_display_name(row: dict[str, Any]) -> str:
    first = str(row.get("firstName") or row.get("FIRST_NAME") or "").strip()
    family = str(row.get("familyName") or row.get("lastName") or row.get("LAST_NAME") or "").strip()
    full_name = f"{first} {family}".strip()
    return full_name if full_name else str(_value(row, "name", "nameI", "playerName", "PLAYER_NAME"))


def _has_player_identity(row: dict[str, Any]) -> bool:
    """Exclude Stats API roster placeholders that have no player identity."""
    return _player_display_name(row).strip() not in {"", "-", "None"}


def _played_in_game(row: dict[str, Any]) -> bool:
    """A player-stat table contains only players with an official minutes value."""
    minutes = _value(row, "minutes", "MIN", "min")
    return str(minutes).strip() not in {"", "-", "None"}


def _shooting_value(row: dict[str, Any], made: str, attempted: str, percentage: str) -> str:
    made_value = _value(row, made)
    attempted_value = _value(row, attempted)
    if made_value == "-" or attempted_value == "-":
        return "-"
    percentage_value = row.get(percentage)
    if percentage_value in (None, ""):
        return f"{made_value}/{attempted_value}"
    try:
        numeric = float(percentage_value)
        display = numeric * 100 if 0 <= numeric <= 1 else numeric
        return f"{made_value}/{attempted_value} ({display:.1f}%)"
    except (TypeError, ValueError):
        return f"{made_value}/{attempted_value} ({percentage_value})"


def _percentage_value(row: dict[str, Any], *keys: str) -> str:
    """Format NBA API decimal percentages for their own Box Score column."""
    value = _value(row, *keys)
    if value == "-":
        return "-"
    try:
        numeric = float(value)
        numeric = numeric * 100 if 0 <= numeric <= 1 else numeric
        return f"{numeric:.1f}"
    except (TypeError, ValueError):
        return str(value)


def render_boxscore_template(messages: list[object]) -> str | None:
    """Render a stable, high-value table for a simple single-game player-stat request."""
    query = _human_query(messages).lower()
    if any(hint.lower() in query for hint in ANALYSIS_HINTS):
        return None

    for message in reversed(messages):
        if str(getattr(message, "name", "")) != "lookup_boxscore_data":
            continue
        payload = _payload(message)
        # BoxScoreTraditionalV3 can include blank roster slots and named DNP
        # entries with zeroed statistics. They do not belong in a player-stats
        # table; only players with an official MIN value are rendered.
        players = [
            row
            for row in payload.get("players") or []
            if isinstance(row, dict) and _has_player_identity(row) and _played_in_game(row)
        ]
        if not players:
            return None

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in players:
            team = str(_value(row, "teamTricode", "team", "TEAM_ABBREVIATION", "teamAbbreviation"))
            grouped.setdefault(team, []).append(row)

        # Put the values users compare first, then retain the complete shooting
        # split and secondary box-score fields for detailed inspection.
        fields = [
            "球员", "上场时间", "得分", "篮板", "助攻", "抢断", "盖帽", "正负值",
            "投篮命中", "投篮出手", "投篮命中率", "三分命中", "三分出手", "三分命中率",
            "罚球命中", "罚球出手", "罚球命中率", "前场篮板", "后场篮板", "失误", "犯规",
        ]
        sections: list[str] = []
        for team, rows in grouped.items():
            # The API response is the NBA official roster sequence.  Do not rank
            # players by PTS, MIN, +/- or alphabetical order for a box score.
            rows = sorted(
                enumerate(rows),
                key=lambda indexed_row: (
                    int(indexed_row[1].get("officialOrder", indexed_row[0]))
                    if str(indexed_row[1].get("officialOrder", indexed_row[0])).lstrip("-").isdigit()
                    else indexed_row[0]
                ),
            )
            rows = [row for _, row in rows]
            sample = rows[0]
            team_name = str(_value(sample, "teamName", "TEAM_NAME"))
            heading = team_name if team_name != "-" else team
            if team and team != "-" and team not in heading:
                heading = f"{heading} ({team})"
            lines = [
                f"### {heading}",
                "| " + " | ".join(fields) + " |",
                "|" + "---|" * len(fields),
            ]
            for row in rows:
                values = [
                    _player_display_name(row),
                    _value(row, "minutes", "MIN", "min"),
                    _value(row, "points", "pts", "PTS"),
                    _value(row, "reboundsTotal", "reb", "REB"),
                    _value(row, "assists", "ast", "AST"),
                    _value(row, "steals", "stl", "STL"),
                    _value(row, "blocks", "blk", "BLK"),
                    _value(row, "plusMinusPoints", "plusMinus", "PLUS_MINUS"),
                    _value(row, "fieldGoalsMade", "fgm", "FGM"),
                    _value(row, "fieldGoalsAttempted", "fga", "FGA"),
                    _percentage_value(row, "fieldGoalsPercentage", "fgPct", "FG_PCT"),
                    _value(row, "threePointersMade", "fg3m", "FG3M"),
                    _value(row, "threePointersAttempted", "fg3a", "FG3A"),
                    _percentage_value(row, "threePointersPercentage", "fg3Pct", "FG3_PCT"),
                    _value(row, "freeThrowsMade", "ftm", "FTM"),
                    _value(row, "freeThrowsAttempted", "fta", "FTA"),
                    _percentage_value(row, "freeThrowsPercentage", "ftPct", "FT_PCT"),
                    _value(row, "reboundsOffensive", "OREB"),
                    _value(row, "reboundsDefensive", "DREB"),
                    _value(row, "turnovers", "tov", "TOV"),
                    _value(row, "foulsPersonal", "pf", "PF"),
                ]
                lines.append("| " + " | ".join(str(value) for value in values) + " |")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)
    return None


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
