"""Model-driven LangGraph Tool Calling agent.

This graph is intentionally small: the model plans and selects tools, while
the finalizer exposes compatibility fields expected by the existing API.
Safety, caching, and endpoint validation remain in the registered tools.
"""

import json
import os
import sqlite3
from typing import Any
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from app.renderers import render_boxscore_template
from app.state import AgentState
from app.tools.contracts import normalize_tool_result
from app.evidence import evaluate_tool_evidence

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CHECKPOINT_DB_PATH = Path(
    os.getenv("LANGGRAPH_CHECKPOINT_SQLITE_PATH", str(BASE_DIR / "data" / "langgraph_checkpoints.sqlite3"))
)


NATIVE_AGENT_INSTRUCTIONS = """
You are an NBA research agent. Understand the user's goal before acting.
Decompose complex requests into data tasks and choose the registered tools
yourself; do not follow a fixed API sequence.

Historical scores, schedules, rankings, player statistics, game times, and
play-by-play must come exclusively from NBA data tools. Never use search_web
for historical NBA facts, even if an NBA tool returns no data; report the
missing data instead. Never invent facts. For a series or multi-game
request, first resolve all relevant game IDs, then request only the missing
per-game data. Inspect each tool result and continue calling tools when the
evidence is incomplete. Reuse results already present in this conversation.
Play-by-play is high-volume: use it only for a possession, period, sequence,
final seconds, or a specific event. If the user's premise is wrong or data is
missing, explain that clearly instead of accepting the premise or guessing.
When a follow-up refers to an earlier or indirect game, use list_cached_data
first if the game ID is not already unambiguous in the conversation. Reuse
cached data when it answers the request; do not fetch the same payload again.
If a game-log result says its scope is full_playoffs for a Finals request,
call lookup_series_data to resolve the actual series before answering.

Use search_web only for current news, injuries, trades, interviews, or other
time-sensitive background. Answer in concise, professional Simplified Chinese. Do not mention internal
state fields, tool names, or implementation details to the user.
Choose the presentation format from the user's request and the observed data.
For structured statistics, Markdown tables are appropriate, but do not force a
single fixed schema. For multiple games, group the answer by game first and
then by team when useful. Select only fields supported by the tool result and
do not repeat raw JSON or unrelated records.
"""


NativeState = AgentState


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in value
        )
    return str(value or "")


def _payload(content: object, data_type: str = "") -> dict[str, Any]:
    return dict(normalize_tool_result(_text(content), data_type))


def _tool_names(messages: list[object]) -> list[str]:
    names: list[str] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                name = str(call.get("name") or "")
                if name:
                    names.append(name)
        elif isinstance(message, ToolMessage) and getattr(message, "name", None):
            names.append(str(message.name))
    return list(dict.fromkeys(names))


def _compatibility_fields(state: NativeState) -> dict[str, object]:
    messages = list(state.get("messages") or [])
    names = _tool_names(messages)
    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
    game_id = ""
    data_type = ""
    retrieval_ok = bool(tool_messages)
    for message in tool_messages:
        payload = _payload(message.content, str(getattr(message, "name", "")))
        game_id = game_id or str(payload.get("game_id") or "")
        game_id = game_id or next(iter(payload.get("game_ids") or []), "")
        matches = payload.get("matches") or []
        if not game_id and matches and isinstance(matches[0], dict):
            game_id = str(matches[0].get("game_id") or "")
        if not payload.get("ok", False):
            retrieval_ok = False
        if getattr(message, "name", ""):
            data_type = data_type or str(message.name)

    game_tools = {"lookup_game_data", "lookup_game_log_data"}
    player_tools = {"lookup_boxscore_data", "lookup_player_season_stats", "lookup_player_career_stats"}
    return {
        "intent": "analysis" if len(names) > 1 else "historical_game" if game_tools.intersection(names) else "general",
        "resolved_query": next((
            _text(message.content) for message in reversed(messages)
            if getattr(message, "type", "") == "human"
        ), ""),
        "analysis_level": "deep" if len(names) > 1 else "none",
        "retrieval_ok": retrieval_ok and state.get("evidence_complete", True),
        "evidence_complete": state.get("evidence_complete", True),
        "evidence_missing": list(state.get("evidence_missing") or []),
        "evidence_feedback": str(state.get("evidence_feedback") or ""),
        "retrieval_game_id": game_id,
        "retrieval_data_type": data_type,
        "game_data_used": bool(game_tools.intersection(names)),
        "nba_api_game_used": bool(game_tools.intersection(names) or player_tools.intersection(names)),
        "player_data_used": bool(player_tools.intersection(names)),
        "game_time_used": "lookup_game_time_data" in names,
        "play_by_play_used": "lookup_play_by_play_data" in names,
        "web_search_used": "search_web" in names,
        # Tool payloads carry cache metadata so the UI and LangSmith can tell
        # whether this turn reused a previous result.
        "cache_hit": any(
            bool(_payload(message.content, str(getattr(message, "name", ""))).get("cache_hit"))
            for message in tool_messages
        ),
    }


async def create_async_sqlite_checkpointer() -> AsyncSqliteSaver:
    """Create the durable checkpointer used by all web conversations."""
    CHECKPOINT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = await aiosqlite.connect(CHECKPOINT_DB_PATH)
    await connection.execute("PRAGMA busy_timeout = 5000")
    checkpointer = AsyncSqliteSaver(connection)
    await checkpointer.setup()
    return checkpointer


def agent_thread_id(user_id: int | str, conversation_thread_id: str) -> str:
    """Namespace a browser conversation ID so checkpoint state is user-isolated."""
    return f"user-{user_id}:{conversation_thread_id}"


def delete_agent_thread_state(user_id: int | str, conversation_thread_id: str) -> None:
    """Delete durable LangGraph state for one user-owned conversation."""
    if not CHECKPOINT_DB_PATH.exists():
        return
    thread_id = agent_thread_id(user_id, conversation_thread_id)
    with sqlite3.connect(CHECKPOINT_DB_PATH) as connection:
        connection.execute("PRAGMA busy_timeout = 5000")
        # These tables are the public SQLite checkpointer schema created by
        # SqliteSaver.setup(). Delete writes first for compatibility with
        # SQLite foreign-key configurations.
        connection.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
        connection.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))


def delete_all_agent_thread_state(user_id: int | str) -> None:
    """Delete durable LangGraph state for every conversation owned by a user."""
    if not CHECKPOINT_DB_PATH.exists():
        return
    prefix = f"user-{user_id}:%"
    with sqlite3.connect(CHECKPOINT_DB_PATH) as connection:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("DELETE FROM writes WHERE thread_id LIKE ?", (prefix,))
        connection.execute("DELETE FROM checkpoints WHERE thread_id LIKE ?", (prefix,))


def build_native_tool_graph(tools, checkpointer: AsyncSqliteSaver):
    max_steps = max(2, int(os.getenv("REACT_MAX_STEPS", "12")))
    model = ChatOpenAI(
        model=os.getenv("MODEL_NAME", "qwen3.6-flash"),
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv(
            "MODEL_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        temperature=0.2,
        max_completion_tokens=int(os.getenv("NATIVE_MAX_COMPLETION_TOKENS", "6000")),
        extra_body={"enable_thinking": False},
    ).bind_tools(tools)

    def start_turn_node(state: NativeState):
        """Reset per-request controls while retaining conversation messages."""
        return {
            "react_steps": 0,
            "evidence_complete": True,
            "evidence_feedback": "",
            "evidence_missing": [],
        }

    async def agent_node(state: NativeState):
        step = int(state.get("react_steps", 0)) + 1
        if step > max_steps:
            return {
                "react_steps": step,
                "messages": [
                    AIMessage(
                        content=(
                            "已达到本次检索的最大执行步数。请基于目前已核实的数据回答；"
                            "如果数据不足，请明确说明缺少的信息。"
                        )
                    )
                ],
            }
        response_chunks = []
        feedback = str(state.get("evidence_feedback") or "")
        prompt = NATIVE_AGENT_INSTRUCTIONS
        if feedback:
            prompt += f"\nEvidence check from the previous observation: {feedback}\n"
        async for chunk in model.astream(
            [
                SystemMessage(content=prompt),
                *list(state.get("messages") or [])[-16:],
            ]
        ):
            response_chunks.append(chunk)
        response = response_chunks[0] if response_chunks else AIMessage(content="")
        for chunk in response_chunks[1:]:
            response = response + chunk
        return {"messages": [response], "react_steps": step}

    def evidence_node(state: NativeState):
        query = next((_text(message.content) for message in reversed(list(state.get("messages") or [])) if getattr(message, "type", "") == "human"), "")
        payloads = [_payload(message.content, str(getattr(message, "name", ""))) for message in state.get("messages") or [] if isinstance(message, ToolMessage)]
        result = evaluate_tool_evidence(query, payloads)
        return {"evidence_complete": bool(result["complete"]), "evidence_feedback": str(result["feedback"]), "evidence_missing": list(result["missing"])}

    def evidence_guard(state: NativeState):
        return {}

    def route_after_guard(state: NativeState):
        if state.get("evidence_complete", True) or int(state.get("react_steps", 0)) >= max_steps:
            return "finalize"
        return "agent"

    def finalize_node(state: NativeState):
        result = _compatibility_fields(state)
        # ReAct owns presentation decisions. Do not replace the model's final
        # answer with a single-game renderer, which would discard earlier
        # observations in multi-game requests.
        result["template_rendered"] = False
        result["presentation_mode"] = "model_selected"
        boxscore_template = render_boxscore_template(list(state.get("messages") or []))
        if boxscore_template:
            result["messages"] = [AIMessage(content=boxscore_template)]
            result["template_rendered"] = True
            result["presentation_mode"] = "boxscore_template"
        if state.get("evidence_complete") is False and any(isinstance(message, ToolMessage) for message in state.get("messages") or []):
            result["messages"] = [AIMessage(content="当前 NBA 数据工具返回的范围不足，暂时无法可靠核实问题。请补充更具体的系列赛或场次。")]
            result["template_rendered"] = False
            result["presentation_mode"] = "evidence_fallback"
        return result

    workflow = StateGraph(NativeState)
    workflow.add_node("start_turn", start_turn_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("evidence", evidence_node)
    workflow.add_node("evidence_guard", evidence_guard)
    workflow.add_node("finalize", finalize_node)
    workflow.add_edge(START, "start_turn")
    workflow.add_edge("start_turn", "agent")
    workflow.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", END: "evidence_guard"},
    )
    workflow.add_edge("tools", "evidence")
    workflow.add_edge("evidence", "agent")
    workflow.add_conditional_edges("evidence_guard", route_after_guard, {"agent": "agent", "finalize": "finalize"})
    workflow.add_edge("finalize", END)
    return workflow.compile(checkpointer=checkpointer)


# FastAPI creates the graph in its lifespan, so AsyncSqliteSaver is bound to
# the same event loop that later runs ``astream_events``.
graph = None
