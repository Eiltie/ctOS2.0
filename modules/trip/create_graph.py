"""出行 Agent 的图：START → agent → END。

只有一个节点、没有条件边，和对话模块那张图同构。
「路由」体现在 agent 节点内部的三种结论上（自己答 / 路线 / 攻略），
由 agent.py 按结论分派到对应的子图。

等哪天需要 Agent 自己转圈（比如排完攻略接着去查路线，一个回合连调两个能力），
再改成多节点加回边。现在加只是空转。
"""

from langgraph.graph import END, START, StateGraph

from modules.trip.node import decide_node
from modules.trip.state import TripState


def build_agent_graph():
    """组装 Agent 图。不带检查点：它现在不暂停、也不需要跨轮恢复。"""
    graph = StateGraph(TripState)

    graph.add_node("agent", decide_node)

    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)

    return graph.compile()


agent_graph = build_agent_graph()
