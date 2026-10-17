import os

from dotenv import load_dotenv
from pathlib import Path
from langchain_openai import ChatOpenAI

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

TEMPERATURE = 0.7

def get_llm() -> ChatOpenAI:
    ai = ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        model=os.getenv("DEEPSEEK_MODEL"),
        temperature=TEMPERATURE,
    )

    return ai


if __name__ == "__main__":
    ai = get_llm()