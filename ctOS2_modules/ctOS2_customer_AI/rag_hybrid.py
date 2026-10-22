import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.rag_keyword import keyword_search
from ctOS2_modules.ctOS2_customer_AI.rag_vector import vector_search

# 第三层检索：把关键词和向量两层按名次加权合并
# 混合后交给模型的片段数上限；两层各取 3 条，最坏 6 条
MAX_HITS = 4


def rank_score(hits: list[str]) -> dict[str, float]:
    """给一层检索结果按名次打分，返回 {片段: 分数}。"""
    # 按名次给分：第 1 名最高
    scores: dict[str, float] = {}
    for position, chunk in enumerate(hits):
        scores[chunk] = max(0, len(hits) - position)
    return scores


def hybrid_search(query: str) -> list[str]:
    """两层检索都跑，按名次加权后返回最相关的几段。"""
    keyword_hits = keyword_search(query)
    vector_hits = vector_search(query)

    # 两层的分数累加到同一张表，key 是片段正文，自然完成去重
    total_scores: dict[str, float] = {}

    for scores in (rank_score(keyword_hits), rank_score(vector_hits)):
        for chunk, score in scores.items():
            total_scores[chunk] = total_scores.get(chunk, 0) + score

    ranked = sorted(total_scores.items(), key=lambda item: item[1], reverse=True)

    return [chunk for chunk, _ in ranked[:MAX_HITS]]


if __name__ == "__main__":
    test_query = "这个项目有哪些模块"
    print(f"提问：{test_query}\n")
    for i, hit in enumerate(hybrid_search(test_query), start=1):
        print(f"{i}. {hit[:60].replace(chr(10), ' ')}")
