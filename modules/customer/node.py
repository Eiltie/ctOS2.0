"""客服｜两个图节点

做什么：retrieve 跑三层检索，generate 用检索结果 + 历史写答案。
被谁用：modules/customer/graph.py 注册为节点。
"""

from modules.customer.state import AgentState
from core.llm import get_llm
from modules.customer.prompts import ANSWER_PROMPT
from modules.customer.rag_search import (
    hybrid_search,
    keyword_search,
    vector_search,
)

# 客服图的节点：retrieve 检索、generate 生成，一条直线走到底
#
# 关于历史的两个用法（很重要）：
#   1. 检索：用「当前问题 + 上一轮的原问题」一起去搜。
#      因为「那它怎么配」这句话本身没有关键词，单搜搜不到东西。
#      拼上上一轮的原问题，就能搜到相关的资料。
#   2. 生成：把历史给模型，让它理解「它」指什么。

# 带进提示词的历史轮数（一问一答算一轮）
HISTORY_TURNS = 3


def _last_question(history: list[dict]) -> str:
    """从历史里找上一条用户提问，用于补全模糊的追问。"""
    for item in reversed(history):
        if item.get("role") == "user" and item.get("content"):
            return item["content"]
    return ""


def _build_search_query(query: str, history: list[dict]) -> str:
    """拼出检索用的查询串。

    为什么不直接用 query：
      「那它怎么配」里没有「配置」「端口」这些能检索到的词，
      单搜只会搜到一堆无关内容，模型也就答不出来。

    策略：当前问题 + 上一轮用户问题，用空格拼起来。
      多了会稀释相关性，所以最多带一条。
    """
    last_q = _last_question(history)
    if last_q and last_q != query:
        return f"{last_q} {query}"
    return query


def _format_history(history: list[dict]) -> str:
    """把历史格式化成提示词里的一段文字，只取最近几轮。"""
    if not history:
        return "（这是第一句，没有历史）"

    # 只取最近 HISTORY_TURNS 轮（一问一答），太长的历史会挤占上下文
    recent = history[-HISTORY_TURNS * 2:]

    lines = []
    for item in recent:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        speaker = "用户" if role == "user" else "客服"
        lines.append(f"{speaker}：{content}")

    return "\n".join(lines) if lines else "（这是第一句，没有历史）"


def retrieve_node(state: AgentState) -> dict:
    """检索节点：三层检索都跑一遍，结果一起写进 state。"""
    query = state["user_query"]
    history = state.get("history") or []

    # 用「上一轮问题 + 当前问题」去检索，解决追问搜不到的问题
    search_query = _build_search_query(query, history)

    keyword_hits = keyword_search(search_query)
    vector_hits = vector_search(search_query)
    hybrid_hits = hybrid_search(search_query)

    return {
        "keyword_hits": keyword_hits,
        "vector_hits": vector_hits,
        "hybrid_hits": hybrid_hits,
    }


def generate_node(state: AgentState) -> dict:
    """生成节点：用混合检索的片段让模型写回答。"""
    hits = state["hybrid_hits"]
    history = state.get("history") or []

    # 一段都没检索到时给句占位，别让提示词里留空白
    context = "\n\n---\n\n".join(hits) if hits else "（没有检索到任何资料）"

    prompt = (ANSWER_PROMPT
              .replace("{history}", _format_history(history))
              .replace("{context}", context)
              .replace("{user_query}", state["user_query"]))

    answer = get_llm().invoke(prompt).content.strip()

    return {"answer": answer}
