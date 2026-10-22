import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(_PROJECT_ROOT / "config" / ".env")

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 路径与模型参数：客服模块的所有文件都从这里读配置

MODULE_DIR = Path(__file__).resolve().parent

DOCS_DIR = MODULE_DIR / "data" / "docs"

CHROMA_DIR = MODULE_DIR / "data" / "chroma"

COLLECTION_NAME = "ctos2_docs"

TEMPERATURE = 0.3

EMBEDDING_MODEL = "embedding-3"

EMBEDDING_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"


def get_llm() -> ChatOpenAI:
    """新建一个 DeepSeek 客户端，生成最终回答用。"""
    return ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        model=os.getenv("DEEPSEEK_MODEL"),
        temperature=TEMPERATURE,
    )


def get_zhipu_api_key() -> str:
    """取智谱密钥；缺了直接报错，避免后面冒出看不懂的 401。"""
    api_key = os.getenv("ZHIPU_API_KEY")
    if not api_key:
        raise RuntimeError("config/.env 里没有 ZHIPU_API_KEY，向量检索无法工作")
    return api_key


if __name__ == "__main__":
    print(get_llm())
    print("DOCS_DIR   =", DOCS_DIR)
    print("CHROMA_DIR =", CHROMA_DIR)
