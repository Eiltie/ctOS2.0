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

# 出行侧的模型配置：参数从 config/.env 读

TEMPERATURE = 0.3

# 思考强度。
#   none  = 不思考，模型直接写答案，快很多（实测同一任务 10.7 秒 → 2.4 秒）
#   high  = 默认强度，模型会先在内部推理再写，慢但适合需要算数的任务
# 出行流程里大多数环节只是"把已有信息写成文字"，不需要思考；
# 只有排路线时刻这种要算时间的环节才值得打开。调用方按需传。
THINKING_LEVEL = "high"
NO_THINKING_LEVEL = "none"


def get_llm(thinking: bool = False) -> ChatOpenAI:
    """新建一个 DeepSeek 客户端。

    Args:
        thinking: 是否开启深度思考。默认关闭，因为关闭后快得多，
                  而且写天气总结、景点清单这类任务质量基本不变。
    """
    return ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        model=os.getenv("DEEPSEEK_MODEL"),
        temperature=TEMPERATURE,
        # 服务端认这个参数：none 表示不思考，high 表示正常思考
        reasoning_effort=THINKING_LEVEL if thinking else NO_THINKING_LEVEL,
    )


if __name__ == "__main__":
    print(get_llm())
