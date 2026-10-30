"""客服｜图组装

做什么：把 retrieve → generate 连成一条直线，没有分支也没有循环。
被谁用：modules/customer/stream.py 在 import 时调 build_graph()。
"""

from langgraph.graph import END, START, StateGraph

from modules.customer.node import generate_node, retrieve_node
from modules.customer.state import AgentState

# 客服图结构：START → retrieve → generate → END

INITIAL_STATE = {
    "user_query": "",
    "history": [],
    "keyword_hits": [],
    "vector_hits": [],
    "hybrid_hits": [],
    "answer": "",
}


def build_graph():
    """组装并编译客服图：START → retrieve → generate → END。"""
    graph = StateGraph(AgentState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


if __name__ == "__main__":
    print(build_graph().get_graph().draw_mermaid())
