"""路线规划｜这个能力的对外出口

做什么：解析路线需求 → 查地点和天气 → 跑路线决策图 → 暂停等人选 → 继续写结论 → 存库。
被谁用：modules/trip/agent.py（Agent 判断 action=route 后调）和 api/main.py（选完继续）。
注意：这个文件里的函数都是同步生成器，统一交给 core.sse.stream_from_thread 跑。

走到这里的前提：
  Agent 已经判断这一句是路线需求。所以这里不再做"是不是走错门"的判断，
  只负责把这条路线需求办到底。
"""

import uuid
from datetime import date

from langchain_core.messages import AIMessageChunk
from langgraph.types import Command

from core.sse import sse, stream_from_thread
from databases.db_trip import save_trip_turn
from modules.trip.capabilities.route.need import (
    build_initial_state,
    check_need,
    find_places,
    get_weather_text,
    parse_route_need,
)
from modules.trip.capabilities.route.graph import (
    ROUTE_SECTION_KEYS,
    ROUTE_TOKEN_KEYS,
    route_checkpointer,
    route_graph,
)
from modules.trip.capabilities.route.tools import (
    format_need_text,
    make_route_title,
)

# 路线决策的四步提示语。前端按后端发的 STEP 事件点亮进度条
ROUTE_STEP_TEXT = {
    "route_need": "正在确认起点和终点…",
    "route_compare": "正在查询候选路线…",
    "route_decision": "正在整理推荐方案…",
    "route_tips": "正在写出发提醒…",
}

ROUTE_NEXT_STEP = {
    "route_compare": "route_decision",
    "route_decision": "route_tips",
}

# 单个段落逐字推送的上限，防止极端情况下无限推送
MAX_ROUTE_TOKENS = 50000

# 这类地名指的是一个区域或一串异地点位，直接取第一个容易指错
BROAD_PLACE_WORDS = ("长城", "古镇", "老街", "风景区", "公园", "广场")


def _step(key):
    """打包一条路线进度提示。"""
    return sse({"kind": "STEP", "key": key, "text": ROUTE_STEP_TEXT[key]})


def _save(user_query, ai_output, turn_kind, chat_id, tenant_id):
    """存一轮，失败只打印，不影响已经生成的路线结果。"""
    try:
        return save_trip_turn(
            user_query, ai_output, turn_kind,
            chat_id=chat_id, tenant_id=tenant_id,
        )
    except Exception as e:
        print(f"[数据库] 出行记录写入失败（不影响本次结果）：{e}")
        return chat_id


def _chat_and_save(message, query, chat_id, tenant_id):
    """把反问当成一条普通回复存下来，并打包成 CHAT 事件。"""
    saved_chat_id = _save(query, {"chat_reply": message}, "CHAT", chat_id, tenant_id)
    return sse({"kind": "CHAT", "message": message, "chat_id": saved_chat_id})


def save_route_turn(state, chat_id, tenant_id):
    """把跑完的路线决策存成一轮 ROUTE 记录。"""
    need = state.get("need") or {}

    departure_time = need.get("departure_time") or ""
    start_date = departure_time[:10] if departure_time[:10] else str(date.today())

    ai_output = {
        "title": make_route_title(need),
        "destination": need.get("destination") or "",
        "start_date": start_date,
        "route_need": state.get("route_need") or state.get("need_text") or "",
        "route_compare": state.get("route_compare") or "",
        "route_decision": state.get("route_decision") or "",
        "route_tips": state.get("route_tips") or "",
    }

    return _save(state.get("user_query") or "", ai_output, "ROUTE", chat_id, tenant_id)


def _route_events(chunks, thread_id, context):
    """把图里的事件翻译成前端认识的 SSE。

    context 用来记两件事：
        paused  —— 是不是停在等用户选方案
        problem —— 查路线失败时的说明
    """
    tokens = {}

    for stream_mode, payload in chunks:
        if stream_mode == "messages":
            chunk, meta = payload
            node = meta.get("langgraph_node")
            key = ROUTE_TOKEN_KEYS.get(node)

            if not key or not isinstance(chunk, AIMessageChunk):
                continue
            if not chunk.content:
                continue
            if tokens.get(key, 0) >= MAX_ROUTE_TOKENS:
                continue

            tokens[key] = tokens.get(key, 0) + len(chunk.content)
            yield sse({"kind": "TOKEN", "key": key, "text": chunk.content})
            continue

        for node_name, update in payload.items():
            if node_name == "__interrupt__":
                context["paused"] = True
                value = update[0].value if update else {}

                yield sse({
                    "kind": "ASK",
                    "thread_id": thread_id,
                    "question": value.get("question", "你想按哪条路线走？"),
                    "options": value.get("options", []),
                    "recommended_id": value.get("recommended_id", ""),
                    "recommended_name": value.get("recommended_name", ""),
                    "recommended_text": value.get("recommended_text", ""),
                })
                continue

            if node_name == "collect_routes" and update.get("problem"):
                context["problem"] = update["problem"]
                yield sse({
                    "kind": "ERROR",
                    "message": f"没查到路线：{update['problem']}",
                })
                continue

            for key in ROUTE_SECTION_KEYS:
                text = update.get(key)
                if not text:
                    continue

                yield sse({"kind": "DONE", "key": key, "text": text})
                next_key = ROUTE_NEXT_STEP.get(key)
                if next_key:
                    yield _step(next_key)


def place_options(place_name, city):
    """把查到的地点整理成可以点的选项。"""
    from core.tools.amap import find_place_candidates

    options = []
    for index, place in enumerate(find_place_candidates(place_name, city), start=1):
        label = place.get("address") or place.get("name") or place_name
        note = place.get("level") or ""

        options.append({
            "id": str(index),
            "label": label,
            "note": note,
        })

    return options


def need_place_choice(place_name, city):
    """这个地名是不是该先让用户挑一个具体位置。

    只有「这类名字本来就指一片地方」并且「真查到好几个」才值得问。
    只查到一条时问了也没意义——没得选，点一下还是它自己。
    """
    if not any(word in place_name for word in BROAD_PLACE_WORDS):
        return False

    # 至少两条候选才构成一个"选择"
    return len(place_options(place_name, city)) >= 2


def can_ask_place(place_name, city):
    """认不准时，值不值得把候选摆出来。

    两条标准，必须同时满足才问：
      1. 至少两条候选——只有一条用户没得选，点完还是原来那个名字，
         重新解析一遍可能又回到同样的状态（以前就卡在这里）
      2. 这几条候选真的分不清——见 _needs_user_to_pick()。
         高德经常返回"主地点 + 同名的另一个小地方"，第一条明显最匹配时直接用它。
    """
    options = place_options(place_name, city)
    if len(options) < 2:
        return False

    return _needs_user_to_pick(place_name, options)


def _needs_user_to_pick(place_name, options):
    """这几条候选是不是真的需要用户来指。

    高德的两种返回要分开对待：
      A. 主地点 + 同名的另一个小地方（查"灵隐寺"带出"富阳灵隐寺"）
         → 第一条明显最匹配，直接用，别问
      B. 名字本来就指一片地方，真有好几处（"长城"有八达岭、慕田峪、司马台）
         → 得让用户选

    区分的依据是地址里名字**前面紧挨着什么**：
      A 型：…富阳区**富阳**灵隐寺     ← 名字前面是"富阳"，多了一个地名
      B 型：…通州区**长城**(西门)     ← 名字前面是"通州区"，那是行政区，不是地名修饰
    所以：名字前面紧挨着"省/市/区/县/镇/村"这类行政后缀，就是 B 型；
    紧挨着一个具体地名（富阳、慕田峪），就是同名变体，不用问。
    """
    admin_suffix = ("省", "市", "区", "县", "镇", "村", "道", "路", "街")

    for option in options[1:]:
        address = option["label"]
        index = address.find(place_name)
        if index <= 0:
            continue

        before = address[:index]
        # 名字前面紧挨着行政后缀：这是个独立的同名地点，属于 B 型
        if before.endswith(admin_suffix):
            return True
        # 否则是加了地名前缀的变体（富阳灵隐寺），跳过

    return False


def ask_place(question, place_name, city, query, chat_id, tenant_id):
    """地点认不准时，把候选摆出来让用户点。"""
    options = place_options(place_name, city)

    if options:
        saved_chat_id = _save(query, {"chat_reply": question}, "CHAT", chat_id, tenant_id)
        yield sse({
            "kind": "ASK_PLACE",
            "question": question,
            "name": place_name,
            "options": options,
            "chat_id": saved_chat_id,
        })
        return

    yield _chat_and_save(question, query, chat_id, tenant_id)


def start_route_decision(query, history=None, chat_id=None, tenant_id=None):
    """路线决策的第一步：解析需求、查地点、查候选，然后停在选方案。

    走到这里说明 Agent 已经判断"这句该查路线"。所以这里不再做"走错门"的判断，
    只负责把这条路线需求办到底；缺起点终点就如实反问，让用户补。
    """
    yield sse({"kind": "START", "mode": "ROUTE", "query": query})
    yield _step("route_need")

    need = parse_route_need(query, history)
    if need is None:
        yield _chat_and_save(
            "我没太听懂起点和终点。能说得具体一点吗？"
            "比如「从杭州东站到灵隐寺怎么走」。",
            query, chat_id, tenant_id,
        )
        return

    problem = check_need(need)
    if problem:
        yield _chat_and_save(problem, query, chat_id, tenant_id)
        return

    start, end, problem = find_places(need)
    if problem:
        # 能列出两个以上候选就让人点；只有一个（或一个都没有）就别问了——
        # 只查到一条时用户没得选，点了还是它自己，会来回绕。
        place_name = ""

        if "太笼统" in problem or "不太确定" in problem:
            if need["origin"] and need["origin"] in problem:
                place_name = need["origin"]
            elif need["destination"] in problem:
                place_name = need["destination"]

        if place_name and can_ask_place(place_name, need.get("city") or ""):
            yield from ask_place(
                f"「{place_name}」我查到的不太确定，你指的是下面哪个？",
                place_name,
                need.get("city") or "",
                query, chat_id, tenant_id,
            )
        else:
            yield _chat_and_save(problem, query, chat_id, tenant_id)

        return

    # 「长城」「古镇」这类名字能匹配到好几处，直接取第一个容易指错，先让人挑
    for place_name in (need["origin"], need["destination"]):
        if place_name and need_place_choice(place_name, need.get("city") or ""):
            yield from ask_place(
                f"「{place_name}」有多个地方，你指的是哪一个？",
                place_name,
                need.get("city") or "",
                query, chat_id, tenant_id,
            )
            return

    weather_text = get_weather_text(need)
    need_text = format_need_text(need, start, end, weather_text)

    yield sse({"kind": "DONE", "key": "route_need", "text": need_text})
    yield _step("route_compare")

    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    initial = build_initial_state(
        query, need, start, end, weather_text, need_text, tenant_id,
    )

    context = {"paused": False, "problem": ""}
    try:
        chunks = route_graph.stream(
            initial,
            config,
            stream_mode=["updates", "messages"],
        )
        yield from _route_events(chunks, thread_id, context)
    except Exception as e:
        yield sse({"kind": "ERROR", "message": f"这次路线决策没跑通：{e}"})
        return

    if context["paused"] or context["problem"]:
        return

    # 正常情况第一段一定会停在选方案，这里只是兜底
    final_state = route_graph.get_state(config).values
    saved_chat_id = save_route_turn(final_state, chat_id, tenant_id)
    route_checkpointer.delete_thread(thread_id)
    yield sse({"kind": "SAVED", "chat_id": saved_chat_id})


def resume_route_decision(thread_id, choice_id, chat_id=None, tenant_id=None):
    """用户在候选里点了一条之后，接着把对比、推荐、提醒写完。"""
    config = {"configurable": {"thread_id": thread_id}}
    state = route_graph.get_state(config)

    if not state.values or not state.next:
        yield sse({
            "kind": "ERROR",
            "message": "这次选择已经失效了，请重新查一次路线。",
        })
        return

    if state.values.get("tenant_id") != tenant_id:
        yield sse({
            "kind": "ERROR",
            "message": "这次选择不属于当前账号，请重新查一次路线。",
        })
        return

    yield sse({
        "kind": "SAY",
        "text": "按你选的方案，正在整理对比和推荐…",
    })

    context = {"paused": False, "problem": ""}
    try:
        chunks = route_graph.stream(
            Command(resume=choice_id),
            config,
            stream_mode=["updates", "messages"],
        )
        yield from _route_events(chunks, thread_id, context)
    except Exception as e:
        yield sse({"kind": "ERROR", "message": f"这次路线决策没跑通：{e}"})
        return

    if context["paused"] or context["problem"]:
        return

    final_state = route_graph.get_state(config).values
    saved_chat_id = save_route_turn(final_state, chat_id, tenant_id)
    route_checkpointer.delete_thread(thread_id)
    yield sse({"kind": "SAVED", "chat_id": saved_chat_id})


async def route_choose_stream(thread_id, choice_id, chat_id=None, tenant_id=None):
    """给 API 用的异步出口：把同步的恢复流程放进工作线程。"""
    async for event in stream_from_thread(
        resume_route_decision(
            thread_id, choice_id,
            chat_id=chat_id, tenant_id=tenant_id,
        )
    ):
        yield event
