import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.rag_store import get_store, tokenize

# 第一层检索：jieba 分词 + BM25 排序，对专有名词最准

TOP_K = 3


def keyword_search(query: str) -> list[str]:
    """BM25 关键词检索：按词命中率找回最相关的几段。"""
    store = get_store()

    scores = store.bm25.get_scores(tokenize(query))

    ranked = sorted(range(store.total), key=lambda i: scores[i], reverse=True)

    # 分数为 0 表示一个词都没匹配上，不算命中
    top_indexes = [i for i in ranked[:TOP_K] if scores[i] > 0]

    return [store.chunks[i] for i in top_indexes]


if __name__ == "__main__":
    for hit in keyword_search("这个项目有哪些模块"):
        print("-", hit[:60].replace("\n", " "))
