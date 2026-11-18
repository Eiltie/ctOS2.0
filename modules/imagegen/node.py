"""生图｜三个节点

plan     把用户需求拆成结构化规格，判断信息够不够
ask      需求不足时停下来问（interrupt），用户回答后回到 plan
generate 拿规格拼提示词，调 Seedream 生图，存到本地

为什么 ask 之后要回 plan 而不是直接 generate：
  用户可能回答了「一只猫」，这时候还需要模型把这句话补成完整规格
  （风格、比例、光线）。回 plan 让它统一处理，不用在 ask 里另写一套解析。
"""

import json
from datetime import date

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from common.llm import get_llm
from modules.imagegen.prompts import (
    ASK_QUESTION,
    FALLBACK_TOPICS,
    PLAN_PROMPT,
    PROMPT_PROMPT,
    RANDOM_PROMPT,
)
from modules.imagegen.state import (
    DEFAULT_ASPECT,
    STATUS_API_FAILED,
    STATUS_NEED_MORE,
    STATUS_OK,
    STATUS_PROMPT_FAILED,
)
from modules.imagegen.tools import (
    build_prompt,
    call_seedream,
    normalize_size,
    save_generated,
)

# 规格里必须有的字段：主体是唯一硬要求
REQUIRED_FIELDS = ("subject",)


def _parse_json(raw):
    """解析模型输出的 JSON；失败返回 None。"""
    text = (raw or "").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, AttributeError):
        return None

    return data if isinstance(data, dict) else None


def _history_text(history):
    """把之前说过的话拼成文本。"""
    lines = [str(item).strip() for item in (history or []) if str(item).strip()]
    return "\n".join(lines) if lines else "（还没聊过）"


def plan_node(state) -> dict:
    """把需求拆成结构化规格，并判断信息够不够。

    这是整张图里唯一"做判断"的节点：
      够  → 往下生成
      不够 → 交给 ask 停下来问
    """
    query = (state.get("user_query") or "").strip()
    history = state.get("history") or []
    asked_once = bool(state.get("asked_once"))
    answer = (state.get("answer") or "").strip()

    # 用户刚回答了提问：把回答并进来当新需求
    if answer and answer != query:
        query = f"{query}\n用户的补充：{answer}" if query else answer

    prompt = (PLAN_PROMPT
              .replace("{today}", str(date.today()))
              .replace("{history}", _history_text(history))
              .replace("{query}", query))

    try:
        raw = get_llm(temperature=0.3).invoke([HumanMessage(content=prompt)]).content
    except Exception as e:
        return {
            "status": STATUS_PROMPT_FAILED,
            "problem": f"理解需求时出错：{e}",
            "node_path": ["plan"],
        }

    data = _parse_json(raw)

    # 模型没按格式输出：按"信息不足"处理，走 ask 兜底
    if data is None:
        return {
            "spec": {},
            "missing": ["画面内容"],
            "asked_once": asked_once,
            "status": STATUS_NEED_MORE if not asked_once else STATUS_PROMPT_FAILED,
            "problem": "" if not asked_once else "没能理解你想画什么",
            "node_path": ["plan"],
        }

    spec = data.get("spec") or {}
    if not isinstance(spec, dict):
        spec = {}

    # 只保留认识的字段，防止模型塞进奇怪的东西
    kept = {
        "subject": str(spec.get("subject") or "").strip(),
        "action": str(spec.get("action") or "").strip(),
        "scene": str(spec.get("scene") or "").strip(),
        "style": str(spec.get("style") or "").strip(),
        "lighting": str(spec.get("lighting") or "").strip(),
        "aspect": str(spec.get("aspect") or DEFAULT_ASPECT).strip(),
        "text_in_image": str(spec.get("text_in_image") or "").strip(),
        "negative": str(spec.get("negative") or "").strip(),
    }

    # 主体是硬要求：没有主体就画不出东西
    missing = [field for field in REQUIRED_FIELDS if not kept.get(field)]

    enough = bool(data.get("enough")) and not missing

    if not enough:
        return {
            "spec": kept,
            "missing": missing or ["画面内容"],
            "asked_once": asked_once,
            "status": STATUS_NEED_MORE,
            "node_path": ["plan"],
        }

    return {
        "spec": kept,
        "missing": [],
        "asked_once": asked_once,
        "status": STATUS_OK,
        "node_path": ["plan"],
    }


def ask_node(state) -> dict:
    """需求不足时停下来问用户。用户回答后会回到 plan 重新判断。

    asked_once 在这里置 True：问过一次就不再问，
    哪怕用户还是没说清楚，也直接往下画（用随机主题兜底），不能死循环。
    """
    reply = interrupt({
        "question": ASK_QUESTION,
        "asked_once": bool(state.get("asked_once")),
    })

    if isinstance(reply, dict):
        reply = reply.get("answer", "")

    return {
        "answer": str(reply or "").strip(),
        "asked_once": True,
        "node_path": ["ask"],
    }


def generate_node(state) -> dict:
    """拼提示词 → 调接口 → 存图。

    失败一律写进 status + problem，不抛异常。
    """
    spec = state.get("spec") or {}
    asked_once = bool(state.get("asked_once"))

    # 问过一次还是没需求：随机挑一个主题，不再纠缠用户
    if not spec.get("subject"):
        if not asked_once:
            # 理论上到不了这里（plan 会先拦住），兜个底
            return {
                "status": STATUS_NEED_MORE,
                "node_path": ["generate"],
            }

        spec = _random_spec()

    # 第一步：把规格拼成提示词
    prompt = build_prompt(spec)

    if not prompt:
        # 规格拼不出东西时，让模型直接写一段（最后的兜底）
        prompt = _random_prompt()

    if not prompt:
        return {
            "status": STATUS_PROMPT_FAILED,
            "problem": "没能生成有效的提示词",
            "node_path": ["generate"],
        }

    size = normalize_size(spec.get("aspect") or DEFAULT_ASPECT)

    # 第二步：调接口
    content, problem = call_seedream(prompt, size)

    if content is None:
        return {
            "final_prompt": prompt,
            "size": size,
            "status": STATUS_API_FAILED,
            "problem": problem or "生图失败",
            "node_path": ["generate"],
        }

    # 第三步：存盘
    path, rel = save_generated(content)

    return {
        "spec": spec,
        "final_prompt": prompt,
        "size": size,
        "image_path": path,
        "image_url": rel,
        "status": STATUS_OK,
        "problem": "",
        "node_path": ["generate"],
    }


def _random_spec() -> dict:
    """从兜底主题里随机挑一个，转成规格。"""
    import random

    topic = random.choice(FALLBACK_TOPICS)
    return {
        "subject": topic,
        "action": "",
        "scene": "",
        "style": "",
        "lighting": "",
        "aspect": DEFAULT_ASPECT,
        "text_in_image": "",
        "negative": "",
    }


def _random_prompt() -> str:
    """让模型写一段随机主题的提示词（兜底中的兜底）。"""
    try:
        return get_llm(temperature=0.9).invoke(
            [HumanMessage(content=RANDOM_PROMPT)]
        ).content.strip()
    except Exception as e:
        print(f"[生图] 随机主题生成失败：{e}")
        return ""
