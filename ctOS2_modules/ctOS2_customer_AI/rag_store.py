import sys
from pathlib import Path

import chromadb
import jieba
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.get_llm import (
    CHROMA_DIR,
    COLLECTION_NAME,
    get_zhipu_api_key,
)

# 知识库加载层：全模块只加载一次，三层检索都从这里取现成的数据


class KnowledgeStore:
    def __init__(self, client, collection, chunks: list[str], bm25):
        """把检索层要用的东西装进来，并记下总块数。"""
        self.client = client
        self.collection = collection
        self.chunks = chunks
        self.bm25 = bm25
        self.total = len(chunks)


_store: KnowledgeStore | None = None


def tokenize(text: str) -> list[str]:
    """把一句中文切成词表，供 BM25 比对。"""
    return [word for word in jieba.lcut(text) if word.strip()]


def load_store() -> KnowledgeStore:
    """加载知识库（顺便做启动检查），已加载过就直接返回；失败抛 RuntimeError。"""
    global _store
    if _store is not None:
        return _store

    get_zhipu_api_key()

    if not CHROMA_DIR.exists():
        raise RuntimeError(
            f"没找到向量数据库：{CHROMA_DIR}\n"
            f"请先运行一次入库脚本：\n"
            f"    python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py"
        )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    existing_names = [c.name for c in client.list_collections()]
    if COLLECTION_NAME not in existing_names:
        raise RuntimeError(
            f"向量数据库里没有「{COLLECTION_NAME}」这个集合。\n"
            f"请先运行一次入库脚本：\n"
            f"    python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py"
        )

    collection = client.get_collection(COLLECTION_NAME)

    chunks = collection.get(include=["documents"])["documents"]
    if not chunks:
        raise RuntimeError(
            "向量数据库是空的（一块内容都没有）。\n"
            "请先运行一次入库脚本：\n"
            "    python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py"
        )

    corpus = [tokenize(chunk) for chunk in chunks]
    bm25 = BM25Okapi(corpus)

    _store = KnowledgeStore(client, collection, chunks, bm25)
    return _store


def get_store() -> KnowledgeStore:
    """取已加载的知识库，没加载过就先加载。"""
    if _store is None:
        return load_store()
    return _store


def reset_store() -> None:
    """丢掉缓存，下次用时重新加载（重新入库后调用）。"""
    global _store
    _store = None


if __name__ == "__main__":
    try:
        store = load_store()
        print(f"知识库检查通过：{store.total} 块内容，已建好 BM25 索引")
    except RuntimeError as e:
        print(f"知识库检查失败：\n{e}")
