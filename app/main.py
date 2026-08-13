from pathlib import Path
import asyncio
import json
import os
import uuid

from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.native_agent import graph
from app.tools.schedule import lookup_game_time_data
from app.auth import authenticate, create_session, create_user, delete_session, init_auth_db, user_from_session


BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
app = FastAPI(title="NBA Chat", version="1.0.0")
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")
SERVER_INSTANCE_ID = uuid.uuid4().hex
init_auth_db()


@app.middleware("http")
async def utf8_json_response(request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json") and "charset=" not in content_type.lower():
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    thread_id: str = Field(default="", max_length=255)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    password: str = Field(min_length=6, max_length=128)


def require_user(session: str | None) -> dict[str, object]:
    user = user_from_session(session)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def _chunk_text(chunk: object) -> str:
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return ""


def _stream_event(event_type: str, **payload: object) -> str:
    return json.dumps(
        {"type": event_type, **payload},
        ensure_ascii=False,
        default=str,
    ) + "\n"


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "agent_ready": graph is not None,
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING", "false").lower() == "true",
        "langsmith_project": os.getenv("LANGSMITH_PROJECT", "default"),
        "server_instance_id": SERVER_INSTANCE_ID,
    }


@app.post("/api/auth/register")
async def register(credentials: Credentials, response: Response):
    raise HTTPException(status_code=403, detail="Demo 环境暂不开放注册")


@app.post("/api/auth/login")
async def login(credentials: Credentials, response: Response):
    user_id = await asyncio.to_thread(authenticate, credentials.username, credentials.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = await asyncio.to_thread(create_session, user_id)
    response.set_cookie("nba_session", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return {"id": user_id, "username": credentials.username}


@app.get("/api/auth/me")
async def me(nba_session: str | None = Cookie(default=None)):
    return require_user(nba_session)


@app.post("/api/auth/logout")
async def logout(response: Response, nba_session: str | None = Cookie(default=None)):
    await asyncio.to_thread(delete_session, nba_session)
    response.delete_cookie("nba_session")
    return {"ok": True}


@app.get("/api/debug/game-time/{game_id}")
async def debug_game_time(game_id: str):
    result = await asyncio.to_thread(lookup_game_time_data.invoke, game_id)
    try:
        return json.loads(result)
    except ValueError:
        return {"source": "nba_api", "game_id": game_id, "raw": result}


@app.post("/api/chat")
async def chat(payload: ChatRequest, nba_session: str | None = Cookie(default=None)):
    user = require_user(nba_session)
    if graph is None:
        raise HTTPException(status_code=503, detail="DASHSCOPE_API_KEY 未配置")
    # Older browser tabs may submit before the client has initialized a
    # thread ID. Keep the API resilient and start a fresh conversation.
    thread_id = payload.thread_id.strip() or uuid.uuid4().hex

    async def stream_response():
        final_result = {}
        streamed_text = ""
        try:
            async for event in graph.astream_events(
                {"messages": [HumanMessage(content=payload.message.strip())]},
                version="v2",
                config={
                    # LangGraph super-step safety limit. This is separate
                    # from the per-request ReAct budget in native_agent.py.
                    "recursion_limit": max(24, int(os.getenv("LANGGRAPH_RECURSION_LIMIT", "40"))),
                    "configurable": {"thread_id": f"user-{user['id']}:{thread_id}"},
                    "tags": ["nba-chat", "web-chat"],
                    "metadata": {
                        "thread_id": thread_id,
                        "user_id": user["id"],
                        "input_length": len(payload.message.strip()),
                    },
                },
            ):
                if event.get("event") == "on_chat_model_stream":
                    text = _chunk_text(event.get("data", {}).get("chunk"))
                    if text:
                        streamed_text += text
                        yield _stream_event("token", content=text)
                output = event.get("data", {}).get("output")
                if isinstance(output, dict) and output.get("messages"):
                    final_result = output

            messages = final_result.get("messages") or []
            answer = _chunk_text(messages[-1]) if messages else streamed_text
            yield _stream_event(
                "metadata",
                thread_id=thread_id,
                intent=str(final_result.get("intent") or "general"),
                resolved_query=str(final_result.get("resolved_query") or ""),
                analysis_level=str(final_result.get("analysis_level") or "none"),
                web_search_used=bool(final_result.get("web_search_used")),
                game_data_used=bool(final_result.get("game_data_used")),
                nba_api_game_used=bool(final_result.get("nba_api_game_used")),
                player_data_used=bool(final_result.get("player_data_used")),
                game_time_used=bool(final_result.get("game_time_used")),
                play_by_play_used=bool(final_result.get("play_by_play_used")),
                router_used=bool(final_result.get("router_used")),
                deep_analysis_used=bool(final_result.get("needs_deep_analysis")),
                retrieval_game_id=str(final_result.get("retrieval_game_id") or ""),
                cache_hit=bool(final_result.get("cache_hit")),
                answer=answer,
            )
            yield _stream_event("done")
        except Exception as exc:
            yield _stream_event("error", message=f"Agent 调用失败：{exc}")

    return StreamingResponse(
        stream_response(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/{path:path}")
async def frontend(path: str):
    candidate = (WEB_DIR / path).resolve()
    if path and candidate.is_relative_to(WEB_DIR) and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(WEB_DIR / "index.html")
