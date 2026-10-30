"""客服模块的路径与向量化配置：所有客服文件都从这里读。

原来这些常量混在 get_llm.py 里，那个文件名叫「拿模型」却装着「文档在哪」，
找配置的时候根本想不到要翻它。单独拆出来后：
  - 想知道文档放哪、向量库放哪  → 看这里
  - 想知道怎么拿模型客户端      → 看 core/llm.py
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

# 智谱向量模型
EMBEDDING_MODEL = "embedding-3"

EMBEDDING_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"


def get_zhipu_api_key() -> str:
    """取智谱密钥；缺了直接报错，避免后面冒出看不懂的 401。"""
    api_key = os.getenv("ZHIPU_API_KEY")
    if not api_key:
        raise RuntimeError("config/.env 里没有 ZHIPU_API_KEY，向量检索无法工作")
    return api_key


if __name__ == "__main__":
    print("DOCS_DIR   =", DOCS_DIR)
    print("CHROMA_DIR =", CHROMA_DIR)
    print("COLLECTION =", COLLECTION_NAME)
