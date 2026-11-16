"""智能出行｜Agent 唯一的那个节点

做什么：读这一圈的消息，判断该自己答还是交给某个能力，把判断和回复写成一条 AIMessage。
被谁用：modules/trip/graph.py 注册成节点。

判断结果放在 AIMessage 的 additional_kwargs 里（action / query），
这样状态仍然只有 messages，"这一圈要干什么"也跟着消息一起走——
和 LangChain 里 tool_calls 挂在消息上是同一个思路。
"""

import json

from langchain_core.messages import AIMessage

from core.llm import get_llm
from modules.trip.prompts import AGENT_PROMPT
from modules.trip.state import TripState

# 判断不出来时用的兜底回复
FALLBACK_REPLY = ("这句我还没完全听懂。你可以说得具体一点："
                  "想去哪玩几天，或者从哪到哪怎么走。")

# 允许的三个动作
ACTIONS = ("answer", "route", "guide")


def _history_text(messages):
    """把这一圈之前用户说过的话拼成文本（不含最后一句）。"""
    humans = [m.content for m in messages if m.type == "human"]
    earlier = humans[:-1]
    return "\n".join(earlier) if earlier else "（还没聊过）"


def _last_user_text(messages):
    """最后一句用户说的话。"""
    for message in reversed(messages):
        if message.type == "human":
            return message.content or ""
    return ""


def _parse(raw):
    """解析模型输出的 JSON；解析失败返回 None。"""
    text = (raw or "").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, AttributeError):
        return None

    return data if isinstance(data, dict) else None


def decide_node(state: TripState) -> dict:
    """这一圈做什么：自己答、交给路线、还是交给攻略。

    只调一次模型：要答的那类本来就得生成文字，没必要判一次再答一次。
    extra 是调用方给的补充信息（比如已经查好的真实天气），
    模型看不到它就会编天气，所以有就一定要喂进去。
    """
    messages = state["messages"]
    query = _last_user_text(messages)
    history = _history_text(messages)
    extra = state.get("extra_context") or "（没有额外信息）"

    prompt = (AGENT_PROMPT
              .replace("{history}", history)
              .replace("{query}", query)
              .replace("{extra}", extra))

    raw = get_llm().with_config(tags=["internal"]).invoke(prompt).content
    data = _parse(raw)

    # 解析失败：别把用户晾着，按"自己答"处理，把模型写的内容直接用上
    if data is None:
        action, reply, merged = "answer", (raw or "").strip() or FALLBACK_REPLY, ""
    else:
        action = str(data.get("action") or "").strip().lower()
        if action not in ACTIONS:
            action = "answer"
        reply = str(data.get("reply") or "").strip()
        merged = str(data.get("query") or "").strip()

    # 交给能力的两种，必须有一个能独立看懂的需求；没有就退回来自己答
    if action in ("route", "guide") and not merged:
        action, reply, merged = "answer", reply or FALLBACK_REPLY, ""

    if action == "answer" and not reply:
        reply = FALLBACK_REPLY

    return {
        "messages": [AIMessage(
            content=reply,
            additional_kwargs={"action": action, "query": merged},
        )],
        "node_path": ["decide"],
    }
