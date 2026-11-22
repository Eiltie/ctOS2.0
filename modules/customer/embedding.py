"""客服｜把文字变成向量（调用本机跑的 Ollama）

做什么：把一段（或一批）文字交给本机的 Ollama，拿回对应的向量。

为什么单独放一个文件：
  这件事有两个使用者——入库脚本（要把上百块文档变成向量）
  和检索（要把用户的一句话变成向量）。
  两处各写一份 HTTP 请求的话，改模型、改地址要改两遍，容易漏。
  集中到这里之后，入库和检索用的是同一份逻辑。

用本地 Ollama 的好处：
  不用密钥、不联网、不花钱；入库上百块文档只要一两秒（走网络要十几秒）。

前置条件：本机要跑着 Ollama，并且已经拉过模型。
    ollama pull qwen3-embedding:0.6b
没跑的话，入库和检索会直接报错，报错里会写清楚怎么办。
"""

import json
import urllib.error
import urllib.request

from modules.customer.rag_config import EMBEDDING_MODEL, embedding_api_url

# 一次最多发几条给向量服务。
#
# 为什么要有上限：一次发太多，显存和模型上下文都可能扛不住。
# 实测这个模型一次 64 条只要 0.73 秒，分批也很够用。
MAX_BATCH = 64

# 单次请求最多等多久（秒）。
# 第一条请求会让模型从硬盘加载进显存，实测要 10 秒左右；
# 之后每条只要几十毫秒。留的余量是为了覆盖第一次加载。
TIMEOUT = 180

# 报错时拼进提示里的说明
_MODEL_HINT = (
    f"请确认本机 Ollama 正在运行，并且已经拉过模型：\n"
    f"    ollama pull {EMBEDDING_MODEL}\n"
    f"如果 Ollama 不在默认地址，请在 .env 里改 OLLAMA_HOST。"
)


class EmbeddingError(RuntimeError):
    """向量服务连不上或者报错。

    单独定一个类型，是为了让上层能看出「是向量服务挂了」，
    而不是别的错，也好在提示里统一写清楚怎么修。
    """


def _post_embed(texts: list[str]) -> list[list[float]]:
    """把一批文字发给 Ollama，返回对应的一批向量。

    请求体里 input 必须是一个列表，哪怕只有一条。
    返回的 embeddings 顺序和传入顺序一致。
    """
    payload = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": texts,
    }).encode("utf-8")

    request = urllib.request.Request(
        embedding_api_url(),
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        # 连不上本机服务：Ollama 没启动、端口写错，都会走这里
        raise EmbeddingError(
            f"连不上本机的向量服务：{e}\n{_MODEL_HINT}"
        ) from e
    except urllib.error.HTTPError as e:
        # 连上了但接口报错：最常见的是模型名写错或者没拉过
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise EmbeddingError(
            f"向量服务返回错误（HTTP {e.code}）：{detail}\n{_MODEL_HINT}"
        ) from e

    embeddings = body.get("embeddings") or []
    if len(embeddings) != len(texts):
        raise EmbeddingError(
            f"向量服务返回了 {len(embeddings)} 条向量，但传进去的是 {len(texts)} 条文字。\n"
            f"这通常说明模型名写错了，检查 OLLAMA_EMBED_MODEL 是不是一个 embedding 模型。"
        )

    return embeddings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把一批文字转成向量，返回顺序与传入一致。

    会按 MAX_BATCH 分批：一次发太多，显存和上下文都可能扛不住。
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []
    for start in range(0, len(texts), MAX_BATCH):
        batch = texts[start:start + MAX_BATCH]
        all_embeddings.extend(_post_embed(batch))

    return all_embeddings


def embed_one(text: str) -> list[float]:
    """把一句话转成向量。检索时用这个。"""
    embeddings = _post_embed([text or ""])
    return embeddings[0]


if __name__ == "__main__":
    # 单独跑这个文件 = 检查本地向量服务通不通、维度是多少
    # 命令：python -X utf8 -m modules.customer.embedding
    print(f"模型：{EMBEDDING_MODEL}")
    print(f"地址：{embedding_api_url()}")

    try:
        vectors = embed_texts(["端口怎么改", "数据库有几张表"])
    except EmbeddingError as e:
        print(f"\n检查失败：\n{e}")
        raise SystemExit(1)

    print(f"\n检查通过：返回 {len(vectors)} 条向量，每条 {len(vectors[0])} 维")
