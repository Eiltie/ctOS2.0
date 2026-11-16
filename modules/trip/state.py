"""智能出行｜Agent 的状态

做什么：这一圈对话的上下文，只有 messages。
被谁用：modules/trip/graph.py 和 modules/trip/node.py。

为什么只有 messages：
  用户这句话、之前说过的话、这一圈判断出什么、调过哪个能力，
  全都能放在消息里——这就是"正常 agent"的样子，和闲聊模块那张图一样。

以后什么时候往里加字段：
  Agent 要自己转圈（办完攻略接着查路线、或者停下来等用户很久），
  那就需要额外的字段（比如"这趟走到哪一步了"），那时候再加。
  现在是一句话进、一句话出，messages 够用。
"""

import operator
from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages


class TripState(TypedDict):
    # 对话上下文。用户说过的话是 HumanMessage，Agent 的判断和回复是 AIMessage；
    # 判断结果（要干什么）挂在 AIMessage 的 additional_kwargs 上。
    messages: Annotated[list, add_messages]

    # 这一圈要不要接着干（预留）：现在一句话办完就结束，
    # 将来 Agent 要调完一个能力再转一圈时，靠这个字段决定。
    node_path: Annotated[NotRequired[list[str]], operator.add]

    # 调用方给 Agent 的补充信息（比如已经查好的真实天气）。
    # Agent 看不到就会编，所以有就一定要塞进来。
    extra_context: NotRequired[str]
