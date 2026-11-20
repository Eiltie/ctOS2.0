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

from common.sse import sse
from databases.modules.db_trip import save_trip_turn
from modules.trip import image_offer as offers
from modules.trip import image_pending
from modules.trip.guide.quick import answer_weather
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
    # 0) 这一句是不是在**直接要图**？
    #    分两种情况：
    #      a) 上一轮提议过，用户在回答「要」
    #      b) 用户自己开口就要图（「要图片」「画张路线图」）
    #    出行模块专做出行，但图是它的补充能力 ——
    #    用户明确要，就该给，不能因为「没走完流程」就不画。
    offer = image_pending.peek(tenant_id, chat_id)
    direct = offers.wants_image_now(query)

    if offer and offers.wants_image(query):
        image_pending.take(tenant_id, chat_id)
        yield from _generate_image_turn(offer, query, chat_id, tenant_id)
        return

    if direct:
        # 用户主动要图：拿之前跑过的内容当素材，没有就按他这句话画
        image_pending.clear(tenant_id, chat_id)
        prompt = offer["prompt"] if offer else offers.build_free_image_prompt(query)
        yield from _generate_image_turn(
            {"prompt": prompt, "kind": "free"}, query, chat_id, tenant_id,
        )
        return

    # 用户明确拒绝或者换了话题：清掉那条提议，别挂在那儿
    if offer and not offers.wants_image(query):
        image_pending.clear(tenant_id, chat_id)

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
        yield from _with_image_offer(
            start_route_decision(merged, history, chat_id, tenant_id),
            kind=offers.KIND_ROUTE,
            merged=merged,
            chat_id=chat_id,
            tenant_id=tenant_id,
        )
        return

    # 3) 交给旅游攻略子图
    yield sse({"kind": "START", "mode": "TRAVEL", "query": query})
    yield from _with_image_offer(
        start_guide(merged, chat_id=chat_id, tenant_id=tenant_id, history=history),
        kind=offers.KIND_GUIDE,
        merged=merged,
        chat_id=chat_id,
        tenant_id=tenant_id,
    )


def _with_image_offer(stream, kind, merged, chat_id, tenant_id):
    """在路线/攻略跑完之后，顺手提议一句「要不要生成一张图」。

    为什么要包一层：
      子图的产出要边跑边吐，同时我们得在**它跑完**的那一刻插入提议。
      用一个包装生成器既保留了流式，又能拿到最后的状态。

    什么情况下提议：
      只要这一轮**有像样的产出**就提议，包括停在等用户操作的时候。
      先说清楚：用户停在「选方案」「勾景点」这个界面上时，
      恰恰是他最想要一张图的时候 —— 他手里已经有需求确认、有候选路线了。
      之前这里是「停下来就不提议」，导致用户说「要图片」完全没人接。
      唯一的例外是出错（ERROR），那种情况没东西可画。

    为什么要收集产出内容：
      生图需要素材（起点终点、每天的安排）。这些东西在子图吐出的
      TOKEN/DONE 事件里，得先攒起来，等用户说「要」的时候才有料可画。
    """
    produced = {}
    saved_chat_id = chat_id
    failed = False

    for event in stream:
        # 攒素材：把各段定稿的文字存下来
        try:
            import json

            payload = json.loads(event.removeprefix("data: ").strip())
            if payload.get("kind") == "DONE" and payload.get("key"):
                produced[payload["key"]] = payload.get("text") or ""
            elif payload.get("kind") == "SAVED":
                saved_chat_id = payload.get("chat_id") or saved_chat_id
            elif payload.get("kind") == "ERROR":
                # 出错：没东西可画，不提议
                failed = True
        except Exception:
            pass

        yield event

    # 出错，或者一点产出都没有：不提议
    if failed or not produced:
        return

    # 拼出生图需求
    if kind == offers.KIND_ROUTE:
        prompt = offers.build_route_image_prompt(
            produced.get("route_need", merged),
            produced.get("route_decision", ""),
            produced.get("route_tips", ""),
        )
        title = "路线示意图"
    else:
        prompt = offers.build_guide_image_prompt(
            merged,
            produced.get("itinerary", ""),
            produced.get("spots", ""),
        )
        title = "行程海报"

    if not prompt:
        return

    # 记住这条提议，等用户下一句回答
    image_pending.remember(tenant_id, saved_chat_id, kind, prompt, title)

    yield offers.propose(kind)


def _generate_image_turn(offer, user_query, chat_id, tenant_id):
    """用户说了「要」：跑一次生图，把结果作为一条 CHAT 事件发出去。

    失败不影响对话 —— 画不出来就说一句，不报错。
    """
    yield sse({"kind": "SAY", "text": "正在生成图片，大概十几秒…"})

    try:
        from common.tools.imagesproduct import imageProduct

        saved = imageProduct(offer["prompt"], tenantId=tenant_id)
    except Exception as e:
        print(f"[生图] 生成失败：{e}")
        yield sse({"kind": "CHAT", "message": "这次没能生成图片，稍后再试试。", "chat_id": chat_id})
        return

    if not saved:
        yield sse({"kind": "CHAT", "message": "这次没能生成图片，稍后再试试。", "chat_id": chat_id})
        return

    rel_path, mime, byte_size = saved

    # 登记进 message_images，让前端能用统一的方式取图
    image_id = _register_image(rel_path, tenant_id, chat_id, mime, byte_size)

    if image_id is None:
        yield sse({"kind": "CHAT", "message": "这次没能生成图片，稍后再试试。", "chat_id": chat_id})
        return

    saved_chat_id = save_turn(
        user_query,
        {"chat_reply": "图片已生成", "image_id": image_id},
        "CHAT", chat_id, tenant_id,
    )

    yield sse({
        "kind": "CHAT",
        "message": f"图生成好了，可以直接点开下载。",
        "chat_id": saved_chat_id,
    })
    # 单独发一条「有图」的提示，前端据此显示
    yield sse({"kind": "IMAGE", "image_id": image_id, "chat_id": saved_chat_id})


def _register_image(rel_path, tenant_id, session_id, mime=None, byte_size=0):
    """把生成的图登记进 message_images，返回 image_id。

    mime / byte_size 由 imageProduct 给出；没给才按扩展名兜底。
    """
    try:
        from databases.modules.db_chat import add_message_image

        if not mime:
            ext = rel_path.rsplit(".", 1)[-1].lower()
            mime = {"png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(
                ext, "image/jpeg"
            )

        return add_message_image(
            None, rel_path, mime, byte_size or 0,
            session_id=None, tenant_id=tenant_id,
        )
    except Exception as e:
        print(f"[生图] 登记图片失败：{e}")
        return None
