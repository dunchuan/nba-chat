from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.agent import graph


BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"

app = FastAPI(title="Pocket Agent", version="1.0.0")
app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    thread_id: str = Field(min_length=1, max_length=255)


class ChatResponse(BaseModel):
    answer: str
    thread_id: str


@app.get("/api/health")
async def health():
    return {"status": "ok", "agent_ready": graph is not None}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if graph is None:
        raise HTTPException(
            status_code=503,
            detail="尚未配置 DASHSCOPE_API_KEY。请在部署平台的环境变量中添加阿里云百炼 API Key。",
        )

    try:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=payload.message.strip())]},
            config={"configurable": {"thread_id": payload.thread_id}},
        )
        answer = result["messages"][-1].content
        if isinstance(answer, list):
            answer = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in answer
            )
        return ChatResponse(answer=str(answer), thread_id=payload.thread_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent 调用失败：{exc}") from exc


@app.get("/{path:path}")
async def frontend(path: str):
    candidate = (WEB_DIR / path).resolve()
    if path and candidate.is_relative_to(WEB_DIR) and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(WEB_DIR / "index.html")
