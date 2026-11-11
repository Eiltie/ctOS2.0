"""出行｜路线决策的对外出口

做什么：解析路线需求 → 查地点和天气 → 跑路线决策图 → 暂停等人选 → 继续写结论 → 存库。
被谁用：modules/trip/stream.py（开始）和 api/main.py（选完继续）。
注意：这个文件里的函数都是同步生成器，统一交给 core.sse.stream_from_thread 跑。
"""

import json
import uuid
from datetime import date, datetime, timedelta

from langchain_core.messages import AIMessageChunk
from langgraph.types import Command

from core.llm import get_llm
from core.sse import sse, stream_from_thread
from databases.db_trip import save_trip_turn
from modules.trip.route_decision_graph import (
    ROUTE_SECTION_KEYS,
    ROUTE_TOKEN_KEYS,
    route_checkpointer,
    route_graph,
)
from modules.trip.route_decision_prompts import PARSE_ROUTE_NEED_PROMPT
from modules.trip.route_decision_tools import (
    find_place,
    find_place_candidates,
    format_need_text,
    make_route_title,
    normalize_preference,
    normalize_want_mode,
)
from modules.trip.tools import get_weather

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

# 这些词太笼统，直接查地图会认错地方，先反问用户
VAGUE_PLACES = {
    "家", "我家", "学校", "我们学校", "公司", "单位",
    "这里", "附近", "当前位置", "我这",
}


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


def parse_route_need(merged_query):
    """把合并后的需求解析成路线字段；解析失败返回 None。"""
    today = date.today()
    now = datetime.now()

    prompt = (PARSE_ROUTE_NEED_PROMPT
              .replace("{today}", str(today))
              .replace("{weekday}", "一二三四五六日"[today.weekday()])
              .replace("{now}", now.strftime("%Y-%m-%d %H:%M"))
              .replace("{tomorrow}", str(today + timedelta(days=1)))
              .replace("{user_query}", merged_query))

    raw = get_llm().with_config(tags=["internal"]).invoke(prompt).content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, AttributeError):
        return None

    if not isinstance(data, dict):
        return None

    return {
        "origin": str(data.get("origin") or "").strip(),
        "destination": str(data.get("destination") or "").strip(),
        "city": str(data.get("city") or "").strip(),
        "departure_time": str(data.get("departure_time") or "").strip(),
        "preference": normalize_preference(str(data.get("preference") or "")),
        "companions": str(data.get("companions") or "").strip(),
        "want_mode": normalize_want_mode(str(data.get("want_mode") or "")),
        "avoid": str(data.get("avoid") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
    }


def check_need(need):
    """检查起点、终点、城市够不够，返回一句要问用户的话；没问题返回空字符串。"""
    origin = need["origin"]
    destination = need["destination"]
    city = need["city"]

    if not origin:
        return "起点是哪？说个地标、小区或车站，我就能查路线。比如“从杭州东站到灵隐寺”。"
    if not destination:
        return "终点是哪？说个具体地点，我就能查路线。"
    if origin in VAGUE_PLACES:
        return f"「{origin}」太笼统了，具体是哪个小区、校区或哪条路？说个地标或地址就行。"
    if destination in VAGUE_PLACES:
        return f"「{destination}」太笼统了，具体是哪个地方？说个景点名或地址就行。"
    if not city:
        return f"「{destination}」在哪个城市？告诉我城市名，我就能查路线。"

    return ""


def find_places(need):
    """查起点和终点，返回（起点, 终点, 要问用户的话）。

    起点是开放的：用户在北京，要去别的城市也可以。
    终点如果没城市又全国都查不到，就回去问是哪个城市，别硬猜。
    """
    start = find_place(need["origin"], need["city"], allow_nationwide=True)
    if start is None:
        return None, None, (
            f"没找到起点「{need['origin']}」，能说具体一点吗？"
            f"比如加上城市或附近的路。"
        )
    if start.get("too_vague"):
        return None, None, (
            f"「{need['origin']}」我查到的是「{start.get('address') or start.get('city')}」，"
            f"不太确定。能说具体一点吗？比如景点全称或附近的路。"
        )

    end = find_place(need["destination"], need["city"])

    # 有城市时按城市查；没有城市时全国查，查不到再问是哪个城市
    if end is None and not need["city"]:
        end = find_place(need["destination"], "", allow_nationwide=True)

    if end is None:
        return None, None, (
            f"没找到终点「{need['destination']}」（城市：{need['city']}），"
            f"能说具体一点吗？比如景点全称。"
        )
    if end.get("too_vague"):
        return None, None, (
            f"「{need['destination']}」我查到的是「{end.get('address') or end.get('city')}」，"
            f"不太确定。能说具体一点吗？"
        )

    return start, end, ""


def get_weather_text(need):
    """查出发当天的天气；查不到就返回空字符串。"""
    city = need.get("city") or ""
    if not city:
        return ""

    departure_time = need.get("departure_time") or ""
    weather_date = departure_time[:10] if departure_time[:10] else str(date.today())

    try:
        return get_weather.invoke({
            "city": city,
            "days": 1,
            "start_date": weather_date,
        })
    except Exception as e:
        print(f"[路线] 天气查询失败：{e}")
        return ""


def build_initial_state(query, merged_query, need, start, end, weather_text, need_text, tenant_id):
    """把进图前准备好的字段装成一个完整的状态。"""
    return {
        "user_query": query,
        "merged_query": merged_query,
        "tenant_id": tenant_id,
        "need": need,
        "start_place": start,
        "end_place": end,
        "weather_text": weather_text,
        "need_text": need_text,
        "route_need": need_text,
        "choices": [],
        "recommended_index": -1,
        "candidate_text": "",
        "problem": "",
        "choice_id": "",
        "choice_id_name": "",
        "choice_index": -1,
        "route_compare": "",
        "route_decision": "",
        "route_tips": "",
        "node_path": [],
    }


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


# 这类地名指的是一个区域或一串异地点位，直接取第一个容易指错
BROAD_PLACE_WORDS = ("长城", "古镇", "老街", "风景区", "公园", "广场")


def need_place_choice(place_name, city):
    """这个地名是不是该先让用户挑一个具体位置。"""
    if not any(word in place_name for word in BROAD_PLACE_WORDS):
        return False

    return len(place_options(place_name, city)) >= 2


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


def start_route_decision(query, merged_query, chat_id=None, tenant_id=None):
    """路线决策的第一步：解析需求、查地点、查候选，然后停在选方案。"""
    yield sse({
        "kind": "START",
        "mode": "ROUTE",
        "query": query,
        "understood": merged_query,
    })
    yield _step("route_need")

    need = parse_route_need(merged_query)
    if need is None:
        yield _chat_and_save(
            "我没太听懂起点和终点。能说得具体一点吗？"
            "比如“从杭州东站到灵隐寺怎么走”。",
            query, chat_id, tenant_id,
        )
        return

    problem = check_need(need)
    if problem:
        yield _chat_and_save(problem, query, chat_id, tenant_id)
        return

    start, end, problem = find_places(need)
    if problem:
        # 能列出候选就让人点，列不出来才用文字追问
        place_name = ""

        if "太笼统" in problem or "不太确定" in problem:
            if need["origin"] and need["origin"] in problem:
                place_name = need["origin"]
            elif need["destination"] in problem:
                place_name = need["destination"]

        if place_name:
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
        query, merged_query, need, start, end, weather_text, need_text, tenant_id,
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
