"""出行｜模块对外唯一出口

做什么：把一句话交给智能出行服务，边办边吐 SSE。
被谁用：api/main.py 的 POST /trip/chat。

这一层现在只做三件事：先回一句"收到"、把同步流程放进工作线程、把事件原样转发。
判断"这句话该干什么"是 Agent 的事（modules/trip/agent.py），这里不掺和。
"""

from modules.trip.sse import sse, stream_from_thread
from modules.trip.agent import run_trip_service


async def trip_stream(query: str, history: list[str], chat_id=None, tenant_id=None,
                      user_content=None):
    """智能出行：边跑边吐 SSE 事件。

    tenant_id 由 API 层从登录 token 取出来传进来，用于数据隔离。
    user_content：这一轮用户消息的原始 content（带图时是块数组），
                  交给 Agent 看图判断；不带图时是 None，行为和以前一致。
    """

    # 一收到请求就先回一句，让用户知道系统收到了。
    # 这句话是固定的，不用调模型，所以不用等，几乎立刻就能发出去。
    yield sse({"kind": "SAY", "text": "收到，正在理解你的需求…"})

    # 判断和子图都是同步调用，统一交给 stream_from_thread 放到工作线程里跑
    async for event in stream_from_thread(
        run_trip_service(query, history, chat_id, tenant_id, user_content)
    ):
        yield event
