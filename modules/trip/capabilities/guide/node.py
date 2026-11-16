"""旅游攻略｜四个图节点的实现

做什么：weather 解析需求+查天气，spots 搜景点，planner 排行程，advice 写游玩建议。
被谁用：modules/guide/graph.py 注册为节点。
注意：spots 的循环在图里（conditional_edges），其余节点都是一次模型调用。
"""

import json
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm
from core.tools.search import web_search
from core.tools.weather import get_weather
from modules.trip.capabilities.guide.prompts import (
    ADVICE_PROMPT,
    PARSE_QUERY_PROMPT,
    PLANNER_PROMPT,
    SPOTS_PROMPT,
    SPOTS_TASK_PROMPT,
    WEATHER_SUMMARY_PROMPT,
)
from modules.trip.capabilities.guide.state import GuideState

# 景点 Agent 最多搜几轮
MAX_SEARCH = 3


def weather_node(state: GuideState) -> dict:
    """节点一：解析需求、查真实天气、写成总结，返回目的地/天数/日期/天气。"""
    llm = get_llm()
    user_query = state["user_query"]

    # 历史用来接"改成5天""换成成都"这种补充；没聊过就给一句占位
    history_text = "\n".join(state.get("history") or []) or "（还没聊过）"

    today = date.today()
    prompt = (PARSE_QUERY_PROMPT
              .replace("{today}", str(today))
              .replace("{weekday}", "一二三四五六日"[today.weekday()])
              .replace("{tomorrow}", str(today + timedelta(days=1)))
              .replace("{history}", history_text)
              .replace("{user_query}", user_query))

    raw = llm.with_config(tags=["internal"]).invoke(prompt).content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(raw)
        destination = (parsed.get("destination") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        parsed = {}
        destination = ""

    if not destination:
        raise ValueError(f"没能从「{user_query}」里识别出目的地。把话说具体点试试，"
                         f"比如「下周想去杭州玩3天」。")

    days = int(parsed["days"])
    start_date = parsed["start_date"]

    weather_data = get_weather.invoke({
        "city": destination, "days": days, "start_date": start_date,
    })

    prompt = (WEATHER_SUMMARY_PROMPT
              .replace("{weather_data}", weather_data)
              .replace("{user_query}", user_query))
    summary = llm.invoke(prompt).content.strip()

    return {
        "destination": destination,
        "days": days,
        "start_date": start_date,
        "weather": summary,
        "node_path": ["weather"],
    }


def split_spot_names(text):
    """把景点清单里最后一行"景点清单：A、B、C"拆出来，返回（去掉这一行的正文, 名字列表）。

    模型偶尔漏写或写歪，这时候正文原样返回、名字列表为空，不影响原来的显示。
    """
    if not text:
        return text, []

    lines = text.rstrip().split("\n")

    for index in range(len(lines) - 1, -1, -1):
        line = lines[index].strip()
        if not line:
            continue

        if not line.startswith("景点清单"):
            break

        content = line.split("：", 1)[-1] if "：" in line else line.split(":", 1)[-1]
        names = [name.strip() for name in content.split("、") if name.strip()]

        body = "\n".join(lines[:index]).rstrip()
        return body, names

    return text, []


def spots_agent_node(state: GuideState) -> dict:
    """节点二：景点 ReAct 循环，没调工具时返回最终景点清单。"""
    history = state["messages"]

    opening = []
    if not history:
        opening = [
            SystemMessage(content=SPOTS_PROMPT),
            HumanMessage(content=SPOTS_TASK_PROMPT
                         .replace("{destination}", state["destination"])
                         .replace("{days}", str(state["days"]))
                         .replace("{start_date}", state["start_date"])
                         .replace("{weather}", state["weather"])
                         .replace("{user_query}", state["user_query"])),
        ]
        history = opening

    llm = get_llm()

    # 搜够次数就不给工具，逼它直接出清单；在路由里 END 会让 spots 为空
    if _count_searches(history) < MAX_SEARCH:
        llm = llm.bind_tools([web_search])

    ai = llm.invoke(history)

    result = {"messages": opening + [ai], "node_path": ["spots_agent"]}
    if not ai.tool_calls:
        text = ai.content or "（本次没能生成景点推荐，请重试）"
        body, names = split_spot_names(text)
        result["spots"] = body
        result["spot_names"] = names

    return result


def _count_searches(messages: list) -> int:
    """数已经搜过几次工具。"""
    return sum(len(m.tool_calls) for m in messages if getattr(m, "tool_calls", None))


def planner_node(state: GuideState) -> dict:
    """节点三：把景点排成逐日行程，返回 itinerary。"""
    prompt = (PLANNER_PROMPT
              .replace("{destination}", state["destination"])
              .replace("{days}", str(state["days"]))
              .replace("{start_date}", state["start_date"])
              .replace("{weather}", state["weather"])
              .replace("{spots}", state["spots"])
              .replace("{user_query}", state["user_query"])
              .replace("{removed_spots}", format_name_list(state.get("removed_spots") or []))
              .replace("{added_spot}", (state.get("added_spot") or "").strip() or "（没有补充）"))

    itinerary = get_llm().invoke(prompt).content.strip()

    return {"itinerary": itinerary or "（本次没能生成行程安排，请重试）", "node_path": ["planner"]}


def format_name_list(names):
    """把名字列表拼成"A、B"这种样子，空列表给一个说明。"""
    names = [name.strip() for name in names if name and str(name).strip()]
    if not names:
        return "（没有要去掉的）"
    return "、".join(names)


def advice_node(state: GuideState) -> dict:
    """节点四：写游玩建议，返回 advice。

    这一段替代了拆分前的 route_agent（那个节点会用高德查每天的移动）。
    现在攻略不碰地图：需要精确路线时，交给路线规划模块。
    """
    prompt = (ADVICE_PROMPT
              .replace("{destination}", state["destination"])
              .replace("{days}", str(state["days"]))
              .replace("{start_date}", state["start_date"])
              .replace("{weather}", state["weather"])
              .replace("{itinerary}", state["itinerary"])
              .replace("{user_query}", state["user_query"]))

    text = get_llm().invoke(prompt).content.strip()

    return {"advice": text or "（本次没能生成游玩建议，请重试）", "node_path": ["advice"]}
