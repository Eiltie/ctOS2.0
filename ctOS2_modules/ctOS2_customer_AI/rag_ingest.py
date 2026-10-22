import json
import sys
import urllib.request
from pathlib import Path

import chromadb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.get_llm import (
    CHROMA_DIR,
    COLLECTION_NAME,
    DOCS_DIR,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL,
    get_zhipu_api_key,
)

# 一次性入库脚本：读 data/docs 下的文档，切块向量化后写进 Chroma
# 切块与向量化参数
# 单块字符上限，太长的块检索不准
MAX_CHUNK_CHARS = 600

# 智谱 embedding 单次 input 最多 64 条，超了直接 HTTP 400，因此必须分批
MAX_EMBED_BATCH = 64


def split_markdown(text: str) -> list[str]:
    """把一篇 Markdown 切成检索用的片段，返回片段列表。"""
    # 按「## 」切小节，过长的小节再按行切，避免从句子中间劈开
    sections: list[str] = []
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append("\n".join(current_lines))
                current_lines = []
        current_lines.append(line)

    if current_lines:
        sections.append("\n".join(current_lines))

    result: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= MAX_CHUNK_CHARS:
            result.append(section)
            continue

        part_lines: list[str] = []
        part_len = 0
        for line in section.splitlines():
            part_lines.append(line)
            part_len += len(line) + 1
            if part_len >= MAX_CHUNK_CHARS:
                result.append("\n".join(part_lines))
                part_lines = []
                part_len = 0
        if part_lines:
            result.append("\n".join(part_lines))

    return result


def embed_batch(texts: list[str]) -> list[list[float]]:
    """把一小批文本转成向量，返回顺序与传入一致。"""
    api_key = get_zhipu_api_key()

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

    # 接口返回带 index，按 index 排一遍保证和传入顺序对得上
    items = sorted(body["data"], key=lambda item: item["index"])
    return [item["embedding"] for item in items]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """分批把所有文本转成向量，返回全部向量。"""
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), MAX_EMBED_BATCH):
        embeddings.extend(embed_batch(texts[start:start + MAX_EMBED_BATCH]))
    return embeddings


def main() -> None:
    """读文档 → 切块 → 向量化 → 重建 Chroma 集合。"""
    all_chunks: list[str] = []
    all_sources: list[str] = []

    for md_file in sorted(DOCS_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        chunks = split_markdown(text)
        all_chunks.extend(chunks)
        all_sources.extend([md_file.name] * len(chunks))
        print(f"  {md_file.name}: {len(chunks)} 块")

    if not all_chunks:
        print(f"没在 {DOCS_DIR} 里找到任何 .md 文档，先放文档再跑")
        return

    print(f"共 {len(all_chunks)} 块，正在向量化…")
    embeddings = embed_texts(all_chunks)

    # 同名集合先删掉再建，否则重复入库会累积旧数据
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    existing_names = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing_names:
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(COLLECTION_NAME)
    collection.add(
        ids=[f"chunk-{i}" for i in range(len(all_chunks))],
        documents=all_chunks,
        embeddings=embeddings,
        metadatas=[{"source": s} for s in all_sources],
    )

    print(f"入库完成：{collection.count()} 块 → {CHROMA_DIR}")


if __name__ == "__main__":
    main()
