"""生图｜那张图

做什么：START → plan →（ask 或 generate）→ END

三条边：
  plan ──条件边──┬→ status=need_more 且没问过 → ask
                 └→ 其他                     → generate
  ask  ──→ plan        （用户回答后带答案重跑判断）
  generate → END

为什么 ask 回的是 plan 不是 generate：
  用户回答「一只猫」之后，还需要模型把这句话补成完整规格
  （风格、比例、光线）。回 plan 让规格处理只有一处，不写第二套解析。

为什么带检查点：
  ask 用的是 interrupt，必须能暂停后恢复。
  和路线决策共用 core.checkpoints 的那个 saver，靠线程号前缀区分。
"""

from langgraph.graph import END, START, StateGraph

from core.checkpoints import get_checkpointer
from modules.imagegen.node import ask_node, generate_node, plan_node
from modules.imagegen.state import STATUS_NEED_MORE, ImageState


def route_after_plan(state) -> str:
    """判断完之后去哪：问用户，还是直接画。

    只有「信息不足」并且「还没问过」才停下来问。
    问过一次还不足，就直接进 generate（那边会用随机主题兜底），
    否则用户回一句「随便」又会回到 plan，来回卡死。
    """
    if state.get("status") == STATUS_NEED_MORE and not state.get("asked_once"):
        return "ask"
    return "generate"


def build_graph(checkpointer):
    """组装生图图。"""
    graph = StateGraph(ImageState)

    graph.add_node("plan", plan_node)
    graph.add_node("ask", ask_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", route_after_plan, {
        "ask": "ask",
        "generate": "generate",
    })
    graph.add_edge("ask", "plan")
    graph.add_edge("generate", END)

    return graph.compile(checkpointer=checkpointer)


# 全进程共用一个 saver（和出行那边同一份文件，靠线程号区分）
image_checkpointer = get_checkpointer()
image_graph = build_graph(image_checkpointer)
