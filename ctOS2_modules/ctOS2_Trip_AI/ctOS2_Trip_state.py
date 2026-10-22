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
