"""旅游攻略｜模块对外唯一出口

做什么：跑攻略图 → 停在景点清单等用户勾选 → 继续排行程、写游玩建议 → 存库。
被谁用：api/main.py 的 POST /guide/chat 和 POST /guide/spots。
注意：同步生成器，统一交给 core.sse.stream_from_thread 跑；暂停现场存在检查点文件里。

和拆分前的区别：
  1. 没有第二个暂停点了。勾完景点一路跑到"游玩建议"，不再问"要不要查真实路线"。
  2. 不再 import 路线模块的任何东西。
"""

import uuid

from langchain_core.messages import AIMessageChunk
from langgraph.types import Command

from core.checkpoints import get_checkpointer
from core.sse import sse
from databases.db_trip import save_trip_turn
from modules.guide.graph import build_graph

guide_graph = build_graph()

# 逐字推送的上限，防止极端情况下无限推送
MAX_GUIDE_TOKENS = 50000

# 攻略图里哪个节点产出哪一段
GUIDE_TOKEN_KEYS = {
    "weather": "weather",
    "spots_agent": "spots",
    "planner": "itinerary",
    "advice": "advice",
}

# 四段内容的键，和前端 TRIP_MODES.TRAVEL.sections 对齐
GUIDE_SECTION_KEYS = ("weather", "spots", "itinerary", "advice")

# 一段产出后，下一步在做什么
GUIDE_NEXT_STEP = {
    "weather": "spots",
    "spots": "itinerary",
    "itinerary": "advice",
}

GUIDE_STEP_TEXT = {
    "weather": "正在查询天气…",
    "spots": "正在搜集景点资料…",
    "itinerary": "正在安排行程…",
    "advice": "正在写游玩建议…",
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

                # 景点刚出完，接下来要停下来等用户勾选，别急着报"正在安排行程"
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


def start_guide(query, chat_id=None, tenant_id=None, history=None):
    """攻略第一步：跑图，停在景点清单等用户勾选。"""
    thread_id = "guide-" + uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}

    yield guide_step("weather")

    initial = {
        "user_query": query,
        "history": list(history or []),
        "tenant_id": tenant_id,
        "chat_id": chat_id,
        "destination": "",
        "days": 0,
        "start_date": "",
        "weather": "",
        "messages": [],
        "spots": "",
        "itinerary": "",
        "advice": "",
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
    get_checkpointer().delete_thread(thread_id)
    yield sse({"kind": "SAVED", "chat_id": saved_chat_id})


def resume_guide(thread_id, answer, tenant_id=None):
    """用户勾完景点，继续排行程、写游玩建议，然后存库。"""
    config = {"configurable": {"thread_id": thread_id}}
    state = guide_graph.get_state(config)

    if not state.values or not state.next:
        yield sse({"kind": "ERROR", "message": "这次攻略已经失效了，请重新问一次。"})
        return

    # 暂停现场不属于当前账号就不让接着跑。
    # 老线程没有 tenant_id（拆分前存的），放行，避免升级后旧会话直接失效
    saved_tenant = state.values.get("tenant_id")
    if saved_tenant is not None and saved_tenant != tenant_id:
        yield sse({"kind": "ERROR", "message": "这次攻略不属于当前账号，请重新问一次。"})
        return

    yield sse({"kind": "SAY", "text": "按你选的景点，正在安排行程…"})

    # 参数先规整成固定形状再恢复：
    # 空字典在 LangGraph 里会被当成"没有恢复值"，图会重新停在原地。
    # 前端正常会传 {removed, added}，这里兜一下歪掉的入参。
    if not isinstance(answer, dict):
        answer = {}
    answer = {
        "removed": [str(n) for n in (answer.get("removed") or []) if str(n).strip()],
        "added": str(answer.get("added") or "").strip(),
    }

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

    saved_chat_id = save_guide(
        state.values.get("user_query") or "",
        context["produced"],
        state.values.get("chat_id"),
        tenant_id,
    )
    get_checkpointer().delete_thread(thread_id)
    yield sse({"kind": "SAVED", "chat_id": saved_chat_id})
