"""提示词 Agent｜图的状态

这张图只负责「需求 → 提示词」，不调生图接口、不存盘、不管尺寸。
"""

from typing import TypedDict


class AgentState(TypedDict):
    requirement: str    # 进来的生图需求
    images: list        # 图片块，直接拼进 HumanMessage
    prompt: str         # 写出来的提示词
    status: str         # ok / failed
    problem: str        # 失败原因
