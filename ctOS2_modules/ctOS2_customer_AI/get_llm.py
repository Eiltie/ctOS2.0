"""LLM 与公共配置。

本模块所有文件都从这里 import 配置，不再各自读一遍 .env。
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 本文件在 ctOS2_modules/ctOS2_customer_AI/ 下：
#   parents[0] = ctOS2_customer_AI   parents[1] = ctOS2_modules   parents[2] = E:\ctOS_prototype\ctOS2.0
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 项目所有配置集中在 config/.env
load_dotenv(_PROJECT_ROOT / "config" / ".env")

# 让本模块能被以包路径 import（ctOS2_modules.ctOS2_customer_AI.xxx）
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ==================== 路径常量 ====================

# 模块自己的目录（data/ 就在它下面）
MODULE_DIR = Path(__file__).resolve().parent

# 知识库原始文档目录（要入库的 Markdown 都放这里）
DOCS_DIR = MODULE_DIR / "data" / "docs"

# Chroma 向量库落盘目录
CHROMA_DIR = MODULE_DIR / "data" / "chroma"

# Chroma 集合名（一个集合 = 一份知识库）
COLLECTION_NAME = "ctos2_docs"


# ==================== 模型常量 ====================

TEMPERATURE = 0.3          # 生成答案时的随机性，客服场景要稳，取值偏低

# 智谱 embedding 模型名：输出 2048 维向量
EMBEDDING_MODEL = "embedding-3"

# 智谱 embedding 接口地址
EMBEDDING_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"


# ==================== 对外函数 ====================

def get_llm() -> ChatOpenAI:
    """新建一个 DeepSeek 客户端（生成最终回答用）。"""
    return ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        model=os.getenv("DEEPSEEK_MODEL"),
        temperature=TEMPERATURE,
    )


def get_zhipu_api_key() -> str:
    """取智谱密钥（向量化用）。缺了就报错，避免后面报个看不懂的 401。"""
    api_key = os.getenv("ZHIPU_API_KEY")
    if not api_key:
        raise RuntimeError("config/.env 里没有 ZHIPU_API_KEY，向量检索无法工作")
    return api_key


if __name__ == "__main__":
    print(get_llm())
    print("DOCS_DIR   =", DOCS_DIR)
    print("CHROMA_DIR =", CHROMA_DIR)
