"""智能出行｜服务编排（这个模块的"大脑"）

做什么：让 Agent 判断这一句要干嘛，然后按判断去办：
        自己答 / 调路线规划子图 / 调旅游攻略子图，边办边吐 SSE。
被谁用：modules/trip/stream.py（/trip/chat 的出口）。

为什么编排写在这里、不写进图里：
  子图要"边跑边吐"——用户得看到进度。图的节点只能返回状态，产不出事件流。
  所以"判断"交给图（一句话一次判断，干净），"执行"留在这个生成器里，
  两者之间只传一个结论（action + 合并后的需求 + 回复正文）。

三个结论：
    answer —— Agent 自己回答（出行建议、推荐、准备清单、天气、闲聊）
    route  —— 交给路线规划子图
    guide  —— 交给旅游攻略子图

人在回路：子图自己的暂停照旧——用户点完还是打到子图的恢复接口，
          这一层不掺和，也不改线程号。
"""

from langchain_core.messages import AIMessage, HumanMessage

from modules.trip.sse import sse
from databases.modules.db_trip import save_trip_turn
from modules.trip.guide.node import answer_weather
from modules.trip.guide.stream import start_guide
from modules.trip.route.stream import start_route_decision
from modules.trip.graph import agent_graph

# 只是问天气时，先查真实数据再让 Agent 作答——不然模型会编气温
WEATHER_WORDS = ("天气", "气温", "温度", "下雨", "降雨", "冷不冷", "热不热")
ROUTE_WORDS = ("怎么走", "路线", "坐什么", "堵不堵", "多久")


def is_weather_query(query):
    """这句是不是只在问天气（不是问路上的天气/路况）。"""
    has_weather = any(word in query for word in WEATHER_WORDS)
    has_route = any(word in query for word in ROUTE_WORDS)
    return has_weather and not has_route


def save_turn(user_query, ai_output, turn_kind, chat_id, tenant_id):
    """存一轮，失败只打印——存库不该拖垮已经生成的结果。"""
    try:
        return save_trip_turn(user_query, ai_output, turn_kind,
                              chat_id=chat_id, tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 出行记录写入失败（不影响本次结果）：{e}")
        return chat_id


def decide(query, history, extra_context="", user_content=None):
    """跑一次 Agent 图，返回（action, 合并后的需求, 回复正文）。

    user_content 是这一轮用户消息的原始 content（带图时是块数组）。
    不传就退化成纯文字 query，和以前完全一样。
    """
    messages = [HumanMessage(content=text) for text in (history or []) if text]
    messages.append(HumanMessage(content=user_content if user_content is not None else query))

    result = agent_graph.invoke({
        "messages": messages,
        "extra_context": extra_context,
    })

    for message in reversed(result.get("messages") or []):
        if isinstance(message, AIMessage):
            kwargs = message.additional_kwargs or {}
            return (
                kwargs.get("action") or "answer",
                kwargs.get("query") or "",
                message.content or "",
            )

    return "answer", "", ""


def answer_directly(query, reply, chat_id, tenant_id):
    """Agent 自己答：存成 CHAT 轮，回一条气泡。"""
    text = (reply or "").strip() or "这句我还没完全听懂，说具体一点？"
    saved_chat_id = save_turn(query, {"chat_reply": text}, "CHAT", chat_id, tenant_id)
    return sse({"kind": "CHAT", "message": text, "chat_id": saved_chat_id})


def run_trip_service(query, history, chat_id=None, tenant_id=None, user_content=None):
    """一句话进来，办完出门。逐条 yield SSE。

    这段跑在工作线程里（同步生成器），由 stream.py 包起来。

    user_content：这一轮用户消息的原始 content（带图时是块数组）。
      只有 Agent 判断那一步需要看图；后面的路线、攻略子图拿到的
      是 Agent 写出来的文字需求（merged），它们不需要也不该再吃图。
    """
    # 只问天气：先把真实天气查出来当参考，再让 Agent 组织语言。
    # 不直接把天气文本甩给用户，是因为 Agent 还要决定顺带说点什么
    # （比如说"要排行程的话告诉我"）。
    extra = ""
    if is_weather_query(query):
        weather_text = answer_weather(query)
        extra = ("用户问的是天气，下面是系统查到的真实数据（照这个说，不要自己编）：\n"
                 + weather_text)

    action, merged, reply = decide(query, history, extra, user_content)
    merged = merged or query

    # 1) 自己答
    if action == "answer":
        yield answer_directly(query, reply, chat_id, tenant_id)
        return

    # 2) 交给路线规划子图
    if action == "route":
        yield from start_route_decision(merged, history, chat_id, tenant_id)
        return

    # 3) 交给旅游攻略子图
    yield sse({"kind": "START", "mode": "TRAVEL", "query": query})
    yield from start_guide(merged, chat_id=chat_id, tenant_id=tenant_id, history=history)

