from langchain_core.messages import HumanMessage, SystemMessage

from common.llm import get_llm
from modules.generate_prompts.prompts import SYSTEM_PROMPTS
from modules.generate_prompts.state import AgentState


def prompt_node(state: AgentState) -> dict:
    requirement = state["requirement"]
    images = state["images"]

    if not requirement:
        return {
            "status": "failed",
            "problem": "没有获取到需求",
            "prompt": "",
        }

    content = [
        SystemMessage(content=SYSTEM_PROMPTS),
        HumanMessage(content=[{"type": "text", "text": requirement}] + images),
    ]

    work = get_llm()

    try:
        result = work.invoke(content)
    except Exception as e:
        return {
            "status": "failed",
            "problem": f"提示词生成失败：{e}",
            "prompt": "",
        }

    prompt = (result.content or "").strip()

    if not prompt:
        return {
            "status": "failed",
            "problem": "提示词生成失败",
            "prompt": "",
        }

    return {
        "prompt": prompt,
        "status": "ok",
        "problem": "",
    }


if __name__ == "__main__":
    result = prompt_node({"requirement": "画一朵花", "images": []})

    print(result.get("prompt") or result.get("problem"))
