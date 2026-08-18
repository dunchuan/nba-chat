"""Schedule time and standings tools."""
import json
import re
from langchain_core.tools import tool
from app.nba_client import run_nba_api
from app.cache.manager import cache_get, cache_set
from app.tools.support import cached, dump, save, beijing_time


def _season_from_query(query: str) -> str:
    match = re.search(r"(?:19|20)\d{2}", query or "")
    if not match:
        return ""
    year = int(match.group(0))
    return f"{year - 1}-{year % 100:02d}"


@tool
def lookup_series_data(query: str) -> str:
    """Find a requested NBA series schedule and game IDs via ScheduleLeagueV2.

    This is the scope-resolution tool for requests such as an NBA Finals
    series.  It returns the API's series labels instead of assuming that the
    broad Playoffs season type means Finals.
    """
    query = (query or "").strip()
    season = _season_from_query(query)
    if not season:
        return json.dumps({"source": "nba_api", "data_type": "series_schedule", "records": [], "error": "missing_year"}, ensure_ascii=False)
    key = f"{season}:{query.lower()}"
    hit = cache_get("series-schedule", key, 900)
    if hit:
        payload = json.loads(hit)
        payload["cache_hit"] = True
        return json.dumps(payload, ensure_ascii=False, default=str)
    try:
        from nba_api.stats.endpoints import scheduleleaguev2
        frames = run_nba_api(
            lambda: scheduleleaguev2.ScheduleLeagueV2(season=season, timeout=20).get_data_frames()
        )
        records = []
        finals_requested = any(token in query.lower() for token in ("nba finals", "finals", "总决赛", "总决"))
        game_match = re.search(r"(?:g|game|第)\s*(\d+)", query.lower())
        wanted_game = int(game_match.group(1)) if game_match else None
        for frame in frames:
            if "gameId" not in frame.columns:
                continue
            for row in frame.to_dict(orient="records"):
                label = str(row.get("gameLabel") or "")
                sub_label = str(row.get("gameSubLabel") or row.get("seriesGameNumber") or "")
                if finals_requested and "final" not in label.lower():
                    continue
                if wanted_game is not None and not re.search(rf"\b{wanted_game}\b", sub_label):
                    continue
                records.append({
                    "game_id": str(row.get("gameId") or ""),
                    "game_date": row.get("gameDateEst") or row.get("gameDate"),
                    "game_label": label,
                    "game_sub_label": sub_label,
                    "series_game_number": row.get("seriesGameNumber"),
                    "series_text": row.get("seriesText"),
                    "home_team": row.get("homeTeam_teamName"),
                    "home_team_tricode": row.get("homeTeam_teamTricode"),
                    "home_score": row.get("homeTeam_score"),
                    "away_team": row.get("awayTeam_teamName"),
                    "away_team_tricode": row.get("awayTeam_teamTricode"),
                    "away_score": row.get("awayTeam_score"),
                    "gameDateTimeEst": row.get("gameDateTimeEst"),
                    "gameDateTimeUTC": row.get("gameDateTimeUTC"),
                })
        coverage_scope = "NBA Finals" if finals_requested else "schedule"
        payload = {
            "source": "nba_api", "data_type": "series_schedule", "query": query,
            "season": season, "records": records,
            "game_ids": [item["game_id"] for item in records if item.get("game_id")],
            "coverage": {"scope": coverage_scope, "complete": bool(records), "game_count": len(records)},
        }
        raw = json.dumps(payload, ensure_ascii=False, default=str)
        cache_set("series-schedule", key, raw)
        return raw
    except Exception as exc:
        return json.dumps({"source": "nba_api", "data_type": "series_schedule", "query": query, "season": season, "records": [], "error": type(exc).__name__}, ensure_ascii=False)

@tool
def lookup_game_time_data(game_id: str, season: str = "") -> str:
    """Get local, UTC, and Beijing-readable game time fields."""
    if not game_id:
        return json.dumps({"source":"nba_api","game_id":"","time":{},"error":"missing_game_id"})
    try:
        from nba_api.stats.endpoints import scheduleleaguev2
        if not season:
            yy = int(str(game_id)[3:5]); start = 1900 + yy if yy >= 50 else 2000 + yy
            season = f"{start}-{(start+1)%100:02d}"
        key = f"{season}:{game_id}"
        hit = cached("game-time", key)
        if hit:
            return hit
        frames = run_nba_api(
            lambda: scheduleleaguev2.ScheduleLeagueV2(season=season, timeout=20).get_data_frames()
        )
        for frame in frames:
            column = next((c for c in ("gameId", "GAME_ID") if c in frame.columns), None)
            if column:
                rows = frame[frame[column].astype(str) == str(game_id)].to_dict(orient="records")
                if rows:
                    row = rows[0]
                    keys = ("gameDateEst","gameTimeEst","gameDateTimeEst","gameDateUTC","gameTimeUTC","gameDateTimeUTC")
                    time_data = {k:row.get(k) for k in keys if row.get(k) not in (None, "")}
                    utc_value = time_data.get("gameDateTimeUTC")
                    time_data["gameDateTimeBeijing"] = beijing_time(utc_value)
                    return save("game-time", key, dump({"source":"nba_api","game_id":str(game_id),"time":time_data}))
        return save("game-time", key, dump({"source":"nba_api","game_id":str(game_id),"time":{},"error":"not_found"}))
    except Exception as exc:
        return dump({"source":"nba_api","game_id":str(game_id),"time":{},"error":type(exc).__name__})

@tool
def lookup_standings(year: int, season_type: str = "Regular Season") -> str:
    """Get team standings for an NBA season."""
    if not year:
        return json.dumps({"source":"nba_api","standings":[],"error":"missing_year"})
    season=f"{int(year)-1}-{int(year)%100:02d}"
    key=f"{season}:{season_type}"
    hit=cached("standings", key)
    if hit:
        return hit
    try:
        from nba_api.stats.endpoints import leaguestandingsv3
        frame = run_nba_api(
            lambda: leaguestandingsv3.LeagueStandingsV3(
                season=season, season_type=season_type, timeout=20
            ).get_data_frames()[0]
        )
        return save("standings", key, dump({"source":"nba_api","season":season,"standings":frame.to_dict(orient="records")}))
    except Exception as exc:
        return save("standings", key, dump({"source":"nba_api","season":season,"standings":[],"error":type(exc).__name__}))
