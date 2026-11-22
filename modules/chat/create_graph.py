"""闲聊｜图组装

做什么：把唯一的 chat_node 连成 START → chat_node → END 的直线图。
被谁用：modules/chat/stream.py 在 import 时调 create_graph()。
"""

from langgraph.graph import START, StateGraph, END
from modules.chat.node import ctOS_chat_node
from modules.chat.state import AgentState

# 对话图结构：START → chat_node → END


def create_graph():
    """组装并编译对话图：START → chat_node → END。"""
    graph = StateGraph(AgentState)

    graph.add_node("chat_node", ctOS_chat_node)
    graph.add_edge(START, "chat_node")
    graph.add_edge("chat_node", END)

    app = graph.compile()

    return app
