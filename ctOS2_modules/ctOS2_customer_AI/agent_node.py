import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.agent_state import AgentState
from ctOS2_modules.ctOS2_customer_AI.get_llm import get_llm
from ctOS2_modules.ctOS2_customer_AI.promtps import ANSWER_PROMPT
from ctOS2_modules.ctOS2_customer_AI.rag_hybrid import hybrid_search
from ctOS2_modules.ctOS2_customer_AI.rag_keyword import keyword_search
from ctOS2_modules.ctOS2_customer_AI.rag_vector import vector_search

# 客服图的节点：retrieve 检索、generate 生成，一条直线走到底


def retrieve_node(state: AgentState) -> dict:
    """检索节点：三层检索都跑一遍，结果一起写进 state。"""
    query = state["user_query"]

    keyword_hits = keyword_search(query)
    vector_hits = vector_search(query)
    hybrid_hits = hybrid_search(query)

    return {
        "keyword_hits": keyword_hits,
        "vector_hits": vector_hits,
        "hybrid_hits": hybrid_hits,
    }


def generate_node(state: AgentState) -> dict:
    """生成节点：用混合检索的片段让模型写回答。"""
    hits = state["hybrid_hits"]

    # 一段都没检索到时给句占位，别让提示词里留空白
    context = "\n\n---\n\n".join(hits) if hits else "（没有检索到任何资料）"

    prompt = (ANSWER_PROMPT
              .replace("{context}", context)
              .replace("{user_query}", state["user_query"]))

    answer = get_llm().invoke(prompt).content.strip()

    return {"answer": answer}
