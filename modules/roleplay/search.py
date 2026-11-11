"""AI 帮我查：先联网搜资料，再让模型整理成一份角色档案。

只负责生成草稿，不存数据库；
用户看完觉得可以，再走 /roleplay/roles 保存。
"""

import json

from core.llm import get_llm
from modules.roleplay.openings import make_opening
from modules.roleplay.roles import DEFAULT_ROLE_BOUNDARIES
from modules.trip.tools import web_search

# 搜索和整理都要稳一点，不要自由发挥
SEARCH_TEMPERATURE = 0.4

# 搜索词后面补这些，帮助找到性格和说话方式，而不是只有百科生平
SEARCH_SUFFIX = " 人物 性格 说话方式 背景 经典台词"

# 档案字段的长度上限，和手动创建角色保持一致
NAME_LIMIT = 20
EMOJI_LIMIT = 4
TAGLINE_LIMIT = 30
AGE_LIMIT = 20
GENDER_LIMIT = 10
TEXT_LIMIT = 200
LONG_LIMIT = 300

ROLE_SEARCH_PROMPT = """你是一个角色档案整理器。用户想扮演：{query}

下面是网上查到的资料：
{search_text}

请只输出一个 JSON 对象，不要 markdown，不要解释。格式：
{{
  "name": "角色名",
  "emoji": "一个 emoji",
  "tagline": "很短的标签",
  "age": "年龄",
  "gender": "性别",
  "personality": "性格",
  "deeds": "人物事迹",
  "background": "背景故事",
  "extra": "兴趣爱好、口头禅等补充",
  "speaking": "说话方式",
  "opening": "角色说的第一句话"
}}

要求：
1. 名字优先用用户说的名字。
2. 用第一人称设计说话方式，不要照抄百科原文。
3. 资料不足就按人物常识写，不要编造具体事实。
"""


def clean_text(value, limit):
    """去掉首尾空格并限制长度。"""
    return (value or "").strip()[:limit]


def parse_role_json(text):
    """从模型回复里抠出 JSON；前后有多余说明也能处理。"""
    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end <= start:
        raise ValueError("模型没有返回 JSON")

    return json.loads(text[start:end + 1])


def search_role(query):
    """搜资料 + 生成角色草稿，返回 (role, note)。"""
    search_text = web_search.invoke({"query": query + SEARCH_SUFFIX})

    prompt = ROLE_SEARCH_PROMPT.format(query=query, search_text=search_text)
    result = get_llm(temperature=SEARCH_TEMPERATURE).invoke(prompt)
    data = parse_role_json(str(result.content or ""))

    name = clean_text(data.get("name"), NAME_LIMIT) or clean_text(query, NAME_LIMIT)
    if not name:
        name = "新角色"

    emoji = clean_text(data.get("emoji"), EMOJI_LIMIT) or "🎭"
    tagline = clean_text(data.get("tagline"), TAGLINE_LIMIT) or "AI 生成"
    age = clean_text(data.get("age"), AGE_LIMIT)
    gender = clean_text(data.get("gender"), GENDER_LIMIT)
    personality = clean_text(data.get("personality"), TEXT_LIMIT)
    deeds = clean_text(data.get("deeds"), LONG_LIMIT)
    background = clean_text(data.get("background"), LONG_LIMIT)
    extra = clean_text(data.get("extra"), LONG_LIMIT)
    speaking = clean_text(data.get("speaking"), TEXT_LIMIT)
    boundaries = DEFAULT_ROLE_BOUNDARIES
    opening = clean_text(data.get("opening"), TEXT_LIMIT)

    role = {
        "name": name,
        "emoji": emoji,
        "tagline": tagline,
        "age": age,
        "gender": gender,
        "personality": personality,
        "deeds": deeds,
        "background": background,
        "extra": extra,
        "speaking": speaking,
        "boundaries": boundaries,
        "opening": opening,
        "source": "ai_search",
    }

    if not opening:
        role["opening"] = make_opening(role)

    if "没搜到" in search_text or "没有找到" in search_text:
        note = "没搜到现成资料，按常识整理的，建议你改一改。"
    else:
        note = "根据网上资料整理，可以直接改。"

    return role, note
