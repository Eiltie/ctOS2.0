"""出行｜模块对外出口（阶段过渡版）

做什么：天气问答短路 → 意图分流 → 路线决策 / 旅游攻略。
被谁用：api/main.py 的 POST /trip/chat。

注意：这个文件正在过渡。
  旅游攻略已经搬到 modules/guide（自己的图、自己的 stream、自己的端点），
  这里保留分流只是为了让老的 /trip/chat 在拆分期间还能用。
  阶段 3 会把 understand 和这段分流一起删掉，那时这里只剩路线。
"""

from core.sse import sse, stream_from_thread
from databases.db_trip import save_trip_turn
from modules.guide.quick import answer_weather
from modules.guide.stream import resume_guide, start_guide
from modules.trip.route_decision_stream import start_route_decision
from modules.trip.understand import understand_query

# 只是问天气时，不用把它塞进"旅游攻略"或"路线"流程
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
    text = answer_weather(query)
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
    if _is_weather_query(query):
        yield from _weather_reply(query, chat_id, tenant_id)
        return

    kind, merged_query = understand_query(history, query)

    if kind == "CHAT":
        saved_chat_id = _save(query, {"chat_reply": merged_query}, "CHAT", chat_id, tenant_id)
        yield sse({"kind": "CHAT", "message": merged_query, "chat_id": saved_chat_id})
        return

    if kind == "ROUTE":
        # 路线侧自己会用 history 合并多轮补充，不再需要 merged_query
        yield from start_route_decision(query, history, chat_id, tenant_id)
        return

    # 旅游攻略：图在 modules/guide，会先停在景点清单，等用户勾完再继续
    yield sse({"kind": "START", "mode": "TRAVEL", "query": query})
    yield from start_guide(query, chat_id=chat_id, tenant_id=tenant_id, history=history)


async def guide_choose_stream(thread_id, answer, tenant_id=None):
    """用户在景点清单上点确认后，接着排行程、写游玩建议。"""
    async for event in stream_from_thread(resume_guide(thread_id, answer, tenant_id=tenant_id)):
        yield event
