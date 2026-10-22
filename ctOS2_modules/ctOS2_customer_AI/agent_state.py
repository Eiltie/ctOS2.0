from typing import TypedDict

# 客服图的状态：问题进、三层检索结果和最终回答出


class AgentState(TypedDict):
    user_query: str

    keyword_hits: list[str]
    vector_hits: list[str]
    hybrid_hits: list[str]

    answer: str
