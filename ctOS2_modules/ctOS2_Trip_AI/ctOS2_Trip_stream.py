"""智能出行 · 流式封装（对应闲聊侧的 ctOS_chat_graphOn.py）。

对外只暴露一个东西：

    trip_stream(query, history)  ->  async 生成器，吐 SSE 文本片段

调用方（ctOS_chat_api.py 的 /trip/chat）拿它直接塞进 StreamingResponse 就行，
不需要知道图长什么样、有几段产出、哪个节点该过滤——那些事全在本文件里。

事件协议（前端按 kind 分派）：
    START  开始跑图（前端亮出四段卡片）
    STEP   某一段在忙、暂时没文字（前端显示"正在…"）
    TOKEN  逐字碎片，带 key 说明属于哪一段（打字机效果）
    DONE   某一段整段定稿（前端用它重渲染，纠正逐字拼接的偏差）
    CHAT   判定为闲聊，直接回一句，**不跑图**
    ERROR  跑图途中出错（已产生的段落保留，末尾补一条说明）
"""

import json
import sys
from pathlib import Path

from langchain_core.messages import AIMessageChunk

# 直接运行本文件时，项目根目录不在搜索路径里，补一次（被 import 时重复无害）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_databases.ctOS2_db_trip import save_trip_turn
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_create_graph import build_graph
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_main import understand_query

MAX_TOKENS = 50000       # 单个节点的逐字上限

# 编译一次，之后所有请求复用（编译有开销）
trip_graph = build_graph()

# 进图时初始 state
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

#表：图长什么样（改图结构时改这一块）

SECTION_KEYS = ("weather", "spots", "itinerary", "route_plan")

# 逐字碎片凭这张表决定贴到页面哪一段（表外节点不产正文，如 tools）
NODE_TO_KEY = {
    "weather": "weather",
    "spots_agent": "spots",      
    "planner": "itinerary",
    "route_agent": "route_plan",
}

# 静默时段（模型思考、工具执行）的进度提示
STEP_TEXT = {
    "weather": "正在查询天气…",
    "spots": "正在搜集景点资料…",
    "itinerary": "正在安排行程…",
    "route_plan": "正在规划路线…",
}

# 这段跑完轮到谁——前端进度轨道靠它提前亮下一格
NEXT_KEY = {
    "weather": "spots",
    "spots": "itinerary",
    "itinerary": "route_plan",
}

SKIP_FIRST_CALL_NODES = {"weather"}

# 打包 

def sse(event: dict) -> str:
    """把事件数据打包成一条 SSE 消息（末尾空行即本条结束）。"""
    # ensure_ascii=False：中文原样发送，不转成 \uXXXX
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def _step(key: str) -> str:
    """打包一条进度提示（STEP）事件。"""
    return sse({"kind": "STEP", "key": key, "text": STEP_TEXT[key]})


def _keep(node: str, chunk, blocked_node: dict) -> bool:
    """这一小段文字该不该流给用户。

    四道过滤：① 表外节点跳过 ② 只要 AIMessageChunk（挡开场白提示词这类整条消息）
    ③ 带 tool_call_chunks 的是 ReAct 中间轮的工具参数，跳过
    ④ 内部调用（该节点第一次 LLM 调用）整次不放行
    """
    if node not in NODE_TO_KEY or not isinstance(chunk, AIMessageChunk):
        return False
    if chunk.tool_call_chunks or not chunk.content:
        return False

    rid = getattr(chunk, "id", None)
    if node in SKIP_FIRST_CALL_NODES and node not in blocked_node:
        blocked_node[node] = rid          # 只登记第一次，之后不再改
    return not (node in blocked_node and rid == blocked_node[node])


def _save(user_query: str, ai_output: dict, turn_kind: str) -> None:
    """把这一轮存进数据库。

    存数据库失败【绝不】影响跑图和前端输出 —— 只是少一条历史记录，
    不该让用户这一轮的规划白跑。所以异常在这里就地吃掉。
    """
    try:
        save_trip_turn(user_query, ai_output, turn_kind)
    except Exception as e:
        print(f"[数据库] 出行记录写入失败（不影响本次结果）：{e}")


#对外唯一入口

async def trip_stream(query: str, history: list[str]):
    """跑一次出行图，边跑边吐 SSE 文本片段。

    进图前先分流：出行需求就把多轮对话合并成一句完整需求；是闲聊就直接回、不跑图。
    （口径与终端入口 ctOS2_Trip_main.understand_query 完全一致。）
    """
    kind, content = understand_query(history, query)

    if kind == "CHAT":
        # 闲聊不跑图，但同样是一轮对话，照样存库（turn_kind = CHAT）
        _save(query, {"chat_reply": content}, "CHAT")
        yield sse({"kind": "CHAT", "message": content})
        return

    yield sse({"kind": "START", "query": content})
    yield _step("weather")               # 开工第一个节点必是天气
    blocked_node: dict[str, str] = {}    # 节点名 -> 被判为内部调用的那个 run id
    tokens: dict[str, int] = {}          # 各段已推送的字数（上限用）
    produced: dict[str, str] = {}        # 四段产出 + 出行要素，跑完拿去存库

    try:
        for mode, payload in trip_graph.stream(
            {**INITIAL_STATE, "user_query": content},
            stream_mode=["updates", "messages"],
        ):
            # ① 逐字流入：payload = (消息片段, 元信息)
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

            # ② 整段流入：某节点跑完，推它的完整产出
            else:
                for _, update in payload.items():
                    for key in SECTION_KEYS:
                        if update.get(key):
                            produced[key] = update[key]      # 留一份给存库用
                            yield sse({"kind": "DONE", "key": key, "text": update[key]})
                            nxt = NEXT_KEY.get(key)
                            if nxt:              # 该段完成 → 亮下一段提示
                                yield _step(nxt)

                    # 目的地/天数/出发日期由天气节点解析出来，一起留着存库
                    for key in ("destination", "days", "start_date"):
                        if update.get(key):
                            produced[key] = update[key]
    except Exception as e:
        yield sse({"kind": "ERROR", "message": f"这次没跑通：{e}"})
    else:
        # 图跑完了才存，出错的那一轮不存（免得存进半截数据）
        _save(content, produced, "TRAVEL")
