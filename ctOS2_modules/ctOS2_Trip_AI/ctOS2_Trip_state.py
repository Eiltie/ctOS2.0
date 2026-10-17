import operator
from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """全图共享状态：节点从上游字段读数据，往自己的产出字段写数据。"""

    #输入区
    user_query: str      
    destination: str    
    days: int            
    start_date: str     

    #天气 Agent 产出
    weather: str  

    #景点 Agent 产出
    messages: Annotated[list, add_messages]
    spots: str

    #规划 Agent 产出
    itinerary: str

    #路线 Agent 产出
    route_plan: str

    # 执行轨迹（附带产出，可选）
    node_path: Annotated[NotRequired[list[str]], operator.add]
