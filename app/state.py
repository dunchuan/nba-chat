"""Shared LangGraph state contract for all NBA agent implementations."""

from typing import Literal

from langgraph.graph import MessagesState


class AgentState(MessagesState, total=False):
    """Common state fields; nodes may update only the fields they need."""

    route: Literal["safety", "retrieve", "answer", "clarification"]
    intent: str
    needs_game_data: bool
    needs_web_data: bool
    needs_player_data: bool
    needs_deep_analysis: bool
    analysis_level: Literal["none", "light", "deep"]
    router_used: bool
    retrieval_context: str
    retrieval_ok: bool
    web_search_used: bool
    game_data_used: bool
    nba_api_game_used: bool
    player_data_used: bool
    game_time_used: bool
    play_by_play_used: bool
    conversation_context: dict[str, object]
    resolved_query: str
    parsed_query: dict[str, object]
    reuse_retrieval_context: bool
    retrieval_query: str
    retrieval_game_id: str
    retrieval_data_type: str
    cache_hit: bool
    data_requirements: list[str]
    premise_valid: bool | None
    premise_correction: str
    premise_evidence: str
    premise_user_team_ids: list[int]
    premise_actual_team_ids: list[int]
    awaiting_user_restatement: bool
    pending_user_query: str
    pending_intent: str
    pending_analysis_level: Literal["none", "light", "deep"]
    objective_data: dict[str, object]
    react_steps: int
    template_rendered: bool
    presentation_mode: str
    evidence_complete: bool
    evidence_feedback: str
    evidence_missing: list[str]
