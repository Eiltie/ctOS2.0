"""入库脚本：把 data/docs/ 下的文档切块、向量化，存进 Chroma。

这是一次性脚本，改动文档后手动重跑一次即可：
    python ctOS2_modules/ctOS2_customer_AI/rag_ingest.py

本模块不做数据库入库、不做保存功能，知识只落在本地 Chroma 目录里。
"""

import json
import sys
import urllib.request
from pathlib import Path

import chromadb

# 直接运行本文件时（python rag_ingest.py），项目根目录不在搜索路径里，
# 下面那行包路径就 import 不到。先补一次（被 import 时加的是同一个，重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.get_llm import (
    CHROMA_DIR,
    COLLECTION_NAME,
    DOCS_DIR,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    get_zhipu_api_key,
)

# 单块最大字符数。文档切块时超过它就再切开，避免一块塞太多内容、检索不准。
MAX_CHUNK_CHARS = 600

# 一次请求最多送几条去向量化。智谱 embedding 接口的硬限制是 64，
# 超过会直接 HTTP 400（error code 1214：input 数组最大不得超过 64 条）。
# 所以文档多到 64 块以上时必须分批，分批逻辑在 embed_texts() 里。
MAX_EMBED_BATCH = 64


def split_markdown(text: str) -> list[str]:
    """把一篇 Markdown 按二级标题（## ）切成块。

    每块自带标题，读起来是完整的一小节。
    标题下内容太长（比如目录结构那种大代码块）时再按【行】分组，
    保证不会从句子中间劈开。
    """
    # 按行扫描，遇到 "## " 就另起一块
    sections: list[str] = []        # 按标题切好的小节
    current_lines: list[str] = []   # 当前正在攒的这一小节

    for line in text.splitlines():
        if line.startswith("## "):
            # 遇到新标题：先把攒好的上一节收走
            if current_lines:
                sections.append("\n".join(current_lines))
                current_lines = []
        current_lines.append(line)

    if current_lines:               # 收尾：最后一节
        sections.append("\n".join(current_lines))

    # 去掉空白节；过长的节按行累积，攒够 MAX_CHUNK_CHARS 就切成一块
    result: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= MAX_CHUNK_CHARS:
            result.append(section)
            continue

        part_lines: list[str] = []  # 正在攒的这一块的行
        part_len = 0                # 这一块已有多少字符
        for line in section.splitlines():
            part_lines.append(line)
            part_len += len(line) + 1
            if part_len >= MAX_CHUNK_CHARS:
                result.append("\n".join(part_lines))
                part_lines = []
                part_len = 0
        if part_lines:              # 收尾：这一节剩下的行
            result.append("\n".join(part_lines))

    return result


def embed_batch(texts: list[str]) -> list[list[float]]:
    """调智谱接口，把【一小批】文本转成向量。返回的顺序和传入顺序一一对应。

    注意：texts 最多 MAX_EMBED_BATCH 条，超了接口会直接返回 400。
    调用方是 embed_texts()，它负责分批。
    """
    api_key = get_zhipu_api_key()

    # 请求体：模型名 + 要向量化的文本
    payload = json.dumps({"model": EMBEDDING_MODEL, "input": texts}).encode("utf-8")

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

    # 接口返回里带 index，按 index 排一遍保证顺序对得上
    items = sorted(body["data"], key=lambda item: item["index"])
    return [item["embedding"] for item in items]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把一批文本转成向量，内部按 MAX_EMBED_BATCH 分批调接口。

    为什么必须分批：智谱 embedding 接口限制 input 数组最多 64 条，
    一次提交 65 条以上会直接 HTTP 400（error code 1214：input 数组最大不得超过 64 条）。
    文档越写越多，块数迟早超过 64，所以这里统一分批，调用方不用关心。
    """
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), MAX_EMBED_BATCH):
        embeddings.extend(embed_batch(texts[start:start + MAX_EMBED_BATCH]))
    return embeddings


def main() -> None:
    """读文档 → 切块 → 向量化 → 写进 Chroma。"""
    # ① 读文档：docs/ 下每个 .md 都是一份知识
    all_chunks: list[str] = []      # 所有块的正文
    all_sources: list[str] = []     # 每块来自哪个文件（写进 metadata，方便查证）

    for md_file in sorted(DOCS_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        chunks = split_markdown(text)
        all_chunks.extend(chunks)
        all_sources.extend([md_file.name] * len(chunks))
        print(f"  {md_file.name}: {len(chunks)} 块")

    if not all_chunks:
        print(f"没在 {DOCS_DIR} 里找到任何 .md 文档，先放文档再跑")
        return

    # ② 向量化
    print(f"共 {len(all_chunks)} 块，正在向量化…")
    embeddings = embed_texts(all_chunks)

    # ③ 写进 Chroma：先把同名集合删掉，避免重复入库时旧数据累积
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # 已存在的集合名列表
    existing_names = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing_names:
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(COLLECTION_NAME)
    collection.add(
        ids=[f"chunk-{i}" for i in range(len(all_chunks))],   # 每块的唯一编号
        documents=all_chunks,                                 # 正文
        embeddings=embeddings,                                # 对应的向量
        metadatas=[{"source": s} for s in all_sources],        # 来源文件
    )

    print(f"入库完成：{collection.count()} 块 → {CHROMA_DIR}")


if __name__ == "__main__":
    main()
