"""客服｜图的状态定义

做什么：声明检索的三份结果（keyword / vector / hybrid）和最终 answer。
被谁用：modules/customer/graph.py 和 node.py。
"""

from typing import TypedDict

# 客服图的状态：问题进、三层检索结果和最终回答出
#
# history 是最近几轮的对话，前端每轮带上来。
# 它只用来让模型理解「那它怎么配」这种依赖上文的追问，
# 不参与检索（检索只用当前这一句 question）。


class AgentState(TypedDict):
    user_query: str
    history: list[dict]

    keyword_hits: list[str]
    vector_hits: list[str]
    hybrid_hits: list[str]

    answer: str
