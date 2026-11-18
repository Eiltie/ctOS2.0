"""全项目唯一的模型客户端入口：三个模块都从这里拿 LLM。

为什么合并成一个文件：
  原来闲聊 / 出行 / 客服各有一份 get_llm()，内容几乎一样、只差温度和
  reasoning_effort 两个参数，而 .env 还被 load_dotenv 解析了四遍。
  合并之后改模型名、加超时、换厂商都只需要动这一个文件。

三个模块的差异（调用方按需传）：
  闲聊    get_llm(temperature=0.7)                  要活泼一点，不开思考
  出行    get_llm(temperature=0.3)                  要稳，默认不开思考（快 4 倍）
          get_llm(temperature=0.3, thinking=True)   只有排路线时刻才开
  客服    get_llm(temperature=0.3)                  要准，不开思考
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 项目根目录：本文件在 core/ 下，往上两级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 全项目只在这里读一次 .env。
# 其他文件不要再调 load_dotenv（重复解析没有意义，还可能互相覆盖）。
load_dotenv(_PROJECT_ROOT / "config" / ".env")

# 各模块默认温度：调用方不传就按这里取
DEFAULT_TEMPERATURE = 0.3

# 思考强度。
#   none = 不思考，模型直接写答案，快很多（实测同一任务 10.7 秒 → 2.4 秒）
#   high = 默认强度，模型会先在内部推理再写，慢但适合需要算数的任务
# 大多数环节只是"把已有信息写成文字"，不需要思考；
# 只有排路线时刻这种要算时间的环节才值得打开。调用方按需传。
THINKING_LEVEL = "high"
NO_THINKING_LEVEL = "none"


def get_llm(temperature: float = DEFAULT_TEMPERATURE, thinking: bool = False) -> ChatOpenAI:
    """新建一个 DeepSeek 客户端。

    Args:
        temperature: 随机性。闲聊要 0.7，其余模块 0.3。
        thinking: 是否开启深度思考。默认关闭，因为关闭后快得多，
                  而且写天气总结、景点清单这类任务质量基本不变。
    """
    return ChatOpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        model=os.getenv("DEEPSEEK_MODEL"),
        temperature=temperature,
        # 服务端认这个参数：none 表示不思考，high 表示正常思考
        reasoning_effort=THINKING_LEVEL if thinking else NO_THINKING_LEVEL,
    )


if __name__ == "__main__":
    print(get_llm())
