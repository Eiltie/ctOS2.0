"""客服的三层检索：关键词（BM25）→ 向量（Chroma）→ 混合加权。

改造前的两个毛病（都在这一个文件里）：
  1. 混合只看名次：两层各自按第几名给分，关键词一个词都没匹配上的块也能进榜。
     结果就是「今天天气怎么样」也能搜出 4 条，模型只能靠提示词硬拒。
  2. 没有相关性信号：检索层永远返回 4 条，上层分不清「有资料」和「没资料」。

现在：
  - BM25 和余弦相似度各自归一化到 0~1，再按权重相加，分数是可比的
  - 低于阈值的块不进结果，「查不到」变成检索层能说出来的事实
  - 结果带 title，模型知道这节属于哪份文档的哪一章
"""

from dataclasses import dataclass

from modules.customer.embedding import embed_one
from modules.customer.rag_store import get_store, tokenize

# 每层各取前几段候选
TOP_K = 8

# 混合后交给模型的片段数上限
MAX_HITS = 4

# 两层混合的权重。用 rag_eval 扫过 0.4 / 0.5 / 0.55 / 0.6 四组关键词权重：
#   0.4：可答题@1 76.7%
#   0.5：可答题@1 80.0%  ← 取这组
# 再往上没有额外收益，反而把语义检索压得太狠（同义改写的题会掉）。
VECTOR_WEIGHT = 0.5
KEYWORD_WEIGHT = 0.5

# 余弦相似度下限：低于这个值认为「语义上也没关系」，不进结果。
# 实测 qwen3-embedding:0.6b 下，库内问题的 top1 一般在 0.55 以上，
# 库外问题（今天天气 / 写个快排）基本在 0.30 以下，0.36 是两者的分界带。
MIN_VECTOR_SCORE = 0.36

# 混合分下限：两层都很弱的时候（关键词 0 分 + 向量刚过线）不要硬凑
MIN_HYBRID_SCORE = 0.28


@dataclass
class Hit:
    """一条检索结果：正文 + 它属于哪一节 + 混合分数。"""

    text: str
    title: str
    score: float

    def as_context(self) -> str:
        """拼成给模型看的段落：先标题路径，再正文。"""
        if self.title:
            return f"【{self.title}】\n{self.text}"
        return self.text


# ---------------------------------------------------------------- 第二层：向量

def embed_query(query: str) -> list[float]:
    """把一句话转成向量。

    真正的转换逻辑在 modules/customer/embedding.py，那里入库和检索共用同一份实现，
    这样就不会出现「入库用了一个模型、检索用了另一个」导致检索永远不准的情况。
    """
    return embed_one(query)


def vector_search(query: str, k: int = TOP_K) -> list[tuple[int, float]]:
    """按余弦相似度从知识库找回最相关的几段，返回 [(块下标, 相似度)]。

    相似度是 0~1 的余弦相似度（集合建库时用的是 cosine 距离），
    低于 MIN_VECTOR_SCORE 的直接丢掉——这就是「查不到」信号的来源。
    """
    collection = get_store().collection

    result = collection.query(
        query_embeddings=[embed_query(query)],
        n_results=k,
        include=["documents", "distances"],
    )

    ids = result["ids"][0]
    # cosine 距离 → 相似度：1 - 距离
    similarities = [1.0 - d for d in result["distances"][0]]

    pairs = []
    for chunk_id, sim in zip(ids, similarities):
        if sim < MIN_VECTOR_SCORE:
            continue
        pairs.append((_chunk_index(chunk_id), sim))
    return pairs


def _chunk_index(chunk_id: str) -> int:
    """把入库时的 id（chunk-12）换回块下标。"""
    return int(str(chunk_id).split("-")[-1])


# ---------------------------------------------------------------- 第一层：关键词

def keyword_search(query: str, k: int = TOP_K) -> list[tuple[int, float]]:
    """BM25 关键词检索，返回 [(块下标, 归一化分数 0~1)]。

    归一化方式：除以本次最高分。这一层只关心「相对谁更强」，
    绝对值随查询长短变化，和向量分数不可直接相加。
    分数为 0 表示一个词都没匹配上，不算命中。
    """
    store = get_store()

    scores = store.bm25.get_scores(tokenize(query))

    ranked = sorted(range(store.total), key=lambda i: scores[i], reverse=True)[:k]
    if not ranked or scores[ranked[0]] <= 0:
        return []

    top = scores[ranked[0]]
    return [(i, scores[i] / top) for i in ranked if scores[i] > 0]


# ---------------------------------------------------------------- 第三层：混合

def hybrid_search(query: str, max_hits: int = MAX_HITS) -> list[Hit]:
    """两层检索都跑，分数加权后返回最相关的几段；一段都没有就返回空列表。

    返回空列表 = 检索层明确说「知识库里没有相关内容」，
    上层据此走拒答分支，而不是硬塞 4 条不相关的给模型。
    """
    store = get_store()

    keyword_hits = keyword_search(query)
    vector_hits = vector_search(query)

    # 两层的分数累加到同一张表，key 是块下标，自然完成去重
    total: dict[int, float] = {}
    for idx, score in keyword_hits:
        total[idx] = total.get(idx, 0.0) + KEYWORD_WEIGHT * score
    for idx, score in vector_hits:
        total[idx] = total.get(idx, 0.0) + VECTOR_WEIGHT * score

    ranked = sorted(total.items(), key=lambda item: item[1], reverse=True)

    hits = []
    for idx, score in ranked:
        if score < MIN_HYBRID_SCORE:
            continue
        hits.append(Hit(
            text=store.chunks[idx],
            title=store.titles[idx] if idx < len(store.titles) else "",
            score=round(score, 4),
        ))
        if len(hits) >= max_hits:
            break

    return hits


if __name__ == "__main__":
    test_query = "这个项目有哪些模块"
    print(f"提问：{test_query}\n")
    found = hybrid_search(test_query)
    if not found:
        print("（检索层判断：知识库里没有相关内容）")
    for i, hit in enumerate(found, start=1):
        print(f"{i}. [{hit.score:.3f}] {hit.title}")
        print(f"   {hit.text[:60].replace(chr(10), ' ')}")
