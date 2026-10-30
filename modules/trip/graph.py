"""出行｜图组装（这张图就是全部流程）

做什么：天气 → 景点(搜索循环) → 行程 → 路线，共四个节点加一个工具节点。
被谁用：modules/trip/stream.py 和 cli.py 调 build_graph()。
"""

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from modules.trip.node import (
    planner_node,
    route_agent_node,
    spots_agent_node,
    weather_node,
)
from modules.trip.tools import web_search
from modules.trip.route import should_continue
from modules.trip.state import AgentState

# 出行图结构：天气 → 景点（含搜索循环）→ 行程 → 路线

tools_node = ToolNode([web_search], handle_tool_errors=True)


def build_graph():
    """组装并编译出行图：天气 → 景点(搜) → 行程 → 路线。"""
    graph = StateGraph(AgentState)

    graph.add_node("weather", weather_node)
    graph.add_node("spots_agent", spots_agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("planner", planner_node)
    graph.add_node("route_agent", route_agent_node)

    graph.add_edge(START, "weather")
    graph.add_edge("weather", "spots_agent")
    graph.add_conditional_edges("spots_agent", should_continue)
    graph.add_edge("tools", "spots_agent")
    graph.add_edge("planner", "route_agent")
    graph.add_edge("route_agent", END)

    return graph.compile()
