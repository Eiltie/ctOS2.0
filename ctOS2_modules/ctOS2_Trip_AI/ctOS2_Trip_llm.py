import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(_PROJECT_ROOT / "config" / ".env")

for _p in (_PROJECT_ROOT / "src", _PROJECT_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


TEMPERATURE = 0.3


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        model=os.getenv("DEEPSEEK_MODEL"),
        temperature=TEMPERATURE,
    )


if __name__ == "__main__":
    print(get_llm())
