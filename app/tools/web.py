"""Tavily web search tool."""
import json
import os
import httpx
from langchain_core.tools import tool

@tool
async def search_web(query: str) -> str:
    """Search current NBA news, injuries, trades, interviews, and time-sensitive background; never use for historical scores or statistics."""
    key=os.getenv("TAVILY_API_KEY", "").strip()
    if not key: return json.dumps({"source":"tavily","results":[],"error":"missing_api_key"})
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response=await client.post("https://api.tavily.com/search", json={"api_key":key,"query":query,"search_depth":"basic","max_results":5})
            response.raise_for_status()
            return json.dumps({"source":"tavily",**response.json()}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"source":"tavily","results":[],"error":type(exc).__name__}, ensure_ascii=False)
