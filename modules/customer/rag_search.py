"""客服的三层检索：关键词（BM25）→ 向量（Chroma）→ 混合加权。

原来拆在三个文件里（rag_keyword / rag_vector / rag_hybrid），
其中 rag_keyword 只有 17 行、rag_hybrid 只有 31 行，都是对 rag_store 的薄封装，
打开文件的开销比读函数还大。合并后三层放在一起，一眼能看出它们的关系。

三层都跑是为了方便调试（终端里能看到每层命中），
但真正交给模型写答案的只有第三层 hybrid_search()。
"""

import json
import urllib.request

from modules.customer.rag_config import (
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    get_zhipu_api_key,
)
from modules.customer.rag_store import get_store, tokenize

# 每层各取前几段
TOP_K = 3

# 混合后交给模型的片段数上限；两层各取 3 条，最坏 6 条
MAX_HITS = 4


# ---------------------------------------------------------------- 第二层：向量

def embed_query(query: str) -> list[float]:
    """调智谱接口把一句话转成向量，返回向量。"""
    api_key = get_zhipu_api_key()

    payload = json.dumps({"model": EMBEDDING_MODEL, "input": [query]}).encode("utf-8")

    request = urllib.request.Request(
        EMBEDDING_BASE_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))

    return body["data"][0]["embedding"]


def vector_search(query: str) -> list[str]:
    """按语义相似度从知识库找回最相关的几段。"""
    collection = get_store().collection

    result = collection.query(
        query_embeddings=[embed_query(query)],
        n_results=TOP_K,
        include=["documents"],
    )

    # Chroma 返回「每个查询一组」的二维结构，这里只有一条查询
    return result["documents"][0]


# ---------------------------------------------------------------- 第一层：关键词

def keyword_search(query: str) -> list[str]:
    """BM25 关键词检索：对专有名词（MAX_HITS、rag_ingest 这类）最准。"""
    store = get_store()

    scores = store.bm25.get_scores(tokenize(query))

    ranked = sorted(range(store.total), key=lambda i: scores[i], reverse=True)

    # 分数为 0 表示一个词都没匹配上，不算命中
    top_indexes = [i for i in ranked[:TOP_K] if scores[i] > 0]

    return [store.chunks[i] for i in top_indexes]


# ---------------------------------------------------------------- 第三层：混合

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
