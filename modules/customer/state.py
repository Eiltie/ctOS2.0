"""客服｜图的状态定义

做什么：声明改写结果、检索结果和最终回答。
被谁用：modules/customer/graph.py 和 node.py。

关于 search_query 和 in_scope：
  用户说的是「那它怎么配」「这东西能帮我干什么」这种省略主语的句子，
  直接拿去检索，关键词层基本搜不到东西（实测命中@1 只有 40%）。
  rewrite 节点先用历史把它补成一句自包含的话（search_query），
  顺便判断这个问题是不是在问 ctOS 本身（in_scope），不在库内就不检索、直接拒答。
"""

from typing import TypedDict


class AgentState(TypedDict):
    # 进图时前端给的
    user_query: str
    history: list[dict]

    # rewrite 节点填的
    search_query: str
    in_scope: bool
    not_found: bool

    # retrieve 节点填的：带标题路径和分数的检索结果
    hits: list[dict]

    # generate 节点填的
    answer: str
