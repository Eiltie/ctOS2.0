"""出行｜图的状态定义

做什么：声明目的地/天数/日期 + 四段产出（weather/spots/itinerary/route_plan）+ node_path。
被谁用：modules/trip/graph.py 和 node.py。
注意：加字段要同步改 stream.py 和 cli.py 里的 INITIAL_STATE，代码不会自动对齐。
"""

import operator
from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages

# 出行图的状态：各节点从上游字段读，往自己的产出字段写


class AgentState(TypedDict):
    user_query: str
    destination: str
    days: int
    start_date: str

    weather: str

    messages: Annotated[list, add_messages]
    spots: str

    itinerary: str

    route_plan: str

    node_path: Annotated[NotRequired[list[str]], operator.add]
