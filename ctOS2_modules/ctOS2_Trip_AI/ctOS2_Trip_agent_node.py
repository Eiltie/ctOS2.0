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

MAX_SEARCH = 3          # 景点 Agent 最多搜几轮
MAX_ROUTE_ROUNDS = 8    # 路线 Agent 最多问几轮


#节点一：查询天气

def weather_node(state: AgentState) -> dict:
    """返回 destination / days / start_date / weather。"""
    llm = get_llm()
    user_query = state["user_query"]

    #解析需求（日期占位符由代码算好，模型只做认字）
    today = date.today()
    prompt = (PARSE_QUERY_PROMPT
              .replace("{today}", str(today))
              .replace("{weekday}", "一二三四五六日"[today.weekday()])
              .replace("{tomorrow}", str(today + timedelta(days=1)))
              .replace("{user_query}", user_query))
    # tags=["internal"]：本意是让这次产出不逐字流给用户。
    # 实测本版本组合下流元信息里没有 tags，这道过滤在 API 层无效，处理办法待 API 关再定（详见 temp 细节文件）
    raw = llm.with_config(tags=["internal"]).invoke(prompt).content.strip()
    # 容错：LLM 常把 JSON 裹在 ```json ... ``` 代码块里
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

    #查真实天气（直接调工具，不经 LLM）
    weather_data = get_weather.invoke({
        "city": destination, "days": days, "start_date": start_date,
    })

    #天气数据写成给人看的总结
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


#节点二：推荐景点(图级 ReAct)

def spots_agent_node(state: AgentState) -> dict:
    """返回 messages / spots（会被反复执行，直到不再调工具）。"""
    history = state["messages"]

    #第一轮才拼开场白：System 是规矩，Human 是任务书
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

    #搜够次数就不给工具，逼它直接出清单（刹车踩在"给不给工具"上，而不是在路由里直接 END——
    #否则模型没有机会输出最终清单，spots 会是空的）
    llm = get_llm()
    if _count_searches(history) < MAX_SEARCH:
        llm = llm.bind_tools([web_search])

    ai = llm.invoke(history)

    #没调工具 = 这条就是最终清单
    result = {"messages": opening + [ai], "node_path": ["spots_agent"]}
    if not ai.tool_calls:
        result["spots"] = ai.content or "（本次没能生成景点推荐，请重试）"

    return result


def _count_searches(messages: list) -> int:
    """数已经搜过几次：把每条 AI 消息里的 tool_calls 加起来。"""
    return sum(len(m.tool_calls) for m in messages if getattr(m, "tool_calls", None))


#节点三：安排行程（纯推理）

def planner_node(state: AgentState) -> dict:
    """返回 itinerary。"""
    #原料都在 state 里，不调工具：填提示词 → 调一次 LLM → 交结果
    prompt = (PLANNER_PROMPT
              .replace("{destination}", state["destination"])
              .replace("{days}", str(state["days"]))
              .replace("{start_date}", state["start_date"])
              .replace("{weather}", state["weather"])
              .replace("{spots}", state["spots"])
              .replace("{user_query}", state["user_query"]))

    itinerary = get_llm().invoke(prompt).content.strip()

    return {"itinerary": itinerary or "（本次没能生成行程安排，请重试）", "node_path": ["planner"]}


#节点四：规划路线（节点内 ReAct）

def route_agent_node(state: AgentState) -> dict:
    """返回 route_plan。"""
    messages = [
        SystemMessage(content=ROUTE_PROMPT),
        HumanMessage(content=ROUTE_TASK_PROMPT
                     .replace("{destination}", state["destination"])
                     .replace("{days}", str(state["days"]))
                     .replace("{start_date}", state["start_date"])
                     .replace("{user_query}", state["user_query"])
                     .replace("{itinerary}", state["itinerary"])),
    ]

    #把查路线的工具交给它（循环藏在本函数内部，图上只是个普通节点）
    llm = get_llm().bind_tools([get_directions])

    #循环：它要查路线就替它查，查完接回消息再来一轮；它不再调工具就收工
    ai = None
    for _ in range(MAX_ROUTE_ROUNDS):
        ai = llm.invoke(messages)
        if not ai.tool_calls:
            break
        messages.append(ai)
        for call in ai.tool_calls:
            try:
                result = get_directions.invoke(call["args"])
            except Exception as e:      # 参数传错（比如漏了 city）也别让程序崩
                result = f"这个查询没成功（{e}），请检查参数后重试。"
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

    #轮次用完还在要工具：不给工具，让它用手上信息直接写路线
    if ai.tool_calls:
        ai = get_llm().invoke(messages)

    return {"route_plan": ai.content or "（本次没能生成路线，请重试）", "node_path": ["route_agent"]}
