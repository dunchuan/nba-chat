"""Historical game lookup and process-local cache tools."""

import json
import re

from langchain_core.tools import tool

from app.cache.manager import cache_get, cache_items, cache_set


def _summary(namespace: str, key: str, raw: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        payload = {}
    records = payload.get("matches") or payload.get("players") or payload.get("events") or []
    if not isinstance(records, list):
        records = []
    ids = []
    for item in records:
        if isinstance(item, dict):
            value = item.get("game_id") or item.get("gameId")
            if value is not None and str(value) not in ids:
                ids.append(str(value))
    direct = payload.get("game_id")
    if direct is not None and str(direct) not in ids:
        ids.insert(0, str(direct))
    if not ids and namespace in {"boxscore", "play-by-play", "game-time"}:
        ids = [key.split(":", 1)[0]]
    return {"namespace": namespace, "key": key, "data_type": namespace, "game_ids": ids, "query": payload.get("query", ""), "source": payload.get("source", "")}


@tool
def list_cached_data(query: str = "", data_type: str = "") -> str:
    """List cached labels, game IDs, and available data types."""
    query = (query or "").lower().strip()
    data_type = (data_type or "").lower().strip()
    records = []
    for item in cache_items(900):
        namespace = str(item["namespace"])
        summary = _summary(namespace, str(item["key"]), str(item["value"]))
        if data_type and data_type not in namespace:
            continue
        if query and query not in json.dumps(summary, ensure_ascii=False).lower():
            continue
        records.append(summary)
    return json.dumps({"source": "process_cache", "data_type": "cache_index", "records": records, "game_ids": sorted({x for item in records for x in item["game_ids"]}), "cache_hit": True, "ok": True}, ensure_ascii=False)


@tool
def lookup_game_data(query: str) -> str:
    """Find historical game dates, teams, scores, and results exclusively via NBA API."""
    return _lookup_game_log(query, "Playoffs" if ("finals" in query.lower() or "总决赛" in query) else "Regular Season")


def _lookup_game_log(query: str, season_type: str) -> str:
    query = (query or "").strip()
    match = re.search(r"(?:19|20)\d{2}", query)
    if not match:
        return json.dumps({"source": "nba_api", "query": query, "matches": [], "error": "missing_year"}, ensure_ascii=False)
    year = int(match.group(0))
    season = f"{year - 1}-{year % 100:02d}"
    cache_key = f"{season_type}:{season}:{query.lower()}"
    cached = cache_get("game-log", cache_key, 900)
    if cached:
        payload = json.loads(cached)
        payload["cache_hit"] = True
        return json.dumps(payload, ensure_ascii=False)
    try:
        from nba_api.stats.endpoints import leaguegamelog
        frame = leaguegamelog.LeagueGameLog(
            season=season,
            season_type_all_star=season_type,
            player_or_team_abbreviation="T",
            timeout=20,
        ).get_data_frames()[0]
        rows = frame.to_dict(orient="records") if frame is not None and not frame.empty else []
    except Exception as exc:
        return json.dumps({"source": "nba_api", "query": query, "season": season, "matches": [], "error": type(exc).__name__}, ensure_ascii=False)
    matches = []
    grouped = {}
    for row in rows:
        game_id = str(row.get("GAME_ID") or "")
        if not game_id:
            continue
        grouped.setdefault(game_id, []).append(row)
    for game_id, teams in grouped.items():
        if len(teams) < 2:
            continue
        home = next((row for row in teams if " vs. " in str(row.get("MATCHUP"))), teams[0])
        away = next((row for row in teams if row is not home), teams[1])
        matches.append({
            "game_date": home.get("GAME_DATE"),
            "season_type": season_type,
            "home_team": home.get("TEAM_NAME"),
            "home_team_id": home.get("TEAM_ID"),
            "home_score": home.get("PTS"),
            "home_result": home.get("WL"),
            "away_team": away.get("TEAM_NAME"),
            "away_team_id": away.get("TEAM_ID"),
            "away_score": away.get("PTS"),
            "away_result": away.get("WL"),
            "game_id": game_id,
        })
    finals_requested = any(token in query.lower() for token in ("nba finals", "finals", "总决赛", "总决"))
    result = json.dumps({
        "source": "nba_api", "query": query, "season": season, "season_type": season_type,
        "matches": matches,
        "coverage": {
            "scope": "full_playoffs" if finals_requested and season_type == "Playoffs" else "season",
            "complete": not (finals_requested and season_type == "Playoffs"),
            "missing": ["finals_series_scope"] if finals_requested and season_type == "Playoffs" else [],
        },
    }, ensure_ascii=False, default=str)
    cache_set("game-log", cache_key, result)
    for item in matches:
        cache_set("game", str(item["game_id"]), json.dumps({"source": "nba_api", "query": query, "matches": [item]}, ensure_ascii=False, default=str))
    return result


@tool
def lookup_game_log_data(query: str, season_type: str = "Playoffs") -> str:
    """Find NBA game logs for a season and competition type exclusively via NBA API."""
    return _lookup_game_log(query, season_type)
