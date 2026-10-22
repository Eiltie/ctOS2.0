import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.graph import END, START, StateGraph

from ctOS2_modules.ctOS2_customer_AI.agent_node import generate_node, retrieve_node
from ctOS2_modules.ctOS2_customer_AI.agent_state import AgentState

# 客服图结构：START → retrieve → generate → END

INITIAL_STATE = {
    "user_query": "",
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
