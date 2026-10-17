"""智能客服图的状态。

全图共享这一份状态：节点从上游字段读数据，把自己的产出写回对应字段。
"""

from typing import TypedDict


class AgentState(TypedDict):
    """一张图从头到尾流动的数据。"""

    # ==================== 输入区 ====================
    user_query: str                 # 用户这一轮的问题（原话，不做任何加工）

    # ==================== 检索区（retrieve 节点产出）====================
    keyword_hits: list[str]         # 第一层·关键词检索命中的文本片段
    vector_hits: list[str]          # 第二层·向量检索命中的文本片段
    hybrid_hits: list[str]          # 第三层·混合检索的最终片段（交给 LLM 的就是它）

    # ==================== 输出区（generate 节点产出）====================
    answer: str                     # 最终回答；检索不到时是「没找到答案」那句话
