"""知识库的加载与复用（全模块只加载一次）。

为什么要有这个文件：
    关键词检索要看到全部文本，向量检索要连上 Chroma。
    如果每次提问都重新开库、重新读文本、重新分词，就是纯浪费——
    这些数据在程序运行期间根本不会变，加载一次就够了。

用法：
    程序启动时调一次 load_store()，之后检索层随时用 get_store() 取现成的数据。
"""

import sys
from pathlib import Path

import chromadb
import jieba
from rank_bm25 import BM25Okapi

# 直接运行本文件时项目根目录不在搜索路径里，先补一次（被 import 时重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.get_llm import (
    CHROMA_DIR,
    COLLECTION_NAME,
    get_zhipu_api_key,
)


class KnowledgeStore:
    """一份加载好的知识库，装着检索层需要的东西。

    属性：
        client      —— Chroma 客户端（向量检索用它查）
        collection  —— 知识库集合（向量检索用它查）
        chunks      —— 全部文本片段（关键词检索用）
        bm25        —— 已经建好的 BM25 索引（关键词检索用）
        total       —— 一共多少块（启动检查时报告用）
    """

    def __init__(self, client, collection, chunks: list[str], bm25):
        self.client = client
        self.collection = collection
        self.chunks = chunks
        self.bm25 = bm25
        self.total = len(chunks)


# 加载好的知识库。没加载过时是 None，加载过就一直放在这里复用。
_store: KnowledgeStore | None = None


def tokenize(text: str) -> list[str]:
    """把一句中文切成词表，供 BM25 比对。

    例："项目有哪些模块" -> ["项目", "有", "哪些", "模块"]
    """
    return [word for word in jieba.lcut(text) if word.strip()]


def load_store() -> KnowledgeStore:
    """加载知识库。启动时调一次，之后所有检索都复用这份。

    加载的过程顺便就是"启动检查"：向量库在不在、有没有内容、
    智谱密钥配没配，出了问题在这里就说清楚，不用等到用户提问才报错。

    出问题时抛 RuntimeError，错误信息里带上"怎么办"。
    """
    global _store
    if _store is not None:
        return _store                      # 已经加载过，直接给现成的

    # ① 检查智谱密钥（向量检索要用它把问题转成向量）
    get_zhipu_api_key()

    # ② 检查向量库目录存不存在
    if not CHROMA_DIR.exists():
        raise RuntimeError(
            f"没找到向量数据库：{CHROMA_DIR}\n"
            f"请先运行一次入库脚本：\n"
            f"    python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py"
        )

    # ③ 打开 Chroma，检查集合在不在
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    existing_names = [c.name for c in client.list_collections()]
    if COLLECTION_NAME not in existing_names:
        raise RuntimeError(
            f"向量数据库里没有「{COLLECTION_NAME}」这个集合。\n"
            f"请先运行一次入库脚本：\n"
            f"    python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py"
        )

    collection = client.get_collection(COLLECTION_NAME)

    # ④ 读出全部文本，检查是不是空的
    chunks = collection.get(include=["documents"])["documents"]
    if not chunks:
        raise RuntimeError(
            "向量数据库是空的（一块内容都没有）。\n"
            "请先运行一次入库脚本：\n"
            "    python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py"
        )

    # ⑤ 把每段文本切成词表，建好 BM25 索引（一次性建好，之后只管查）
    corpus = [tokenize(chunk) for chunk in chunks]
    bm25 = BM25Okapi(corpus)

    _store = KnowledgeStore(client, collection, chunks, bm25)
    return _store


def get_store() -> KnowledgeStore:
    """取已经加载好的知识库。没加载过就先加载。"""
    if _store is None:
        return load_store()
    return _store


def reset_store() -> None:
    """丢掉已加载的知识库，下次用时重新加载。

    重新入库（跑了 rag_ingest.py）之后如果不想重启程序，可以调这个。
    """
    global _store
    _store = None


if __name__ == "__main__":
    # 单独运行本文件 = 做一次启动检查
    try:
        store = load_store()
        print(f"知识库检查通过：{store.total} 块内容，已建好 BM25 索引")
    except RuntimeError as e:
        print(f"知识库检查失败：\n{e}")
