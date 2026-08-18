"""Player and single-game box score tools."""
import json
from langchain_core.tools import tool
from app.nba_client import run_nba_api
from app.tools.support import cached, dump, save

def _json(source, **payload):
    return json.dumps({"source": source, **payload}, ensure_ascii=False, default=str)

@tool
def lookup_boxscore_data(game_id: str) -> str:
    """Get traditional player box score data for one game."""
    game_id = str(game_id or "").strip()
    if not game_id:
        return _json("nba_api", game_id="", players=[], error="missing_game_id")
    hit = cached("boxscore", game_id)
    if hit:
        return hit
    try:
        from nba_api.stats.endpoints import boxscoretraditionalv3
        frames = run_nba_api(
            lambda: boxscoretraditionalv3.BoxScoreTraditionalV3(
                game_id=str(game_id), timeout=20
            ).get_data_frames()
        )
        frame = frames[0] if frames else None
        return save("boxscore", game_id, _json("nba_api", game_id=str(game_id), players=frame.to_dict(orient="records") if frame is not None else []))
    except Exception as exc:
        return _json("nba_api", game_id=str(game_id), players=[], error=type(exc).__name__)

@tool
def lookup_player_season_stats(year: int, player_name: str = "", season_type: str = "Regular Season") -> str:
    """Get player season statistics."""
    if not year:
        return _json("nba_api", players=[], error="missing_year")
    season = f"{int(year)-1}-{int(year)%100:02d}"
    key = f"{season}:{season_type}:{player_name.lower()}"
    hit = cached("player-season", key)
    if hit:
        return hit
    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
        frame = run_nba_api(
            lambda: leaguedashplayerstats.LeagueDashPlayerStats(
                season=season, season_type_all_star=season_type, timeout=20
            ).get_data_frames()[0]
        )
        rows = frame.to_dict(orient="records") if frame is not None else []
        if player_name:
            rows = [row for row in rows if player_name.lower() in str(row).lower()]
        return save("player-season", key, _json("nba_api", season=season, players=rows))
    except Exception as exc:
        return _json("nba_api", season=season, players=[], error=type(exc).__name__)

@tool
def lookup_player_career_stats(player_id: int = 0, player_name: str = "") -> str:
    """Get a player's career statistics."""
    if not player_id:
        return _json("nba_api", player_name=player_name, players=[], error="missing_player")
    key = str(player_id)
    hit = cached("player-career", key)
    if hit:
        return hit
    try:
        from nba_api.stats.endpoints import playercareerstats
        frames = run_nba_api(
            lambda: playercareerstats.PlayerCareerStats(
                player_id=int(player_id), timeout=20
            ).get_data_frames()
        )
        return save("player-career", key, _json("nba_api", player_id=int(player_id), players=frames[0].to_dict(orient="records") if frames else []))
    except Exception as exc:
        return _json("nba_api", player_id=int(player_id), players=[], error=type(exc).__name__)
