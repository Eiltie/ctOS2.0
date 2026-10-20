from langgraph.graph import END

MAX_MESSAGES = 20       # 消息总数上限：正常流程碰不到，防工具反复失败时循环失控


def should_continue(state) -> str:
    """景点 Agent 这一轮还想不想调工具。"""
    messages = state["messages"]

    #消息太多说明循环失控
    if len(messages) >= MAX_MESSAGES:
        return END

    #最后一条还想调工具 → 去工具节点，回来接着搜
    #不想调了 → 清单已写好，交给规划节点
    return "tools" if messages[-1].tool_calls else "planner"
