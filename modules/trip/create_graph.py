"""智能出行｜那张图

做什么：START → agent → END。
被谁用：modules/trip/agent.py 调它拿判断结果。

为什么只有一个节点、没有条件边：
  一句话进来，办一件事就走——和闲聊模块那张图（START → chat_node → END）同构。
  "路由"现在表现为 agent 节点内部的三种结论（自己答 / 路线 / 攻略），
  由 agent.py 按结论分派出去。

什么时候该改成真正的条件边 + 循环：
  Agent 要"自己转圈"时——比如攻略排完，它觉得该接着查路线，
  同一个回合里连调两个能力。那时候才需要多节点和回边，
  现在加了只是空转。
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
