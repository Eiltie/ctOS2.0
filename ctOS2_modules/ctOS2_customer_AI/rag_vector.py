"""第二层检索：向量数据库检索（Chroma + 智谱 embedding）。

把问题和知识库里的每段文本都变成向量，找语义最接近的几段。
好处是问法和文档用词不一样时也能命中（比如问"这是什么系统"，能匹配到"多模块 AI 应用"）。

Chroma 客户端由 rag_store 在启动时打开，这里只管查。
"""

import json
import sys
import urllib.request
from pathlib import Path

# 直接运行本文件时项目根目录不在搜索路径里，先补一次（被 import 时重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.get_llm import (
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    get_zhipu_api_key,
)
from ctOS2_modules.ctOS2_customer_AI.rag_store import get_store

# 每次检索返回几条。三层都取同样条数，混合时才好比较。
TOP_K = 3


def embed_query(query: str) -> list[float]:
    """把用户这一句话转成向量（和入库时用的是同一个模型，维度必须一致）。"""
    api_key = get_zhipu_api_key()

    # 请求体：模型名 + 待向量化的文本
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
    """按语义相似度从知识库里找回最相关的几段文本。"""
    collection = get_store().collection          # 启动时已打开的集合

    result = collection.query(
        query_embeddings=[embed_query(query)],   # 用问题向量去查
        n_results=TOP_K,                         # 要几条
        include=["documents"],                   # 只要正文
    )

    # Chroma 返回的是"每个查询一组"的二维结构，我们只有一条查询，所以取 [0]
    return result["documents"][0]


if __name__ == "__main__":
    for hit in vector_search("这个项目有哪些模块"):
        print("-", hit[:60].replace("\n", " "))
