"""客服｜知识库加载层

做什么：全进程只加载一次 Chroma 集合和 BM25 索引，三层检索共享这一份。
被谁用：rag_search.py 的 get_store()。

每个块除了正文还带着一行「标题路径」（文件 › 一级标题 › 二级标题）：
  - 检索时拼进结果，模型看得到这节属于哪份文档的哪一章
  - BM25 也给标题路径单独建一份索引，标题里的词（比如「部署」）直接可搜
"""

from pathlib import Path

import chromadb
import jieba
from rank_bm25 import BM25Okapi


from modules.customer.rag.rag_config import (
    CHROMA_DIR,
    COLLECTION_NAME,
)

# 知识库加载层：全模块只加载一次，三层检索都从这里取现成的数据


class KnowledgeStore:
    def __init__(self, client, collection, chunks, titles, sources, bm25):
        """把检索层要用的东西装进来，并记下总块数。"""
        self.client = client
        self.collection = collection
        self.chunks = chunks
        self.titles = titles
        self.sources = sources
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

    if not CHROMA_DIR.exists():
        raise RuntimeError(
            f"没找到向量数据库：{CHROMA_DIR}\n"
            f"请先运行一次入库脚本：\n"
            f"    python -X utf8 -m modules.customer.rag.rag_ingest"
        )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    existing_names = [c.name for c in client.list_collections()]
    if COLLECTION_NAME not in existing_names:
        raise RuntimeError(
            f"向量数据库里没有「{COLLECTION_NAME}」这个集合。\n"
            f"请先运行一次入库脚本：\n"
            f"    python -X utf8 -m modules.customer.rag.rag_ingest"
        )

    collection = client.get_collection(COLLECTION_NAME)

    got = collection.get(include=["documents", "metadatas"])
    chunks = got["documents"]
    if not chunks:
        raise RuntimeError(
            "向量数据库是空的（一块内容都没有）。\n"
            "请先运行一次入库脚本：\n"
            "    python -X utf8 -m modules.customer.rag.rag_ingest"
        )

    metadatas = got.get("metadatas") or [{} for _ in chunks]
    # 老库（改版前入库的）没有 title 字段，退化成只用文件名，不至于报错
    titles = [(m or {}).get("title") or "" for m in metadatas]
    sources = [(m or {}).get("source") or "" for m in metadatas]

    # BM25 索引的是「标题路径 + 正文」：标题里的词也能被关键词检索命中
    corpus = [tokenize(_index_text(t, c)) for t, c in zip(titles, chunks)]
    bm25 = BM25Okapi(corpus)

    _store = KnowledgeStore(client, collection, chunks, titles, sources, bm25)
    return _store


def _index_text(title: str, chunk: str) -> str:
    """BM25 建索引和打分共用的文本：标题路径 + 正文。"""
    return f"{title}\n{chunk}" if title else chunk


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
