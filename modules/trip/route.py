"""出行｜攻略图里景点节点的条件路由

做什么：判断 spots_agent 跑完后是继续搜工具，还是交给用户勾选景点。
被谁用：modules/trip/graph.py 的 add_conditional_edges("spots_agent", should_continue)。
"""

from langgraph.graph import END

# 消息总数上限：正常流程碰不到，防工具反复失败时循环失控
MAX_MESSAGES = 20


def should_continue(state) -> str:
    """景点节点这一轮之后去哪：继续搜工具，还是停下来让用户过目。"""
    messages = state["messages"]

    if len(messages) >= MAX_MESSAGES:
        return END

    return "tools" if messages[-1].tool_calls else "planner"
