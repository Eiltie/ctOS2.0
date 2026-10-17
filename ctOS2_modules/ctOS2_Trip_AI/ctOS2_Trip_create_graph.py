from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_agent_node import (
    planner_node,
    route_agent_node,
    spots_agent_node,
    weather_node,
)
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_agent_tools import web_search
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_route import should_continue
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_state import AgentState

# 工具节点没有自定义逻辑，直接复用现成的 ToolNode：把上一条 AI 消息里的 tool_calls 逐个执行，包成 ToolMessage。
# handle_tool_errors=True：工具抛异常时不炸图，把错误文本当结果还回去，让 LLM 自己决定要不要换个说法重试。
tools_node = ToolNode([web_search], handle_tool_errors=True)


def build_graph():
    """组装并编译出行助手流程图。"""
    graph = StateGraph(AgentState)

    #挂节点（名字随意起，但 api 那层的「节点名 → 前端段落」表要靠这些名字认人）
    graph.add_node("weather", weather_node)
    graph.add_node("spots_agent", spots_agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("planner", planner_node)
    graph.add_node("route_agent", route_agent_node)

    #连边：普通边写死走向，条件边看 state 现算
    graph.add_edge(START, "weather")            # 起点 → 天气
    graph.add_edge("weather", "spots_agent")    # 天气 → 景点
    graph.add_conditional_edges("spots_agent", should_continue)   # 景点 → 去搜 / 去排期
    graph.add_edge("tools", "spots_agent")      # 搜完回到景点，形成循环
    graph.add_edge("planner", "route_agent")    # 排完行程 → 细化路线
    graph.add_edge("route_agent", END)          # 路线出完 → 结束

    return graph.compile()
