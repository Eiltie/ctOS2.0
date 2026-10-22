from typing import TypedDict, Annotated
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages

# 闲聊图的状态：只装一条消息列表


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
