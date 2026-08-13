"""Domain-separated tool registry for the ReAct agent."""

from app.tools.game import list_cached_data, lookup_game_data, lookup_game_log_data
from app.tools.player import lookup_boxscore_data, lookup_player_career_stats, lookup_player_season_stats
from app.tools.play_by_play import lookup_play_by_play_data
from app.tools.schedule import lookup_game_time_data, lookup_series_data, lookup_standings
from app.tools.team import lookup_team_season_stats
from app.tools.web import search_web


def get_tool_registry() -> list[object]:
    """Return every tool available to the model; add new tools here."""
    return [
        list_cached_data,
        lookup_game_data,
        lookup_game_log_data,
        lookup_boxscore_data,
        lookup_play_by_play_data,
        lookup_game_time_data,
        lookup_series_data,
        lookup_standings,
        lookup_player_season_stats,
        lookup_player_career_stats,
        lookup_team_season_stats,
        search_web,
    ]
