"""图的节点：检索、生成。

每个节点都是"收一份 state，返回要更新的那几个字段"，LangGraph 负责合并。
"""

import sys
from pathlib import Path

# 直接运行本文件时项目根目录不在搜索路径里，先补一次（被 import 时重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.agent_state import AgentState
from ctOS2_modules.ctOS2_customer_AI.get_llm import get_llm
from ctOS2_modules.ctOS2_customer_AI.promtps import ANSWER_PROMPT
from ctOS2_modules.ctOS2_customer_AI.rag_hybrid import hybrid_search
from ctOS2_modules.ctOS2_customer_AI.rag_keyword import keyword_search
from ctOS2_modules.ctOS2_customer_AI.rag_vector import vector_search


def retrieve_node(state: AgentState) -> dict:
    """检索节点：把三层检索依次跑一遍，结果都写进 state。

    三层都跑、都留着，是为了在终端里能看清每一层各命中了什么，方便调参。
    真正交给生成节点用的是第三层（混合）。
    """
    query = state["user_query"]         # 用户这一轮的问题

    keyword_hits = keyword_search(query)     # 第一层：关键词
    vector_hits = vector_search(query)       # 第二层：向量
    hybrid_hits = hybrid_search(query)       # 第三层：混合

    return {
        "keyword_hits": keyword_hits,
        "vector_hits": vector_hits,
        "hybrid_hits": hybrid_hits,
    }


def generate_node(state: AgentState) -> dict:
    """生成节点：拿混合检索的片段让 LLM 写回答。

    检索不到时照样问 LLM——提示词里写死了"没有资料就回答没找到"，
    这样"答不出来"这句话也由模型统一输出，不用在代码里写分支。
    """
    hits = state["hybrid_hits"]         # 混合检索的片段

    # 把多段资料拼成一块文本；一段都没有就写一句说明，避免提示词里出现空白
    context = "\n\n---\n\n".join(hits) if hits else "（没有检索到任何资料）"

    prompt = (ANSWER_PROMPT
              .replace("{context}", context)
              .replace("{user_query}", state["user_query"]))

    answer = get_llm().invoke(prompt).content.strip()

    return {"answer": answer}
