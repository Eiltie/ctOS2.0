import json
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_agent_tools import get_directions, get_weather, web_search
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_llm import get_llm
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_prompts import (
    PARSE_QUERY_PROMPT,
    PLANNER_PROMPT,
    ROUTE_PROMPT,
    ROUTE_TASK_PROMPT,
    SPOTS_PROMPT,
    SPOTS_TASK_PROMPT,
    WEATHER_SUMMARY_PROMPT,
)
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_state import AgentState

# 出行图的四个节点：天气 → 景点 → 行程 → 路线
# 循环次数上限
# 景点 Agent 最多搜几轮
MAX_SEARCH = 3

# 路线 Agent 最多问几轮
MAX_ROUTE_ROUNDS = 8


def weather_node(state: AgentState) -> dict:
    """节点一：解析需求、查真实天气、写成总结，返回目的地/天数/日期/天气。"""
    llm = get_llm()
    user_query = state["user_query"]

    today = date.today()
    prompt = (PARSE_QUERY_PROMPT
              .replace("{today}", str(today))
              .replace("{weekday}", "一二三四五六日"[today.weekday()])
              .replace("{tomorrow}", str(today + timedelta(days=1)))
              .replace("{user_query}", user_query))

    raw = llm.with_config(tags=["internal"]).invoke(prompt).content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(raw)
        destination = (parsed.get("destination") or "").strip()
    except (json.JSONDecodeError, AttributeError):
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


def spots_agent_node(state: AgentState) -> dict:
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
        result["spots"] = ai.content or "（本次没能生成景点推荐，请重试）"

    return result


def _count_searches(messages: list) -> int:
    """数已经搜过几次工具。"""
    return sum(len(m.tool_calls) for m in messages if getattr(m, "tool_calls", None))


def planner_node(state: AgentState) -> dict:
    """节点三：把景点排成逐日行程，返回 itinerary。"""
    prompt = (PLANNER_PROMPT
              .replace("{destination}", state["destination"])
              .replace("{days}", str(state["days"]))
              .replace("{start_date}", state["start_date"])
              .replace("{weather}", state["weather"])
              .replace("{spots}", state["spots"])
              .replace("{user_query}", state["user_query"]))

    itinerary = get_llm().invoke(prompt).content.strip()

    return {"itinerary": itinerary or "（本次没能生成行程安排，请重试）", "node_path": ["planner"]}


def route_agent_node(state: AgentState) -> dict:
    """节点四：带工具查路线的循环，返回 route_plan。"""
    messages = [
        SystemMessage(content=ROUTE_PROMPT),
        HumanMessage(content=ROUTE_TASK_PROMPT
                     .replace("{destination}", state["destination"])
                     .replace("{days}", str(state["days"]))
                     .replace("{start_date}", state["start_date"])
                     .replace("{user_query}", state["user_query"])
                     .replace("{itinerary}", state["itinerary"])),
    ]

    llm = get_llm().bind_tools([get_directions])

    # 循环藏在这个函数里：要查路线就替它查，查完接回消息再来一轮，不调工具就收工
    ai = None
    for _ in range(MAX_ROUTE_ROUNDS):
        ai = llm.invoke(messages)
        if not ai.tool_calls:
            break
        messages.append(ai)
        for call in ai.tool_calls:
            try:
                result = get_directions.invoke(call["args"])
            except Exception as e:
                result = f"这个查询没成功（{e}），请检查参数后重试。"
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

    # 轮次用完还在要工具：不给工具，让它用手上信息直接写路线
    if ai.tool_calls:
        ai = get_llm().invoke(messages)

    return {"route_plan": ai.content or "（本次没能生成路线，请重试）", "node_path": ["route_agent"]}
