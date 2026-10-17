"""第三层检索：混合检索（按名次加权）。

把第一层（关键词）和第二层（向量）的结果合到一起，但不再简单地
「关键词排前面、向量排后面」，而是按名次打分后重新排序。

为什么要加权：
    两层各取 3 条，合起来最多 6 条。如果直接按顺序截断，
    关键词那层排第 3 的片段会永远压过向量那层排第 1 的片段，
    这显然不合理——向量层的第一名往往比关键词层的第三名更相关。

打分规则（RRF 思路，简单版）：
    每层第 1 名得 3 分，第 2 名得 2 分，第 3 名得 1 分。
    同一个片段被两层都命中，分数相加。
    最后按总分从高到低取前几条。

这样做的好处：
    只在单层排后面的「万金油片段」（比如各种问题都沾点边的高频词片段）
    总分上不去，会被真正相关的片段压下去。
"""

import sys
from pathlib import Path

# 直接运行本文件时项目根目录不在搜索路径里，先补一次（被 import 时重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.rag_keyword import keyword_search
from ctOS2_modules.ctOS2_customer_AI.rag_vector import vector_search

# 混合后最终交给 LLM 的片段数上限。
# 两层各取 3 条，最坏情况 6 条；这里限制成 4 条，控制提示词长度。
MAX_HITS = 4


def rank_score(hits: list[str]) -> dict[str, float]:
    """给一层的结果按名次打分。

    第 1 名得 3 分，第 2 名得 2 分，第 3 名得 1 分，往后递减到 0 为止。
    返回：{片段正文: 分数}
    """
    scores: dict[str, float] = {}
    for position, chunk in enumerate(hits):
        # 名次越靠前分越高；用 max(0, ...) 兜底，排名超过 3 的不再给分
        scores[chunk] = max(0, len(hits) - position)
    return scores


def hybrid_search(query: str) -> list[str]:
    """同时跑关键词和向量两层，按名次加权后返回最相关的几段。"""
    keyword_hits = keyword_search(query)     # 第一层结果
    vector_hits = vector_search(query)       # 第二层结果

    # 把两层的分数累加到同一张表上（key 是片段正文，自然完成去重）
    total_scores: dict[str, float] = {}

    for scores in (rank_score(keyword_hits), rank_score(vector_hits)):
        for chunk, score in scores.items():
            # 两层都命中的片段，分数相加 —— 这正是"双通道命中更可信"的体现
            total_scores[chunk] = total_scores.get(chunk, 0) + score

    # 按总分从高到低取前 MAX_HITS 条
    ranked = sorted(total_scores.items(), key=lambda item: item[1], reverse=True)

    return [chunk for chunk, _ in ranked[:MAX_HITS]]


if __name__ == "__main__":
    # 手动跑一下：看加权后排序和命中情况
    test_query = "这个项目有哪些模块"
    print(f"提问：{test_query}\n")
    for i, hit in enumerate(hybrid_search(test_query), start=1):
        print(f"{i}. {hit[:60].replace(chr(10), ' ')}")
