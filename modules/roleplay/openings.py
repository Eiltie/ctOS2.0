"""角色的开场白：用户没写，就让模型根据人设说一句。"""

import re

from core.llm import get_llm

# 开场白不要太长，太长放进聊天框很奇怪
OPENING_LIMIT = 200

# 生成开场白可以活泼一点
OPENING_TEMPERATURE = 0.7


def split_opening(extra):
    """把补充说明拆成（开场白，去掉开场白后的补充说明）。"""
    match = re.search(r"开场白\s*[:：]\s*(.+)", extra or "")
    if not match:
        return "", extra or ""

    opening = match.group(1).strip()[:OPENING_LIMIT]
    cleaned = ((extra or "")[:match.start()] + (extra or "")[match.end():]).strip()
    return opening, cleaned


def take_opening(extra):
    """从补充说明里找“开场白：xxx”，找到就返回。"""
    return split_opening(extra)[0]


def role_lines(role):
    """把角色资料拼成几行，给模型看。"""
    pairs = (
        ("名字", role.get("name")),
        ("年龄", role.get("age")),
        ("性别", role.get("gender")),
        ("性格", role.get("personality")),
        ("人物事迹", role.get("deeds")),
        ("背景故事", role.get("background")),
        ("补充说明", role.get("extra")),
    )

    lines = []
    for label, value in pairs:
        value = (value or "").strip()
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines)


def make_opening(role):
    """让模型写一句开场白；失败就用一句最简单的。"""
    name = (role.get("name") or "这个角色").strip()
    fallback = f"我是{name}，你想聊点什么？"

    prompt = f"""你正在设计一个角色的开场白。

角色资料：
{role_lines(role)}

请只写角色说的第一句话，要求：
1. 用第一人称，符合角色的身份、性格和背景。
2. 一句话，30 到 60 个字，不要解释，不要加引号。
3. 资料不足就写得自然一点，不要编造具体事实。
"""
    try:
        result = get_llm(temperature=OPENING_TEMPERATURE).invoke(prompt)
        text = str(result.content or "").strip()
        text = text.splitlines()[0].strip() if text else ""
        text = text.strip("\"“”")
        return text[:OPENING_LIMIT] or fallback
    except Exception as e:
        print(f"[角色开场白] 生成失败：{e}")
        return fallback
