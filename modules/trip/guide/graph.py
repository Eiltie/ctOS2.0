"""旅游攻略｜图组装（这张图就是攻略的全部流程）

做什么：天气 → 景点(搜索循环) → 暂停等用户勾选 → 行程 → 游玩建议。
被谁用：modules/guide/stream.py 和 modules/trip/cli.py。
注意：这张图带检查点，因为要在景点清单处暂停；线程号在 stream.py 里生成。

和拆分前的区别：
  末节点从 route_agent（用高德查逐日路线）换成 advice（写游玩建议）。
  攻略从此不依赖地图，需要精确路线时交给路线规划模块。
"""

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from common.checkpoints import get_checkpointer
from common.tools.search import web_search
from modules.trip.guide.ask import ask_spots_node
from modules.trip.guide.conditions import should_continue
from modules.trip.guide.node import advice_node, planner_node, spots_agent_node, weather_node
from modules.trip.guide.state import GuideState

# 景点搜索用的工具节点
tools_node = ToolNode([web_search], handle_tool_errors=True)


def build_graph(checkpointer=None):
    """组装并编译攻略图：天气 → 景点(搜) → 选景点 → 行程 → 建议。

    不传 checkpointer 就用全进程共用的那个（common.checkpoints）。
    """
    graph = StateGraph(GuideState)

    graph.add_node("weather", weather_node)
    graph.add_node("spots_agent", spots_agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("ask_spots", ask_spots_node)
    graph.add_node("planner", planner_node)
    graph.add_node("advice", advice_node)

    graph.add_edge(START, "weather")
    graph.add_edge("weather", "spots_agent")
    graph.add_conditional_edges("spots_agent", should_continue, {
        "tools": "tools",
        "planner": "ask_spots",
        END: END,
    })
    graph.add_edge("tools", "spots_agent")
    graph.add_edge("ask_spots", "planner")
    graph.add_edge("planner", "advice")
    graph.add_edge("advice", END)

    return graph.compile(checkpointer=checkpointer or get_checkpointer())
