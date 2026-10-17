"""第一层检索：关键词检索（jieba 分词 + BM25 排序）。

BM25 是衡量「查询词和文档有多相关」的经典算法，纯靠词频，不需要向量。
知识库小的时候它很快，而且对专有名词（比如 ctOS、chroma）特别准。

文本和 BM25 索引都由 rag_store 在启动时准备好，这里只管查。
"""

import sys
from pathlib import Path

# 直接运行本文件时项目根目录不在搜索路径里，先补一次（被 import 时重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.rag_store import get_store, tokenize

# 每次检索返回几条。三层都取同样条数，混合时才好比较。
TOP_K = 3


def keyword_search(query: str) -> list[str]:
    """按关键词从知识库里找回最相关的几段文本。"""
    store = get_store()          # 启动时已加载好的知识库

    # 把用户问题也切成词表，和库里的词表比对
    scores = store.bm25.get_scores(tokenize(query))

    # 按分数从高到低排序，取前 TOP_K 段
    ranked = sorted(range(store.total), key=lambda i: scores[i], reverse=True)

    # 分数为 0 表示一个词都没匹配上，这种不算命中
    top_indexes = [i for i in ranked[:TOP_K] if scores[i] > 0]

    return [store.chunks[i] for i in top_indexes]


if __name__ == "__main__":
    for hit in keyword_search("这个项目有哪些模块"):
        print("-", hit[:60].replace("\n", " "))
