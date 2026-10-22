from langgraph.graph import END

# 景点节点的条件路由：决定继续搜工具还是进规划
# 消息总数上限：正常流程碰不到，防工具反复失败时循环失控
MAX_MESSAGES = 20


def should_continue(state) -> str:
    """景点节点这一轮之后去哪：继续搜工具，还是交给规划。"""
    messages = state["messages"]

    if len(messages) >= MAX_MESSAGES:
        return END

    return "tools" if messages[-1].tool_calls else "planner"
