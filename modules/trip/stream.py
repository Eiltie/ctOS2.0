"""出行｜模块对外唯一出口（路线规划）

做什么：只问天气 → 直接回一句；其余全部交给路线决策。
被谁用：api/main.py 的 POST /trip/chat。
注意：旅游攻略在 modules/guide，有自己的入口和端点，和这里没有任何调用关系。

拆分前这里还有一层"意图分流"（一次模型调用判断路线/攻略/闲聊）。
现在模式由用户点，走错模式时由各自模块发 SUGGEST 让他一键转场，
所以那层分流已删除。
"""

from core.sse import sse, stream_from_thread
from databases.db_trip import save_trip_turn
from modules.guide.quick import answer_weather
from modules.trip.route_decision_stream import start_route_decision

# 只是问天气时，不用把它塞进路线流程
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
    """只问天气：直接查天气，不要跑完整的路线流程。"""
    text = answer_weather(query)
    saved_chat_id = _save(query, {"chat_reply": text}, "CHAT", chat_id, tenant_id)
    yield sse({"kind": "CHAT", "message": text, "chat_id": saved_chat_id})


async def trip_stream(query: str, history: list[str], chat_id=None, tenant_id=None):
    """路线规划：边跑边吐 SSE 事件。

    tenant_id 由 API 层从登录 token 取出来传进来，用于数据隔离。
    """

    # 一收到请求就先回一句，让用户知道系统收到了。
    # 这句话是固定的，不用调模型，所以不用等，几乎立刻就能发出去。
    yield sse({"kind": "SAY", "text": "收到，正在理解你的需求…"})

    # 图和解析都是同步调用，统一交给 stream_from_thread 放到工作线程里跑
    async for event in stream_from_thread(
        _run_trip(query, history, chat_id, tenant_id)
    ):
        yield event


def _run_trip(query: str, history: list[str], chat_id, tenant_id=None):
    """同步跑完一次路线规划，逐个 yield SSE 字符串。

    这段跑在工作线程里，不占用事件循环。
    """
    if _is_weather_query(query):
        yield from _weather_reply(query, chat_id, tenant_id)
        return

    # 路线侧自己会用 history 合并多轮补充（"改成8点出发"这类）
    yield from start_route_decision(query, history, chat_id, tenant_id)
