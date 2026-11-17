"""客服｜知识库入库脚本（改完文档必须重跑）

做什么：把 data/docs/*.md 按 ## 切块 → 向量化 → 重建 Chroma 集合。
怎么用：python -X utf8 -m modules.customer.rag_ingest，然后重启服务。

说明：向量化交给 modules/customer/embedding.py（本机 Ollama）。
这个文件只管「读文档、切块、写库」这三件事。

关于「标题路径」（title）：
  一块正文单独拿出来，模型不知道它是讲什么的——
  FAQ 里一段「这个要看情况」和手册里一段「这个要看情况」长得一样。
  所以每个块入库时额外存一行「文件名 › 一级标题 › 二级标题」，
  检索时拼到正文前面一起给模型。这一行也一起向量化，
  这样「部署怎么配」这类问题更容易命中部署那几块。
"""

from pathlib import Path

import chromadb


from modules.customer.embedding import embed_texts
from modules.customer.rag_config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    DOCS_DIR,
    EMBEDDING_MODEL,
)

# 一次性入库脚本：读 data/docs 下的文档，切块向量化后写进 Chroma
# 切块与向量化参数
#
# 单块字符上限。用 rag_eval 扫过 500 / 600 / 800 / 1000 四个值：
#   500：@1 42.5%，可答题@1 56.7%  —— 太碎，答案散到几个块里
#   600：@1 52.5%，可答题@1 70.0%  —— 原来的值
#   800：@1 60.0%，可答题@1 80.0%  —— 现在的值，@4 和 @1 同时最好
#  1000：@1 60.0%，可答题@1 76.7%  —— @4 更高但 @1 反而回落，块太粗
# 改这个数之前先跑 rag_eval 对比，别凭感觉调。
MAX_CHUNK_CHARS = 800

# 短于这个长度的块直接丢掉：只有一个标题、或者只剩一条列表符号的碎片，
# 检索命中它也没法回答问题，还占一个名额。
MIN_CHUNK_CHARS = 40


def _split_sections(text: str):
    """按 # / ## 切成小节，返回 [(一级标题, 正文)]。

    一级标题（`# `）只用来记「这块属于哪一章」，不会重复放进正文，
    因为正文里本来就带着它；二级标题（`## `）是真正的切分点。

    **代码块里的 `#` 不是标题**：文档里有大量 bash 片段，
    `# macOS / Linux`、`# 启动项目` 这种注释行长得和标题一模一样。
    不跳过代码块的话，切出来的每一块都会带上一条假的章节名
    （改版前实测：整本手册 63 块里有一半的标题路径是「› source venv/bin/activate」）。
    """
    sections = []
    h1 = ""
    current_lines = []
    in_fence = False

    for line in text.splitlines():
        # 围栏行本身要留在正文里，只是之后不再判断标题
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            current_lines.append(line)
            continue

        if in_fence:
            current_lines.append(line)
            continue

        if line.startswith("# "):
            if current_lines:
                sections.append((h1, "\n".join(current_lines)))
                current_lines = []
            h1 = line[2:].strip()
            # 一级标题本身留在正文里：有的文档正文第一段就靠它
            current_lines.append(line)
            in_fence = False
            continue

        if line.startswith("## "):
            if current_lines:
                sections.append((h1, "\n".join(current_lines)))
                current_lines = []
            # 上一节要是没闭合围栏就结束了，这里要清掉，否则这一节会被并进代码块
            in_fence = False

        current_lines.append(line)

    if current_lines:
        sections.append((h1, "\n".join(current_lines)))

    return sections


def _split_long(body: str) -> list[str]:
    """超长小节再切小，但**不在代码块中间下刀**。

    切在代码块中间，前半截有开头没结尾，模型看不懂那是什么命令，
    也会让半个代码块占据一个检索名额。

    优先在 `###` 三级标题处切：三级标题本身就是这个话题的天然边界，
    按它切出来的块语义最完整。
    实测「怎么用 Docker 部署」就是因为按长度硬切，
    把「6.1 环境要求 / 6.2 依赖清单 / 6.3 数据位置」捆成一块，
    真正的部署命令被挤到别的块里，模型拿到资料也答不出来。
    没有三级标题、或者单个小节还是超长，才退回按段落（空行）切。
    """
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]

    # 先按 ### 拆成小节；每个小节连同它后面的内容算一个单元
    subs = []
    cur = []
    for line in body.splitlines():
        if line.startswith("### ") and cur:
            subs.append("\n".join(cur))
            cur = []
        cur.append(line)
    if cur:
        subs.append("\n".join(cur))

    # 单个小节还是超长，就按段落再拆
    units = []
    for sub in subs:
        if len(sub) <= MAX_CHUNK_CHARS:
            units.append(sub)
        else:
            units.extend(_split_by_paragraph(sub))

    # 把单元贪心拼回块，拼到接近上限为止
    parts = []
    cur_parts = []
    cur_len = 0
    for unit in units:
        if cur_parts and cur_len + len(unit) + 2 > MAX_CHUNK_CHARS:
            parts.append("\n\n".join(cur_parts))
            cur_parts = []
            cur_len = 0
        cur_parts.append(unit)
        cur_len += len(unit) + 2
    if cur_parts:
        parts.append("\n\n".join(cur_parts))

    return parts


def _split_by_paragraph(body: str) -> list[str]:
    """按空行（段落）切单元，代码块当成不可分的一段。"""
    units = []
    buf = []
    buf_len = 0
    in_fence = False
    fence_buf = []

    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            fence_buf.append(line)
            if not in_fence:
                units.append("\n".join(fence_buf))
                fence_buf = []
                buf = []
                buf_len = 0
            continue

        if in_fence:
            fence_buf.append(line)
            continue

        if not line.strip():
            if buf:
                units.append("\n".join(buf))
                buf = []
                buf_len = 0
            continue

        if len(line) > MAX_CHUNK_CHARS:
            if buf:
                units.append("\n".join(buf))
                buf = []
                buf_len = 0
            units.append(line)
            continue

        if buf_len + len(line) + 1 > MAX_CHUNK_CHARS:
            units.append("\n".join(buf))
            buf = []
            buf_len = 0

        buf.append(line)
        buf_len += len(line) + 1

    if fence_buf:
        units.append("\n".join(fence_buf))
    if buf:
        units.append("\n".join(buf))

    return units


def split_markdown_detailed(text: str, source: str = "") -> list[dict]:
    """把一篇 Markdown 切成检索用的片段，每块带标题路径。

    返回 [{"text": 正文, "title": "文件名 › 一级标题 › 二级标题"}]。
    超长的小节按行再切，每一刀切出来的块沿用同一条标题路径。
    """
    result = []

    for h1, body in _split_sections(text):
        body = body.strip()
        if not body:
            continue

        # 二级标题就是这一节的标题；没有就是一级标题
        h2 = ""
        first_line = body.splitlines()[0].strip()
        if first_line.startswith("## "):
            h2 = first_line[3:].strip()

        parts = _split_long(body)

        for i, part in enumerate(parts):
            # 去掉标题行本身之后剩不下多少内容 = 碎片，不要
            if len(part.strip()) < MIN_CHUNK_CHARS:
                continue

            crumbs = [c for c in (source, h1, h2) if c]
            title = " › ".join(crumbs)
            # 同一个二级标题被切成多段时标上「第 N 段」，检索结果里分得清
            if len(parts) > 1:
                title = f"{title}（第 {i + 1}/{len(parts)} 段）"
            result.append({"text": part, "title": title})

    return result


def main() -> None:
    """读文档 → 切块 → 向量化 → 重建 Chroma 集合。"""
    all_chunks: list[str] = []
    all_titles: list[str] = []
    all_sources: list[str] = []

    for md_file in sorted(DOCS_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        blocks = split_markdown_detailed(text, source=md_file.name)
        all_chunks.extend(b["text"] for b in blocks)
        all_titles.extend(b["title"] for b in blocks)
        all_sources.extend([md_file.name] * len(blocks))
        print(f"  {md_file.name}: {len(blocks)} 块")

    if not all_chunks:
        print(f"没在 {DOCS_DIR} 里找到任何 .md 文档，先放文档再跑")
        return

    print(f"共 {len(all_chunks)} 块，正在用本机模型「{EMBEDDING_MODEL}」向量化…")
    # 向量化的是「标题路径 + 正文」：让标题里的词也能被检索到
    embeddings = embed_texts([f"{t}\n{c}" for t, c in zip(all_titles, all_chunks)])

    # 同名集合先删掉再建，否则重复入库会累积旧数据
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    existing_names = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing_names:
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    collection.add(
        ids=[f"chunk-{i}" for i in range(len(all_chunks))],
        documents=all_chunks,
        embeddings=embeddings,
        metadatas=[
            {"source": s, "title": t}
            for s, t in zip(all_sources, all_titles)
        ],
    )

    print(f"入库完成：{collection.count()} 块 → {CHROMA_DIR}")
    print("提示：入库后要重启服务，进程里缓存的还是旧知识库。")


if __name__ == "__main__":
    main()
