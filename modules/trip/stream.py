"""出行｜模块对外唯一出口

做什么：分流(出行还是闲聊) → 在工作线程里跑图 → 边跑边吐 SSE 并逐段落库。
被谁用：api/main.py 的 POST /trip/chat。
注意：同步的 LangGraph 必须留在工作线程里，挪回事件循环会让 SSE 被整体缓冲。
"""

import asyncio
import threading

from langchain_core.messages import AIMessageChunk

from databases.db_trip import save_trip_turn
from core.sse import sse
from modules.trip.graph import build_graph
from modules.trip.understand import understand_query

# 出行模块的对外出口：ctOS_chat_api 只 import 这里的 trip_stream
# 逐字推送与事件字段
# 单个节点逐字推送的上限，防止极端情况下无限推送
MAX_TOKENS = 50000

trip_graph = build_graph()

# 进图时各段产出的初始状态：字段要和 AgentState 对齐，缺字段的节点会直接 KeyError
INITIAL_STATE = {
    "user_query": "",
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

# 节点 → 产出字段：逐字碎片贴到哪一段、前端进度条怎么亮
SECTION_KEYS = ("weather", "spots", "itinerary", "route_plan")

# 逐字碎片凭这张表决定贴到哪一段；表外节点（如 tools）不产正文
NODE_TO_KEY = {
    "weather": "weather",
    "spots_agent": "spots",
    "planner": "itinerary",
    "route_agent": "route_plan",
}

# 静默时段的进度提示与下一段提示
STEP_TEXT = {
    "weather": "正在查询天气…",
    "spots": "正在搜集景点资料…",
    "itinerary": "正在安排行程…",
    "route_plan": "正在规划路线…",
}

NEXT_KEY = {
    "weather": "spots",
    "spots": "itinerary",
    "itinerary": "route_plan",
}

# 节点跑到一半、还没产出正文时，补一句话告诉用户在忙什么。
# 键是节点名，值是那句话。不在表里的节点不发这类提示。
NODE_PROGRESS_TEXT = {
    "spots_agent": "正在判断该查哪些景点资料…",
    "tools": "景点资料查到了，正在整理推荐清单…",
}

# 超过这么多秒没有任何新内容，就补一句「还在处理」，避免用户以为卡死。
# 景点搜索、路线查询这类环节中间会有较长的静默，靠这个兜底。
HEARTBEAT_SECONDS = 8

# 天气节点第一次调 LLM 是在解析需求，那段的输出是 JSON，不能流给用户
SKIP_FIRST_CALL_NODES = {"weather"}


def _step(key: str) -> str:
    """打包一条进度提示（STEP）事件。"""
    return sse({"kind": "STEP", "key": key, "text": STEP_TEXT[key]})


def _keep(node: str, chunk, blocked_node: dict) -> bool:
    """这一小段文字该不该流给用户。"""
    # 四道过滤：① 表外节点 ② 只要逐字碎片（挡开场白这类整条消息）
    # ③ 带 tool_call 的是 ReAct 中间轮的工具参数 ④ 该节点的内部调用
    if node not in NODE_TO_KEY or not isinstance(chunk, AIMessageChunk):
        return False
    if chunk.tool_call_chunks or not chunk.content:
        return False

    rid = getattr(chunk, "id", None)
    if node in SKIP_FIRST_CALL_NODES and node not in blocked_node:
        blocked_node[node] = rid
    return not (node in blocked_node and rid == blocked_node[node])


def _save(user_query: str, ai_output: dict, turn_kind: str, chat_id, tenant_id):
    """存一轮出行对话，返回所属会话 id；失败只打印。"""
    # 存库失败不能拖垮这一轮：不然用户白等一次规划
    try:
        return save_trip_turn(user_query, ai_output, turn_kind,
                              chat_id=chat_id, tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 出行记录写入失败（不影响本次结果）：{e}")
        return chat_id


async def trip_stream(query: str, history: list[str], chat_id=None, tenant_id=None):
    """先分流，再跑出行图，边跑边吐 SSE 事件。

    tenant_id 由 API 层从登录 token 取出来传进来，用于数据隔离。
    """

    # 一收到请求就先回一句，让用户知道系统收到了。
    # 这句话是固定的，不用调模型，所以不用等，几乎立刻就能发出去。
    yield sse({"kind": "SAY", "text": "收到，正在理解你的需求…"})

    # understand_query 和图都是同步调用，直接跑会把事件循环卡住，
    # 期间已经 yield 的数据发不出去，浏览器会一直白屏到整个流程结束。
    # 所以统一切到线程里跑，这里用队列把结果取回来。
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    DONE = object()

    def worker():
        """工作线程：跑同步逻辑，每产出一条就丢进队列。"""
        try:
            for item in _run_trip(query, history, chat_id, tenant_id):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", e))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, DONE)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        try:
            # 最多等 HEARTBEAT_SECONDS 秒。等到了就正常发出去，
            # 等不到说明工作线程还在闷头干活，先给用户一句提示再继续等。
            item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
        except asyncio.TimeoutError:
            yield sse({"kind": "SAY", "text": "仍在处理中，请稍等…"})
            continue

        if item is DONE:
            break
        # 工作线程里没被 _run_trip 内部捕获的异常，转成 ERROR 事件给前端
        if isinstance(item, tuple) and item and item[0] == "error":
            yield sse({"kind": "ERROR", "message": f"这次没跑通：{item[1]}"})
            continue
        yield item


def _run_trip(query: str, history: list[str], chat_id, tenant_id=None):
    """同步跑完整个出行流程，逐个 yield SSE 字符串。

    这段跑在工作线程里，不占用事件循环。
    """
    # 两个值要分清：query 是用户原话（存库、回显），merged_query 是合并后的需求，只喂给出行图
    kind, merged_query = understand_query(history, query)

    if kind == "CHAT":
        saved_chat_id = _save(query, {"chat_reply": merged_query}, "CHAT", chat_id, tenant_id)
        yield sse({"kind": "CHAT", "message": merged_query, "chat_id": saved_chat_id})
        return

    # 回显用户原话，合并后的需求单独放在 understood 里，前端不展示、也不进历史
    yield sse({"kind": "START", "query": query, "understood": merged_query})
    yield _step("weather")
    blocked_node: dict[str, str] = {}
    tokens: dict[str, int] = {}
    produced: dict[str, str] = {}

    try:
        for mode, payload in trip_graph.stream(
            {**INITIAL_STATE, "user_query": merged_query},
            stream_mode=["updates", "messages"],
        ):
            if mode == "messages":
                chunk, meta = payload
                node = meta.get("langgraph_node")
                if not _keep(node, chunk, blocked_node):
                    continue

                key = NODE_TO_KEY[node]
                if tokens.get(key, 0) >= MAX_TOKENS:
                    continue
                tokens[key] = tokens.get(key, 0) + len(chunk.content)
                yield sse({"kind": "TOKEN", "key": key, "text": chunk.content})

            else:
                for node_name, update in payload.items():
                    for key in SECTION_KEYS:
                        if update.get(key):
                            produced[key] = update[key]
                            yield sse({"kind": "DONE", "key": key, "text": update[key]})
                            nxt = NEXT_KEY.get(key)
                            if nxt:
                                yield _step(nxt)

                    # 这个节点跑了但还没交出正文（中途轮次），补一句进度。
                    # 比如景点先问模型要不要搜索、搜完再回来写清单，
                    # 中间这两段原本是完全没有输出的。
                    if node_name in NODE_PROGRESS_TEXT:
                        gave_content = any(update.get(k) for k in SECTION_KEYS)
                        if not gave_content:
                            yield sse({"kind": "SAY", "text": NODE_PROGRESS_TEXT[node_name]})

                    for key in ("destination", "days", "start_date"):
                        if update.get(key):
                            produced[key] = update[key]
    except Exception as e:
        yield sse({"kind": "ERROR", "message": f"这次没跑通：{e}"})
    else:
        # 只有跑完才存，出错的那一轮不存，免得留下半截数据
        saved_chat_id = _save(query, produced, "TRAVEL", chat_id, tenant_id)
        yield sse({"kind": "SAVED", "chat_id": saved_chat_id})
