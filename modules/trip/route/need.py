"""路线规划｜需求解析

做什么：把"用户这句话 + 前几轮说过的话"变成一份结构化的路线需求，
        再检查起点/终点/城市够不够、去地图上把地点查出来。
被谁用：modules/trip/route/stream.py。
注意：不生成给用户看的结论，只负责"搞清楚用户要什么"。

为什么单独成文件：
  拆分之后没有了统一的意图分流，多轮补充（"改成明天下午3点""那坐地铁呢"）
  必须在各自模块里接上。路线这边就靠这里的 {history} 占位。
"""

import json
from datetime import date, datetime, timedelta

from common.llm import get_llm
from modules.trip.amap import find_place
from modules.trip.weather import get_weather
from modules.trip.route.prompts import PARSE_ROUTE_NEED_PROMPT
from modules.trip.route.tools import normalize_preference, normalize_want_mode

# 这些词太笼统，直接查地图会认错地方，先反问用户
VAGUE_PLACES = {
    "家", "我家", "学校", "我们学校", "公司", "单位",
    "这里", "附近", "当前位置", "我这",
}


def parse_route_need(user_query, history=None):
    """把需求解析成路线字段；解析失败返回 None。

    history 是前几轮用户说过的话。用户常说"改成8点""那坐地铁呢"这类碎片，
    只喂最新一句会丢失起点终点，所以这里让模型一次把历史合进来。
    """
    today = date.today()
    now = datetime.now()

    history_text = "\n".join(history or []) or "（还没聊过）"

    prompt = (PARSE_ROUTE_NEED_PROMPT
              .replace("{today}", str(today))
              .replace("{weekday}", "一二三四五六日"[today.weekday()])
              .replace("{now}", now.strftime("%Y-%m-%d %H:%M"))
              .replace("{tomorrow}", str(today + timedelta(days=1)))
              .replace("{history}", history_text)
              .replace("{user_query}", user_query))

    raw = get_llm().with_config(tags=["internal"]).invoke(prompt).content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, AttributeError):
        return None

    if not isinstance(data, dict):
        return None

    return {
        "origin": str(data.get("origin") or "").strip(),
        "destination": str(data.get("destination") or "").strip(),
        "city": str(data.get("city") or "").strip(),
        "departure_time": str(data.get("departure_time") or "").strip(),
        "preference": normalize_preference(str(data.get("preference") or "")),
        "companions": str(data.get("companions") or "").strip(),
        "want_mode": normalize_want_mode(str(data.get("want_mode") or "")),
        "avoid": str(data.get("avoid") or "").strip(),
        "notes": str(data.get("notes") or "").strip(),
    }


def check_need(need):
    """检查起点、终点、城市够不够，返回一句要问用户的话；没问题返回空字符串。"""
    origin = need["origin"]
    destination = need["destination"]
    city = need["city"]

    if not origin:
        return "起点是哪？说个地标、小区或车站，我就能查路线。比如「从杭州东站到灵隐寺」。"
    if not destination:
        return "终点是哪？说个具体地点，我就能查路线。"
    if origin in VAGUE_PLACES:
        return f"「{origin}」太笼统了，具体是哪个小区、校区或哪条路？说个地标或地址就行。"
    if destination in VAGUE_PLACES:
        return f"「{destination}」太笼统了，具体是哪个地方？说个景点名或地址就行。"
    if not city:
        return f"「{destination}」在哪个城市？告诉我城市名，我就能查路线。"

    return ""


def find_places(need):
    """查起点和终点，返回（起点, 终点, 要问用户的话）。

    起点是开放的：用户在北京，要去别的城市也可以。
    终点如果没城市又全国都查不到，就回去问是哪个城市，别硬猜。
    """
    start = find_place(need["origin"], need["city"], allow_nationwide=True)
    if start is None:
        return None, None, (
            f"没找到起点「{need['origin']}」，能说具体一点吗？"
            f"比如加上城市或附近的路。"
        )
    if start.get("too_vague"):
        return None, None, (
            f"「{need['origin']}」我查到的是「{start.get('address') or start.get('city')}」，"
            f"不太确定。能说具体一点吗？比如景点全称或附近的路。"
        )

    end = find_place(need["destination"], need["city"])

    # 有城市时按城市查；没有城市时全国查，查不到再问是哪个城市
    if end is None and not need["city"]:
        end = find_place(need["destination"], "", allow_nationwide=True)

    if end is None:
        return None, None, (
            f"没找到终点「{need['destination']}」（城市：{need['city']}），"
            f"能说具体一点吗？比如景点全称。"
        )
    if end.get("too_vague"):
        return None, None, (
            f"「{need['destination']}」我查到的是「{end.get('address') or end.get('city')}」，"
            f"不太确定。能说具体一点吗？"
        )

    return start, end, ""


def get_weather_text(need):
    """查出发当天的天气；查不到就返回空字符串。"""
    city = need.get("city") or ""
    if not city:
        return ""

    departure_time = need.get("departure_time") or ""
    weather_date = departure_time[:10] if departure_time[:10] else str(date.today())

    try:
        return get_weather.invoke({
            "city": city,
            "days": 1,
            "start_date": weather_date,
        })
    except Exception as e:
        print(f"[路线] 天气查询失败：{e}")
        return ""


def build_initial_state(query, need, start, end, weather_text, need_text, tenant_id):
    """把进图前准备好的字段装成一个完整的状态。"""
    return {
        "user_query": query,
        "tenant_id": tenant_id,
        "need": need,
        "start_place": start,
        "end_place": end,
        "weather_text": weather_text,
        "need_text": need_text,
        "route_need": need_text,
        "choices": [],
        "recommended_index": -1,
        "candidate_text": "",
        "problem": "",
        "choice_id": "",
        "choice_id_name": "",
        "choice_index": -1,
        "route_compare": "",
        "route_decision": "",
        "route_tips": "",
        "node_path": [],
    }
