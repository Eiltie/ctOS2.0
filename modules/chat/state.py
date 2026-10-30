"""闲聊｜图的状态定义

做什么：声明图里只流转一个字段 messages（用 add_messages 累加，不是覆盖）。
被谁用：modules/chat/graph.py 和 node.py。
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

# 闲聊图的状态：只装一条消息列表


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
