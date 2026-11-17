"""客服｜图组装

做什么：rewrite → retrieve → generate 一条线，外加「不在知识范围」的分支。
被谁用：modules/customer/stream.py 在 import 时调 build_graph()。
"""

from langgraph.graph import END, START, StateGraph

from modules.customer.node import (
    generate_node,
    greet_node,
    refuse_node,
    retrieve_node,
    rewrite_node,
    route_after_retrieve,
    route_start,
)
from modules.customer.state import AgentState

# 客服图结构：
#   START → rewrite ─┬─(寒暄)─────→ greet                → END
#                    └─(其余问句)─→ retrieve ─┬─(有资料)───→ generate → END
#                                             └─(没有资料)→ refuse   → END
#
# 为什么先改写再检索：
#   「那它怎么配」单独拿去检索是搜不到东西的，得先补成一句自包含的话。
#
# 为什么寒暄单独一个分支：
#   用户第一句常常就是「你好」，原样回「抱歉，我在知识库里没有找到相关答案」
#   太生硬，也看不出这个客服该问什么。寒暄回一句引导语，不检索、不调模型，几十毫秒就返回。
#
# 为什么拒答的判定放在检索之后：
#   改写节点会顺带判断「是不是在问 ctOS」，但模型对「像不像在问项目」
#   和「知识库里有没有」经常混在一起（「怎么用 Docker 部署」被误判成库外，
#   而文档里有整章部署）。所以让检索结果当第二道关，两边都不同意才拒答。

INITIAL_STATE = {
    "user_query": "",
    "history": [],
    "search_query": "",
    "in_scope": True,
    "not_found": False,
    "hits": [],
    "answer": "",
}


def build_graph():
    """组装并编译客服图。

    入口先用 route_start 分一次：寒暄直接进 greet，
    这样「你好」不经过改写节点、一次模型都不用调，几十毫秒就返回。
    寒暄也没有可检索的内容，改写它没有意义。
    """
    graph = StateGraph(AgentState)

    graph.add_node("rewrite", rewrite_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("refuse", refuse_node)
    graph.add_node("greet", greet_node)

    graph.add_conditional_edges(START, route_start, {
        "greet": "greet",
        "rewrite": "rewrite",
    })
    graph.add_edge("rewrite", "retrieve")
    graph.add_conditional_edges("retrieve", route_after_retrieve, {
        "generate": "generate",
        "refuse": "refuse",
    })
    graph.add_edge("generate", END)
    graph.add_edge("refuse", END)
    graph.add_edge("greet", END)

    return graph.compile()


if __name__ == "__main__":
    print(build_graph().get_graph().draw_mermaid())
