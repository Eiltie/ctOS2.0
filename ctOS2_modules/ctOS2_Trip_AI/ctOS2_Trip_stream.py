import json
import sys
from pathlib import Path

from langchain_core.messages import AIMessageChunk

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_databases.ctOS2_db_trip import save_trip_turn
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_create_graph import build_graph
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_main import understand_query

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

# 天气节点第一次调 LLM 是在解析需求，那段的输出是 JSON，不能流给用户
SKIP_FIRST_CALL_NODES = {"weather"}


def sse(event: dict) -> str:
    """把事件打包成一条 SSE 消息（末尾空行即结束）。"""
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


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


def _save(user_query: str, ai_output: dict, turn_kind: str, chat_id):
    """存一轮出行对话，返回所属会话 id；失败只打印。"""
    # 存库失败不能拖垮这一轮：不然用户白等一次规划
    try:
        return save_trip_turn(user_query, ai_output, turn_kind, chat_id=chat_id)
    except Exception as e:
        print(f"[数据库] 出行记录写入失败（不影响本次结果）：{e}")
        return chat_id


async def trip_stream(query: str, history: list[str], chat_id=None):
    """先分流，再跑出行图，边跑边吐 SSE 事件。"""
    # 两个值要分清：query 是用户原话（存库、回显），merged_query 是合并后的需求，只喂给出行图
    kind, merged_query = understand_query(history, query)

    if kind == "CHAT":
        saved_chat_id = _save(query, {"chat_reply": merged_query}, "CHAT", chat_id)
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
                for _, update in payload.items():
                    for key in SECTION_KEYS:
                        if update.get(key):
                            produced[key] = update[key]
                            yield sse({"kind": "DONE", "key": key, "text": update[key]})
                            nxt = NEXT_KEY.get(key)
                            if nxt:
                                yield _step(nxt)

                    for key in ("destination", "days", "start_date"):
                        if update.get(key):
                            produced[key] = update[key]
    except Exception as e:
        yield sse({"kind": "ERROR", "message": f"这次没跑通：{e}"})
    else:
        # 只有跑完才存，出错的那一轮不存，免得留下半截数据
        saved_chat_id = _save(query, produced, "TRAVEL", chat_id)
        yield sse({"kind": "SAVED", "chat_id": saved_chat_id})
