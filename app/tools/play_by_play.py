"""Play-by-play tool."""
import json
from langchain_core.tools import tool
from app.tools.support import cached, dump, save

@tool
def lookup_play_by_play_data(game_id: str, start_period: str = "0", end_period: str = "0") -> str:
    """Get ordered Play-by-Play events, optionally limited to periods."""
    game_id = str(game_id or "").strip()
    start_period = str(start_period or "0").strip()
    end_period = str(end_period or "0").strip()
    if not game_id:
        return json.dumps({"source":"nba_api","events":[],"error":"missing_game_id"})
    key = f"{game_id}:{start_period}:{end_period}"
    hit = cached("play-by-play", key)
    if hit:
        return hit
    try:
        from nba_api.stats.endpoints import playbyplayv3
        frame = playbyplayv3.PlayByPlayV3(game_id=str(game_id), timeout=20).get_data_frames()[0]
        events = frame.to_dict(orient="records") if frame is not None else []
        if start_period != "0":
            end = end_period if end_period != "0" else start_period
            events = [e for e in events if start_period <= str(e.get("period", "")) <= end]
        return save("play-by-play", key, dump({"source":"nba_api","game_id":str(game_id),"start_period":start_period,"end_period":end_period,"events":events}))
    except Exception as exc:
        return save("play-by-play", key, dump({"source":"nba_api","game_id":str(game_id),"events":[],"error":type(exc).__name__}))
