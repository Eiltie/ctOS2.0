"""旅游攻略｜图的状态定义

做什么：声明目的地/天数/日期 + 四段产出（weather / spots / itinerary / advice）。
被谁用：modules/guide/graph.py 和 modules/guide/node.py。
注意：加字段要同步改 modules/guide/stream.py 的初始状态，代码不会自动对齐。

和路线模块的区别：
  路线的状态里是起点、终点、候选方案；这里是玩什么、怎么排。
  两边不再共用同一个 TypedDict。
"""

import operator
from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages


class GuideState(TypedDict):
    # 进图之前就有的
    user_query: str
    # 之前几轮用户说过的话，用来接"改成5天""换成成都"这类补充
    history: NotRequired[list]
    # 恢复暂停时校验用，防止拿别人的暂停现场接着跑
    tenant_id: NotRequired[int]
    # 所属会话。拼在状态里，恢复时才知道存到哪个会话下（不用前端再传一次）
    chat_id: NotRequired[int]

    destination: str
    days: int
    start_date: str

    weather: str

    messages: Annotated[list, add_messages]
    spots: str
    spot_names: NotRequired[list]

    # 用户在景点清单上做的调整，排行程时要用
    removed_spots: NotRequired[list]
    added_spot: NotRequired[str]

    itinerary: str

    # 第四段：游玩建议（拆分前这里是 route_plan，查逐日路线）
    advice: str

    node_path: Annotated[NotRequired[list[str]], operator.add]
