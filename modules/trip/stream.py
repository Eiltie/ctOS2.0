"""出行｜模块对外唯一出口

做什么：分流(路线 / 攻略 / 闲聊) → 在工作线程里跑对应的图 → 边跑边吐 SSE。
被谁用：api/main.py 的 POST /trip/chat。
注意：同步的 LangGraph 必须留在工作线程里，挪回事件循环会让 SSE 被整体缓冲。
"""

from core.sse import sse, stream_from_thread
from databases.db_trip import save_trip_turn
from modules.trip.guide_stream import (
    check_guide_route,
    finish_guide,
    resume_guide,
    start_guide,
)
from modules.trip.node import weather_node
from modules.trip.route_decision_stream import start_route_decision
from modules.trip.understand import understand_query

# 只是问天气时，不用把它塞进“旅游攻略”或“路线”流程
WEATHER_WORDS = ("天气", "气温", "温度", "下雨", "降雨", "冷不冷", "热不热")
ROUTE_WORDS = ("怎么走", "路线", "坐什么", "堵不堵", "多久")


def _is_weather_query(query):
    has_weather = any(word in query for word in WEATHER_WORDS)
    has_route = any(word in query for word in ROUTE_WORDS)
    return has_weather and not has_route


def _save(user_query, ai_output, turn_kind, chat_id, tenant_id):
    """存一轮对话，失败只打印。"""
    try:
        return save_trip_turn(user_query, ai_output, turn_kind,
                              chat_id=chat_id, tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 出行记录写入失败（不影响本次结果）：{e}")
        return chat_id


def _weather_reply(query, chat_id, tenant_id):
    """只问天气：直接查天气，不要跑完整的攻略流程。"""
    try:
        state = weather_node({"user_query": query, "messages": []})
        text = (state.get("weather") or "").strip()
    except Exception as e:
        print(f"[天气] 查询失败：{e}")
        text = "这次没查到天气，换个城市名再试试。"

    saved_chat_id = _save(query, {"chat_reply": text}, "CHAT", chat_id, tenant_id)
    yield sse({"kind": "CHAT", "message": text, "chat_id": saved_chat_id})


async def trip_stream(query: str, history: list[str], chat_id=None, tenant_id=None):
    """先分流，再跑对应的流程，边跑边吐 SSE 事件。

    tenant_id 由 API 层从登录 token 取出来传进来，用于数据隔离。
    """

    # 一收到请求就先回一句，让用户知道系统收到了。
    # 这句话是固定的，不用调模型，所以不用等，几乎立刻就能发出去。
    yield sse({"kind": "SAY", "text": "收到，正在理解你的需求…"})

    # 分流和图都是同步调用，统一交给 stream_from_thread 放到工作线程里跑
    async for event in stream_from_thread(
        _run_trip(query, history, chat_id, tenant_id)
    ):
        yield event


def _run_trip(query: str, history: list[str], chat_id, tenant_id=None):
    """同步跑完整个出行流程，逐个 yield SSE 字符串。

    这段跑在工作线程里，不占用事件循环。
    """
    # query 是用户原话（存库、回显），merged_query 是合并后的需求，只喂给下游的图
    if _is_weather_query(query):
        yield from _weather_reply(query, chat_id, tenant_id)
        return

    kind, merged_query = understand_query(history, query)

    if kind == "CHAT":
        saved_chat_id = _save(query, {"chat_reply": merged_query}, "CHAT", chat_id, tenant_id)
        yield sse({"kind": "CHAT", "message": merged_query, "chat_id": saved_chat_id})
        return

    if kind == "ROUTE":
        yield from start_route_decision(query, merged_query, chat_id, tenant_id)
        return

    # 旅游攻略：会先停在景点清单，等用户勾完再继续
    yield sse({"kind": "START", "mode": "TRAVEL", "query": query, "understood": merged_query})
    yield from start_guide(query, merged_query, chat_id, tenant_id)


async def guide_choose_stream(thread_id, answer, chat_id=None, tenant_id=None):
    """用户在景点清单上点确认后，接着排行程、查路线。"""
    async for event in stream_from_thread(resume_guide(thread_id, answer)):
        yield event


async def guide_route_stream(thread_id, want_route, query, city, chat_id=None, tenant_id=None):
    """用户回答“要不要查真实路线”之后收尾。"""
    if want_route:
        async for event in stream_from_thread(
            check_guide_route(thread_id, city, query, chat_id, tenant_id)
        ):
            yield event
        return

    async for event in stream_from_thread(finish_guide(thread_id, query, chat_id, tenant_id)):
        yield event
