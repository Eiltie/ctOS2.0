import os

from dotenv import load_dotenv
from pathlib import Path
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

# 闲聊侧的模型配置：参数从 config/.env 读，代码里只留温度

TEMPERATURE = 0.7


def get_llm() -> ChatOpenAI:
    """按 config/.env 里的配置新建 DeepSeek 客户端。"""
    ai = ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        model=os.getenv("DEEPSEEK_MODEL"),
        temperature=TEMPERATURE,
    )

    return ai


if __name__ == "__main__":
    ai = get_llm()
