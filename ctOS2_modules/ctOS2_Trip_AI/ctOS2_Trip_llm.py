import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 本文件在 ctOS2_modules/ctOS2_Trip_AI/ 下：
#   parents[0] = ctOS2_Trip_AI   parents[1] = ctOS2_modules   parents[2] = E:\ctOS2.0
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 本项目所有配置集中在 config/.env（不在项目根目录）
load_dotenv(_PROJECT_ROOT / "config" / ".env")

for _p in (_PROJECT_ROOT / "src", _PROJECT_ROOT):
    # src/  —— 需要复用项目 src/ 下的东西时 import 得到
    # 根目录 —— 本模块自己的包路径（ctOS2_modules.ctOS2_Trip_AI.xxx）
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


TEMPERATURE = 0.3


def get_llm() -> ChatOpenAI:
    """按 config/.env 里的 DEEPSEEK_* 配置新建一个模型客户端。

    每次调用都新建：调用方（各节点）通常还要接着 .bind_tools() / .with_config()，
    那些都是返回新对象、不改原对象，所以新建和复用没有区别，写法简单直接。
    """
    return ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        model=os.getenv("DEEPSEEK_MODEL"),
        temperature=TEMPERATURE,
    )


if __name__ == "__main__":
    print(get_llm())
