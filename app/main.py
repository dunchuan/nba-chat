from pathlib import Path
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import socket
import sqlite3
import time
import uuid

import httpx
from fastapi import Cookie, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.native_agent import (
    agent_thread_id,
    build_native_tool_graph,
    create_async_sqlite_checkpointer,
    delete_agent_thread_state,
    delete_all_agent_thread_state,
)
from app.tools.schedule import lookup_game_time_data
from app.tools import get_tool_registry
from app.auth import (
    authenticate,
    append_message,
    create_session,
    create_user,
    delete_all_conversations,
    delete_conversation,
    get_conversation_messages,
    delete_session,
    init_auth_db,
    list_conversations,
    normalize_username,
    rename_conversation,
    user_from_session,
    username_for_user_id,
)


BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
graph = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Create the async checkpointer in FastAPI's serving event loop."""
    global graph
    init_auth_db()
    checkpointer = None
    if os.getenv("DASHSCOPE_API_KEY"):
        checkpointer = await create_async_sqlite_checkpointer()
        graph = build_native_tool_graph(get_tool_registry(), checkpointer)
    application.state.checkpointer = checkpointer
    try:
        yield
    finally:
        graph = None
        if checkpointer is not None:
            await checkpointer.conn.close()


app = FastAPI(title="NBA Chat", version="1.0.0", lifespan=lifespan)
# Uvicorn configures this logger at INFO level and sends it to container stdout.
# Reusing it ensures audit records appear in ``docker compose logs``.
logger = logging.getLogger("uvicorn.error")
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")
SERVER_INSTANCE_ID = uuid.uuid4().hex
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "true").strip().lower() == "true"
REGISTRATION_ENABLED = os.getenv("REGISTRATION_ENABLED", "true").strip().lower() == "true"
SESSION_MAX_AGE = max(3600, int(os.getenv("SESSION_MAX_AGE", str(7 * 24 * 3600))))
_active_chat_threads: set[tuple[str, str]] = set()


def _chat_lock_key(user_id: object, thread_id: str) -> tuple[str, str]:
    return str(user_id), thread_id


def _try_acquire_chat_slot(user_id: object, thread_id: str) -> bool:
    """Acquire a per-process slot for one user conversation."""
    key = _chat_lock_key(user_id, thread_id)
    if key in _active_chat_threads:
        return False
    _active_chat_threads.add(key)
    return True


def _release_chat_slot(user_id: object, thread_id: str) -> None:
    _active_chat_threads.discard(_chat_lock_key(user_id, thread_id))


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


class ConversationRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


def require_user(session: str | None) -> dict[str, object]:
    if not AUTH_REQUIRED:
        return {"id": "guest", "username": "guest"}
    user = user_from_session(session)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def _cookie_is_secure(request: Request) -> bool:
    configured = os.getenv("SESSION_COOKIE_SECURE", "auto").strip().lower()
    if configured in {"true", "1", "yes"}:
        return True
    if configured in {"false", "0", "no"}:
        return False
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    return forwarded_proto == "https" or request.url.scheme == "https"


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        "nba_session",
        token,
        httponly=True,
        secure=_cookie_is_secure(request),
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )


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


def _client_ip(request: Request) -> str:
    """Return the client IP supplied by a trusted proxy, or the direct peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _audit_log(event: str, **fields: object) -> None:
    """Emit one JSON log line so Docker logs can be searched reliably."""
    logger.info("%s", json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def _probe_host(host: str) -> dict[str, object]:
    result: dict[str, object] = {"host": host}
    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
        result["dns"] = {"ok": True, "addresses": addresses}
    except Exception as exc:
        result["dns"] = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
        return result

    started = time.perf_counter()
    try:
        with socket.create_connection((host, 443), timeout=10):
            result["tcp"] = {
                "ok": True,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
    except Exception as exc:
        result["tcp"] = {
            "ok": False,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": type(exc).__name__,
            "message": str(exc),
        }

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=True) as client:
            response = client.get(f"https://{host}/")
        result["https"] = {
            "ok": True,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "bytes": len(response.content),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        result["https"] = {
            "ok": False,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "error": type(exc).__name__,
            "message": str(exc),
        }
    return result


def _run_nba_connectivity_diagnostic(game_id: str) -> dict[str, object]:
    result: dict[str, object] = {
        "source": "nba_api",
        "game_id": game_id,
        "checks": [_probe_host("stats.nba.com"), _probe_host("cdn.nba.com")],
    }
    started = time.perf_counter()
    try:
        raw = lookup_game_time_data.invoke(game_id)
        try:
            result["nba_api"] = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            result["nba_api"] = {"raw": str(raw)}
    except Exception as exc:
        result["nba_api"] = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
    result["nba_api_elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return result


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "agent_ready": graph is not None,
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING", "false").lower() == "true",
        "langsmith_project": os.getenv("LANGSMITH_PROJECT", "default"),
        "auth_required": AUTH_REQUIRED,
        "registration_enabled": REGISTRATION_ENABLED,
        "server_instance_id": SERVER_INSTANCE_ID,
    }


@app.post("/api/auth/register")
async def register(credentials: Credentials, request: Request, response: Response):
    if not REGISTRATION_ENABLED:
        raise HTTPException(status_code=403, detail="当前环境暂未开放注册")
    username = normalize_username(credentials.username)
    try:
        user_id = await asyncio.to_thread(create_user, username, credentials.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该用户名已被使用") from exc
    token = await asyncio.to_thread(create_session, user_id, SESSION_MAX_AGE)
    _set_session_cookie(response, request, token)
    _audit_log("user_registered", client_ip=_client_ip(request), user_id=user_id, username=username)
    return {"id": user_id, "username": username}


@app.post("/api/auth/login")
async def login(credentials: Credentials, request: Request, response: Response):
    user_id = await asyncio.to_thread(authenticate, credentials.username, credentials.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = await asyncio.to_thread(create_session, user_id, SESSION_MAX_AGE)
    _set_session_cookie(response, request, token)
    username = await asyncio.to_thread(username_for_user_id, user_id)
    _audit_log("user_login", client_ip=_client_ip(request), user_id=user_id, username=username)
    return {"id": user_id, "username": username}


@app.get("/api/auth/me")
async def me(nba_session: str | None = Cookie(default=None)):
    return require_user(nba_session)


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response, nba_session: str | None = Cookie(default=None)):
    await asyncio.to_thread(delete_session, nba_session)
    response.delete_cookie("nba_session", path="/", secure=_cookie_is_secure(request), samesite="lax")
    return {"ok": True}


@app.get("/api/conversations")
async def conversations(nba_session: str | None = Cookie(default=None)):
    user = require_user(nba_session)
    return {"conversations": await asyncio.to_thread(list_conversations, int(user["id"]))}


@app.get("/api/conversations/{thread_id}")
async def conversation_messages(thread_id: str, nba_session: str | None = Cookie(default=None)):
    user = require_user(nba_session)
    try:
        messages = await asyncio.to_thread(get_conversation_messages, int(user["id"]), thread_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="对话不存在") from exc
    return {"thread_id": thread_id, "messages": messages}


@app.patch("/api/conversations/{thread_id}")
async def update_conversation(
    thread_id: str,
    payload: ConversationRenameRequest,
    nba_session: str | None = Cookie(default=None),
):
    user = require_user(nba_session)
    try:
        await asyncio.to_thread(rename_conversation, int(user["id"]), thread_id, payload.title)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=404 if isinstance(exc, LookupError) else 422, detail=str(exc)) from exc
    return {"ok": True}


@app.delete("/api/conversations/{thread_id}")
async def remove_conversation(thread_id: str, nba_session: str | None = Cookie(default=None)):
    user = require_user(nba_session)
    deleted = await asyncio.to_thread(delete_conversation, int(user["id"]), thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="对话不存在")
    await asyncio.to_thread(delete_agent_thread_state, int(user["id"]), thread_id)
    return {"ok": True}


@app.delete("/api/conversations")
async def remove_all_conversations(nba_session: str | None = Cookie(default=None)):
    user = require_user(nba_session)
    count = await asyncio.to_thread(delete_all_conversations, int(user["id"]))
    await asyncio.to_thread(delete_all_agent_thread_state, int(user["id"]))
    return {"ok": True, "deleted": count}


@app.get("/api/debug/game-time/{game_id}")
async def debug_game_time(game_id: str):
    result = await asyncio.to_thread(lookup_game_time_data.invoke, game_id)
    try:
        return json.loads(result)
    except ValueError:
        return {"source": "nba_api", "game_id": game_id, "raw": result}


@app.get("/api/debug/nba-connectivity")
async def debug_nba_connectivity(
    game_id: str = "0049900088",
    nba_session: str | None = Cookie(default=None),
):
    """Diagnose Render DNS, TCP, HTTPS, and the real NBA API call."""
    require_user(nba_session)
    return await asyncio.to_thread(_run_nba_connectivity_diagnostic, game_id)


@app.post("/api/chat")
async def chat(
    payload: ChatRequest,
    request: Request,
    nba_session: str | None = Cookie(default=None),
):
    user = require_user(nba_session)
    if graph is None:
        raise HTTPException(status_code=503, detail="DASHSCOPE_API_KEY 未配置")
    # Older browser tabs may submit before the client has initialized a
    # thread ID. Keep the API resilient and start a fresh conversation.
    thread_id = payload.thread_id.strip() or uuid.uuid4().hex
    message = payload.message.strip()
    if not _try_acquire_chat_slot(user["id"], thread_id):
        raise HTTPException(status_code=409, detail="conversation_busy")
    try:
        await asyncio.to_thread(append_message, int(user["id"]), thread_id, "user", message)
    except PermissionError as exc:
        _release_chat_slot(user["id"], thread_id)
        raise HTTPException(status_code=403, detail="无权访问该对话") from exc
    except Exception:
        _release_chat_slot(user["id"], thread_id)
        raise
    client_ip = _client_ip(request)
    started_at = time.perf_counter()
    audit_fields = {
        "client_ip": client_ip,
        "user_id": str(user["id"]),
        "username": str(user["username"]),
        "thread_id": thread_id,
    }
    _audit_log("chat_request", **audit_fields, message=message, input_length=len(message))

    async def stream_response():
        final_result = {}
        streamed_text = ""
        try:
            async for event in graph.astream_events(
                {"messages": [HumanMessage(content=message)]},
                version="v2",
                config={
                    # LangGraph super-step safety limit. This is separate
                    # from the per-request ReAct budget in native_agent.py.
                    "recursion_limit": max(24, int(os.getenv("LANGGRAPH_RECURSION_LIMIT", "40"))),
                    "configurable": {"thread_id": agent_thread_id(user["id"], thread_id)},
                    "tags": ["nba-chat", "web-chat"],
                    "metadata": {
                        "thread_id": thread_id,
                        "user_id": user["id"],
                        "input_length": len(message),
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
            if answer:
                await asyncio.to_thread(append_message, int(user["id"]), thread_id, "assistant", answer)
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
            _audit_log(
                "chat_completed",
                **audit_fields,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                intent=str(final_result.get("intent") or "general"),
                analysis_level=str(final_result.get("analysis_level") or "none"),
                retrieval_game_id=str(final_result.get("retrieval_game_id") or ""),
                cache_hit=bool(final_result.get("cache_hit")),
                nba_api_game_used=bool(final_result.get("nba_api_game_used")),
                player_data_used=bool(final_result.get("player_data_used")),
                game_time_used=bool(final_result.get("game_time_used")),
                play_by_play_used=bool(final_result.get("play_by_play_used")),
                web_search_used=bool(final_result.get("web_search_used")),
            )
            yield _stream_event("done")
        except Exception as exc:
            _audit_log(
                "chat_failed",
                **audit_fields,
                elapsed_seconds=round(time.perf_counter() - started_at, 3),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            yield _stream_event("error", message=f"Agent 调用失败：{exc}")

        finally:
            _release_chat_slot(user["id"], thread_id)

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
