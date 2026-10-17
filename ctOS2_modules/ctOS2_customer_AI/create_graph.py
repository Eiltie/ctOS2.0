"""组装智能客服的图。

这一版是最小可跑的完整流程，一条直线，没有分支也没有循环：

    START → retrieve → generate → END

retrieve：三层检索（关键词 → 向量 → 混合）
generate：根据混合检索到的资料生成回答
"""

import sys
from pathlib import Path

# 直接运行本文件时项目根目录不在搜索路径里，先补一次（被 import 时重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.graph import END, START, StateGraph

from ctOS2_modules.ctOS2_customer_AI.agent_node import generate_node, retrieve_node
from ctOS2_modules.ctOS2_customer_AI.agent_state import AgentState

# 进图时的初始状态：所有字段都要给个空值，图才知道从哪儿开始
INITIAL_STATE = {
    "user_query": "",
    "keyword_hits": [],
    "vector_hits": [],
    "hybrid_hits": [],
    "answer": "",
}


def build_graph():
    """组装并编译客服图。"""
    graph = StateGraph(AgentState)

    # 挂两个节点
    graph.add_node("retrieve", retrieve_node)    # 三层检索
    graph.add_node("generate", generate_node)    # 生成回答

    # 连边：一条直线走到底
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


if __name__ == "__main__":
    # 打印图结构（Mermaid 文本，方便直观确认连线对不对）
    print(build_graph().get_graph().draw_mermaid())
