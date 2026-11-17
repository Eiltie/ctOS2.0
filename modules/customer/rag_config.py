"""客服模块的路径与向量化配置：所有客服文件都从这里读。

原来这些常量混在 get_llm.py 里，那个文件名叫「拿模型」却装着「文档在哪」，
找配置的时候根本想不到要翻它。单独拆出来后：
  - 想知道文档放哪、向量库放哪、用哪个向量模型  → 看这里
  - 想知道怎么拿模型客户端                      → 看 core/llm.py
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根：本文件在 modules/customer/ 下，往上三级
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 全项目统一由 core/llm.py 负责 load_dotenv。
# 这里再调一次是幂等的（已加载过不会有副作用），
# 保证「单独跑本文件」或「直接 import rag_config」时密钥也能读到。
load_dotenv(_PROJECT_ROOT / "config" / ".env")

# 客服模块自己的目录
MODULE_DIR = Path(__file__).resolve().parent

# 知识库源文档：放 .md 文件，按 ## 二级标题切块
DOCS_DIR = MODULE_DIR / "data" / "docs"

# Chroma 向量库落盘位置（运行产物，不入 git）
CHROMA_DIR = MODULE_DIR / "data" / "chroma"

# 向量库集合名
COLLECTION_NAME = "ctos2_docs"


# ---------------------------------------------------------------- 向量化：本机 Ollama
#
# 向量检索用的模型跑在本机（Ollama）上，不走云端接口。
# 好处：不用密钥、不联网、不花钱，入库也快。
#
# 两个环境变量可以在 config/.env 里覆盖下面两个默认值：
#   OLLAMA_HOST         服务的地址，默认本机 11434 端口
#   OLLAMA_EMBED_MODEL  模型名，默认 qwen3-embedding:0.6b

# 模型名。必须是 embedding 模型，不是对话模型。
# 本机装了哪些：命令行运行 ollama list 看
EMBEDDING_MODEL = os.getenv("OLLAMA_EMBED_MODEL") or "qwen3-embedding:0.6b"

# Ollama 服务的地址
EMBEDDING_HOST = os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434"


def embedding_api_url() -> str:
    """拼出 Ollama 的向量接口地址。

    Ollama 的向量接口是 /api/embed，请求体长这样：
        {"model": "模型名", "input": ["第一条", "第二条"]}
    返回里的 embeddings 是一个列表，顺序和传入顺序一致。
    """
    return EMBEDDING_HOST.rstrip("/") + "/api/embed"


if __name__ == "__main__":
    print("DOCS_DIR   =", DOCS_DIR)
    print("CHROMA_DIR =", CHROMA_DIR)
    print("COLLECTION =", COLLECTION_NAME)
    print("向量模型   =", EMBEDDING_MODEL)
    print("向量服务   =", embedding_api_url())
