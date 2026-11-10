"""出行｜攻略图组装（这张图就是攻略的全部流程）

做什么：天气 → 景点(搜索循环) → 暂停等用户勾选 → 行程 → 路线。
被谁用：modules/trip/stream.py 和 cli.py 调 build_graph()。
注意：这张图带检查点，因为要在景点清单处暂停；线程号在 stream.py 里生成。
"""

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from modules.trip.guide_ask import ask_spots_node
from modules.trip.node import (
    planner_node,
    route_agent_node,
    spots_agent_node,
    weather_node,
)
from modules.trip.route_decision_graph import guide_checkpointer
from modules.trip.tools import web_search
from modules.trip.route import should_continue
from modules.trip.state import AgentState

# 攻略图结构：天气 → 景点（含搜索循环）→ 等用户勾选 → 行程 → 路线

tools_node = ToolNode([web_search], handle_tool_errors=True)


def build_graph():
    """组装并编译攻略图：天气 → 景点(搜) → 选景点 → 行程 → 路线。"""
    graph = StateGraph(AgentState)

    graph.add_node("weather", weather_node)
    graph.add_node("spots_agent", spots_agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("ask_spots", ask_spots_node)
    graph.add_node("planner", planner_node)
    graph.add_node("route_agent", route_agent_node)

    graph.add_edge(START, "weather")
    graph.add_edge("weather", "spots_agent")
    graph.add_conditional_edges("spots_agent", should_continue, {
        "tools": "tools",
        "planner": "ask_spots",
        END: END,
    })
    graph.add_edge("tools", "spots_agent")
    graph.add_edge("ask_spots", "planner")
    graph.add_edge("planner", "route_agent")
    graph.add_edge("route_agent", END)

    return graph.compile(checkpointer=guide_checkpointer)
