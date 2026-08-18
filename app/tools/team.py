"""Team season statistics tool."""
import json
from langchain_core.tools import tool
from app.nba_client import run_nba_api
from app.tools.support import cached, dump, save

@tool
def lookup_team_season_stats(year: int, team_id: int = 0, team_name: str = "", season_type: str = "Regular Season") -> str:
    """Get team season statistics."""
    if not year:
        return json.dumps({"source":"nba_api","teams":[],"error":"missing_year"})
    season=f"{int(year)-1}-{int(year)%100:02d}"
    key=f"{season}:{team_id}:{team_name.lower()}:{season_type}"
    hit=cached("team-season", key)
    if hit:
        return hit
    try:
        from nba_api.stats.endpoints import leaguedashteamstats
        frame = run_nba_api(
            lambda: leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                season_type_all_star=season_type,
                team_id_nullable=str(team_id) if team_id else "",
                timeout=20,
            ).get_data_frames()[0]
        )
        rows=frame.to_dict(orient="records") if frame is not None else []
        if team_name: rows=[row for row in rows if team_name.lower() in str(row).lower()]
        return save("team-season", key, dump({"source":"nba_api","season":season,"teams":rows}))
    except Exception as exc:
        return save("team-season", key, dump({"source":"nba_api","season":season,"teams":[],"error":type(exc).__name__}))
