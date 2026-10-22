import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.get_llm import (
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    get_zhipu_api_key,
)

# 第二层检索：Chroma 向量库 + 智谱 embedding，换个说法也能命中
from ctOS2_modules.ctOS2_customer_AI.rag_store import get_store

TOP_K = 3


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


if __name__ == "__main__":
    for hit in vector_search("这个项目有哪些模块"):
        print("-", hit[:60].replace("\n", " "))
