"""出行｜旅游攻略的出口

做什么：跑攻略图 → 停在景点清单等用户勾选 → 继续排行程 → 跑完后问要不要查真实路线。
被谁用：modules/trip/stream.py（开始）和 api/main.py（用户确认后继续）。
注意：同步生成器，统一交给 core.sse.stream_from_thread 跑；暂停现场存在检查点文件里。
"""

import re
import uuid

from langchain_core.messages import AIMessageChunk
from langgraph.types import Command

from core.sse import sse
from databases.db_trip import save_trip_turn
from modules.trip.graph import build_graph
from modules.trip.route_decision_graph import guide_checkpointer

guide_graph = build_graph()

# 逐字推送的上限，防止极端情况下无限推送
MAX_GUIDE_TOKENS = 50000

# 攻略图里哪个节点产出哪一段
GUIDE_TOKEN_KEYS = {
    "weather": "weather",
    "spots_agent": "spots",
    "planner": "itinerary",
    "route_agent": "route_plan",
}

# 四段内容的键，和前端 TRIP_MODES.TRAVEL.sections 对齐
GUIDE_SECTION_KEYS = ("weather", "spots", "itinerary", "route_plan")

# 一段产出后，下一步在做什么
GUIDE_NEXT_STEP = {
    "weather": "spots",
    "spots": "itinerary",
    "itinerary": "route_plan",
}

GUIDE_STEP_TEXT = {
    "weather": "正在查询天气…",
    "spots": "正在搜集景点资料…",
    "itinerary": "正在安排行程…",
    "route_plan": "正在规划路线…",
}

# 节点跑到一半还没出正文时，补一句告诉用户在忙什么
GUIDE_PROGRESS_TEXT = {
    "spots_agent": "正在判断该查哪些景点资料…",
    "tools": "景点资料查到了，正在整理推荐清单…",
}

# 天气节点第一次调模型是解析需求，输出是 JSON，不能流给用户
GUIDE_SKIP_FIRST_NODES = {"weather"}

SPOTS_QUESTION = "这些景点可以吗？可以去掉不想去的，也可以补一个你想去的"


def guide_step(key):
    """打包一条攻略进度提示。"""
    return sse({"kind": "STEP", "key": key, "text": GUIDE_STEP_TEXT[key]})


def keep_token(node, chunk, blocked_node):
    """这一小段文字该不该流给用户。"""
    if node not in GUIDE_TOKEN_KEYS or not isinstance(chunk, AIMessageChunk):
        return False
    if chunk.tool_call_chunks or not chunk.content:
        return False

    rid = getattr(chunk, "id", None)
    if node in GUIDE_SKIP_FIRST_NODES and node not in blocked_node:
        blocked_node[node] = rid
    return not (node in blocked_node and rid == blocked_node[node])


def save_guide(query, produced, chat_id, tenant_id):
    """存一轮攻略，失败只打印。"""
    try:
        return save_trip_turn(query, produced, "TRAVEL", chat_id=chat_id, tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 出行记录写入失败（不影响本次结果）：{e}")
        return chat_id


def guide_events(chunks, thread_id, context):
    """把攻略图的事件翻译成前端认识的 SSE。"""
    tokens = {}
    blocked_node = {}

    for stream_mode, payload in chunks:
        if stream_mode == "messages":
            chunk, meta = payload
            node = meta.get("langgraph_node")
            if not keep_token(node, chunk, blocked_node):
                continue

            key = GUIDE_TOKEN_KEYS[node]
            if tokens.get(key, 0) >= MAX_GUIDE_TOKENS:
                continue
            tokens[key] = tokens.get(key, 0) + len(chunk.content)
            yield sse({"kind": "TOKEN", "key": key, "text": chunk.content})
            continue

        for node_name, update in payload.items():
            if node_name == "__interrupt__":
                context["paused"] = True
                value = update[0].value if update else {}
                if "spot_names" in value:
                    yield sse({
                        "kind": "ASK_SPOTS",
                        "thread_id": thread_id,
                        "question": value.get("question", SPOTS_QUESTION),
                        "spots": value.get("spots", ""),
                        "spot_names": value.get("spot_names", []),
                    })
                continue

            for key in GUIDE_SECTION_KEYS:
                if not update.get(key):
                    continue
                context["produced"][key] = update[key]
                yield sse({"kind": "DONE", "key": key, "text": update[key]})

                # 景点刚出完，接下来要停下来等用户勾选，别急着报“正在安排行程”
                if key == "spots":
                    continue

                next_key = GUIDE_NEXT_STEP.get(key)
                if next_key:
                    yield guide_step(next_key)

            if node_name in GUIDE_PROGRESS_TEXT:
                gave_content = any(update.get(k) for k in GUIDE_SECTION_KEYS)
                if not gave_content:
                    yield sse({"kind": "SAY", "text": GUIDE_PROGRESS_TEXT[node_name]})

            for key in ("destination", "days", "start_date"):
                if update.get(key):
                    context["produced"][key] = update[key]


def start_guide(query, merged_query, chat_id=None, tenant_id=None):
    """攻略第一步：跑图，停在景点清单等用户勾选。"""
    thread_id = "guide-" + uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}

    yield guide_step("weather")

    initial = {
        "user_query": merged_query,
        "destination": "",
        "days": 0,
        "start_date": "",
        "weather": "",
        "messages": [],
        "spots": "",
        "itinerary": "",
        "route_plan": "",
        "node_path": [],
    }

    context = {"paused": False, "produced": {}}
    try:
        chunks = guide_graph.stream(initial, config, stream_mode=["updates", "messages"])
        yield from guide_events(chunks, thread_id, context)
    except Exception as e:
        yield sse({"kind": "ERROR", "message": f"这次没跑通：{e}"})
        return

    if context["paused"]:
        return

    # 景点节点没给出名字列表时会跳过暂停，直接在这里收尾
    saved_chat_id = save_guide(query, context["produced"], chat_id, tenant_id)
    guide_checkpointer.delete_thread(thread_id)
    yield sse({"kind": "SAVED", "chat_id": saved_chat_id})


def resume_guide(thread_id, answer):
    """用户勾完景点，继续排行程和路线，跑完再问要不要查真实路线。"""
    config = {"configurable": {"thread_id": thread_id}}
    state = guide_graph.get_state(config)

    if not state.values or not state.next:
        yield sse({"kind": "ERROR", "message": "这次攻略已经失效了，请重新问一次。"})
        return

    yield sse({"kind": "SAY", "text": "按你选的景点，正在安排行程…"})

    context = {"paused": False, "produced": {}}
    for key in GUIDE_SECTION_KEYS:
        if state.values.get(key):
            context["produced"][key] = state.values[key]

    try:
        chunks = guide_graph.stream(Command(resume=answer), config,
                                    stream_mode=["updates", "messages"])
        yield from guide_events(chunks, thread_id, context)
    except Exception as e:
        yield sse({"kind": "ERROR", "message": f"这次没跑通：{e}"})
        return

    if context["paused"]:
        return

    yield sse({
        "kind": "ASK_ROUTE",
        "thread_id": thread_id,
        "question": "攻略写好了，要不要按真实路线查一下每天的移动？",
        "itinerary": context["produced"].get("itinerary", ""),
    })


def finish_guide(thread_id, query, chat_id=None, tenant_id=None):
    """用户选了“不用查路线”，直接存库收尾。"""
    config = {"configurable": {"thread_id": thread_id}}
    state = guide_graph.get_state(config)

    produced = {}
    for key in GUIDE_SECTION_KEYS:
        if state.values.get(key):
            produced[key] = state.values[key]

    saved_chat_id = save_guide(query or state.values.get("user_query") or "",
                               produced, chat_id, tenant_id)
    guide_checkpointer.delete_thread(thread_id)
    yield sse({"kind": "SAY", "text": "好的，攻略就到这里。"})
    yield sse({"kind": "SAVED", "chat_id": saved_chat_id})


def read_stops(itinerary):
    """从行程里把每天的景点按顺序抠出来。

    只认两种写法：
        上午：景点名（约 2 小时）
        09:20  景点名　游览约 3 小时
    模型偶尔会把一个景点名折成两行，比如：
        上午：灵隐飞来峰景区（含灵隐寺、
        永福寺）
    这时把没写完的括号接上，再当成一个景点。
    """
    days = []
    current = None
    pending = ""

    for line in itinerary.split("\n"):
        text = line.strip()
        if not text:
            continue

        if text.startswith("Day") or (text.startswith("第") and "天" in text):
            pending = ""
            current = {"day": text.split("｜")[0], "stops": []}
            days.append(current)
            continue

        if current is None:
            continue

        # 上一行括号没闭合，这一行是接着写的
        joined = False
        if pending:
            text = pending + text
            pending = ""
            joined = True

        if text.startswith(("上午：", "下午：", "晚上：")):
            value = text.split("：", 1)[-1]
        elif re.match(r"^\d{1,2}:\d{2}", text):
            value = re.sub(r"^\d{1,2}:\d{2}\s*", "", text)
        elif joined:
            # 续行本身没有“上午：”开头，但它是上一个景点的后半截
            value = text
        else:
            continue

        # 括号只开没关，等下一行拼上来再判断
        if value.count("（") > value.count("）") or value.count("(") > value.count(")"):
            pending = value
            continue

        stop = stop_name_from_text(value)
        if stop:
            current["stops"].append(stop)

    return [day for day in days if len(day["stops"]) >= 2]


def stop_name_from_text(text):
    """把“灵隐飞来峰景区（约 3 小时）”这种文字抠出景点名。"""
    # 整行是交通说明的，不是景点
    if any(word in text for word in ("前往", "返回住处", "返回酒店", "打车去", "坐车去")):
        return ""

    # 只有开头是吃饭/休息/活动这类安排时，才当成非景点，
    # 这样“河坊街·南宋御街（晚餐 + 逛）”仍然算景点
    skip_start = ("午餐", "晚餐", "早餐", "自由活动", "机动", "休息", "酒店", "住处", "出发", "返回", "回城", "返程")
    if text.startswith(skip_start):
        return ""

    # 先切掉括号里的时长说明，再切掉逗号后面的补充说明
    name = text.split("（")[0].split("(")[0]
    name = re.split(r"[，,]|约\s|游览|参观", name)[0]
    name = name.split("　")[0]

    # “河坊街—南宋御街逛吃、躲雨取暖”这种，把破折号后面的说明也切掉
    # 注意不用“·”当分隔，因为“河坊街·南宋御街”本身就是一个景点名
    name = re.split(r"[—]", name)[0]

    # 抠出来还带这些词，说明写的是安排而不是地点
    not_place = ("酒店", "住处", "附近", "吃饭", "晚餐", "午餐", "返程", "休息", "自由", "机动", "出门", "睡到", "早饭", "早餐", "逛")
    if any(word in name for word in not_place):
        return ""

    return name.strip() if len(name.strip()) >= 2 else ""


def check_guide_route(thread_id, city, query, chat_id=None, tenant_id=None):
    """按真实路线查行程里每天的相邻站点，再写一段说明。"""
    from modules.trip.route_decision_tools import get_bus_choices, get_drive_choices

    config = {"configurable": {"thread_id": thread_id}}
    state = guide_graph.get_state(config)

    if not state.values:
        yield sse({"kind": "ERROR", "message": "这次攻略已经失效了，请重新问一次。"})
        return

    produced = {}
    for key in GUIDE_SECTION_KEYS:
        if state.values.get(key):
            produced[key] = state.values[key]

    itinerary = produced.get("itinerary", "")
    days = read_stops(itinerary)

    # 攻略里不一定写了城市，没写就尽量用需求里认出的城市
    city = (city or state.values.get("destination") or "").strip()

    yield sse({"kind": "SAY", "text": "正在按真实路线查每天的移动…"})

    lines = []
    if not days:
        lines.append("没从行程里认出可以查的相邻站点，这次就不单独算了。")

    found_any = False

    for day in days:
        day_lines = []

        for start_name, end_name in zip(day["stops"], day["stops"][1:]):
            start = pick_place(start_name, city)
            end = pick_place(end_name, city)

            if start is None or end is None:
                day_lines.append(f"- {start_name} → {end_name}：地图上没查到地点，建议出发前再确认")
                continue

            drives = get_drive_choices(start["location"], end["location"])
            buses = get_bus_choices(
                start["location"], end["location"],
                start.get("adcode", ""), end.get("adcode", ""),
            )

            pieces = []
            if drives:
                drive = drives[0]
                pieces.append(f"打车约 {drive['minutes']} 分钟 / {drive['distance_km']} 公里")
            if buses:
                bus = buses[0]
                pieces.append(f"公交约 {bus['minutes']} 分钟 / {bus['cost_yuan']:.0f} 元")

            if pieces:
                found_any = True
                day_lines.append(f"- {start_name} → {end_name}：" + "，".join(pieces))
            else:
                day_lines.append(f"- {start_name} → {end_name}：没查到路线，建议按地图软件再确认")

        if day_lines:
            lines.append(day["day"])
            lines.extend(day_lines)
            lines.append("")

    if not found_any:
        lines.append("这次一条路线都没算出来，可能是地图服务暂时不可用，出发前再用地图软件确认一下。")

    lines.append("以上按当前路况估算，出发前请再看一次实时路况。")
    route_text = "\n".join(lines).strip()

    # 已经发过的那几段不重发，只把“每一天怎么移动”单独作为一段补上
    yield sse({"kind": "DONE", "key": "guide_route", "text": route_text})

    saved_chat_id = save_guide(query or state.values.get("user_query") or "",
                               produced, chat_id, tenant_id)
    guide_checkpointer.delete_thread(thread_id)
    yield sse({"kind": "SAVED", "chat_id": saved_chat_id})


def pick_place(name, city):
    """查地点，尽量多试几种写法，提高认出行程站点的概率。

    比如“京杭大运河博物馆（拱宸桥馆区）”，高德认不出全名，
    但去掉括号、加“杭州”前缀之后就能查到。
    """
    from modules.trip.route_decision_tools import find_place

    short_name = name.split("（")[0].split("(")[0].strip()

    tried = [name]
    if short_name and short_name != name:
        tried.append(short_name)

    if city:
        for base_name in list(tried):
            if not base_name.startswith(city):
                tried.append(city + base_name)

    for candidate in tried:
        place = find_place(candidate, city)
        if place and not place.get("too_vague"):
            return place

    return None
