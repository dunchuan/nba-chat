import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv


load_dotenv()


SYSTEM_PROMPT = """你是 Pocket Agent，一个简洁、可靠的中文 AI 助手。
优先使用中文回答，除非用户要求其他语言。回答应直接、清楚。
当用户询问某地当前时间时，调用时间工具，不要猜测。
"""


@tool
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """查询指定 IANA 时区的当前时间，例如 Asia/Shanghai 或 Europe/London。"""
    try:
        now = datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError:
        return f"未知时区：{timezone}。请使用 IANA 时区名称。"
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


TOOLS = [get_current_time]
checkpointer = InMemorySaver()


def build_graph():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None

    model = ChatOpenAI(
        model=os.getenv("MODEL_NAME", "qwen-plus"),
        api_key=api_key,
        base_url=os.getenv(
            "MODEL_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        temperature=0.3,
    ).bind_tools(TOOLS)

    async def call_model(state: MessagesState):
        response = await model.ainvoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [response]}

    workflow = StateGraph(MessagesState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(TOOLS))
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    return workflow.compile(checkpointer=checkpointer)


graph = build_graph()
