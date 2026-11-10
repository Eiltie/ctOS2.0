"""出行｜路线决策的小图

做什么：查候选路线 → 暂停让人选 → 写对比/推荐/提醒。
被谁用：modules/trip/route_decision_stream.py。
注意：暂停用 LangGraph 的 interrupt，状态存在 databases/route_checkpoints.sqlite。
      这个文件是运行产物，已经在 .gitignore 里。
"""

import operator
import sqlite3
from pathlib import Path
from typing import Annotated, NotRequired, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from core.llm import get_llm
from modules.trip.route_decision_prompts import (
    ROUTE_COMPARE_PROMPT,
    ROUTE_DECISION_PROMPT,
    ROUTE_TIPS_PROMPT,
)
from modules.trip.route_decision_tools import (
    choose_recommended,
    collect_route_choices,
    format_choice_label,
    format_choice_text,
    get_choice_name,
    normalize_want_mode,
)

# 节点名 -> 逐字输出时贴到哪一段。只列会调模型的节点
ROUTE_TOKEN_KEYS = {
    "compare_routes": "route_compare",
    "decide_route": "route_decision",
    "write_tips": "route_tips",
}

# 四个段落的名字，写库和前端都用这一套
ROUTE_SECTION_KEYS = ("route_need", "route_compare", "route_decision", "route_tips")


class RouteState(TypedDict):
    # 进图之前就准备好的信息
    user_query: str
    merged_query: str
    tenant_id: int
    need: dict
    start_place: dict
    end_place: dict
    weather_text: str
    need_text: str

    # 查完候选后填
    choices: list
    recommended_index: int
    candidate_text: str
    problem: str

    # 暂停回来填
    choice_id: str
    choice_id_name: str
    choice_index: int

    # 最后四段正文
    route_need: str
    route_compare: str
    route_decision: str
    route_tips: str

    node_path: Annotated[NotRequired[list[str]], operator.add]


def collect_routes_node(state: RouteState) -> dict:
    """查候选路线，并按用户偏好先算一条推荐。"""
    need = state["need"]
    companions = need.get("companions", "")
    weather_text = state.get("weather_text", "")
    avoid = need.get("avoid", "")

    choices, note = collect_route_choices(
        state["start_place"],
        state["end_place"],
        companions=companions,
        weather_text=weather_text,
        avoid=avoid,
    )

    if not choices:
        return {"problem": note, "node_path": ["collect_routes"]}

    recommended = choose_recommended(
        choices,
        need.get("preference", "综合"),
        companions=companions,
        weather_text=weather_text,
        want_mode=normalize_want_mode(need.get("want_mode", "")),
    )

    candidate_text = format_choice_text(choices)
    if note:
        candidate_text += f"\n\n补充：{note}"

    return {
        "choices": choices,
        "recommended_index": recommended,
        "candidate_text": candidate_text,
        "problem": "",
        "node_path": ["collect_routes"],
    }


def route_after_collect(state: RouteState) -> str:
    """查到路线就去问用户，没查到就直接收尾。"""
    return "problem" if state.get("problem") else "ask"


def tell_problem_node(state: RouteState) -> dict:
    """查路线失败时走这里，真正的错误提示由外面的 stream 发。"""
    return {"node_path": ["tell_problem"]}


def make_choice_payload(state: RouteState) -> dict:
    """暂停时交给前端的内容：问题、候选按钮、系统推荐哪条。"""
    choices = state["choices"]
    recommended = state["recommended_index"]

    options = []
    for index, choice in enumerate(choices):
        options.append({
            "id": str(index + 1),
            "name": get_choice_name(index),
            "label": format_choice_label(choice),
            "note": choice.get("detail", ""),
        })

    return {
        "question": f"我查到了 {len(options)} 条路线，你想按哪条走？",
        "options": options,
        "recommended_id": str(recommended + 1),
        "recommended_name": get_choice_name(recommended),
        "recommended_text": (
            f"系统倾向{get_choice_name(recommended)}："
            f"{format_choice_label(choices[recommended])}。"
        ),
    }


def ask_user_node(state: RouteState) -> dict:
    """停在这里，等用户点一个方案。"""
    picked = interrupt(make_choice_payload(state))

    # 正常情况前端传回来的是 "1" / "2" 这样的字符串
    if isinstance(picked, dict):
        picked = picked.get("choice_id", "")

    picked = str(picked).strip()
    picked_index = find_picked_index(picked, state.get("choices") or [])

    return {
        "choice_id": picked,
        "choice_id_name": get_choice_name(picked_index) if picked_index >= 0 else "",
        "node_path": ["ask_user"],
    }


def find_picked_index(choice_id, choices):
    """把用户点的编号换成列表位置；对不上返回 -1。"""
    if not choice_id.isdigit():
        return -1

    index = int(choice_id) - 1
    if 0 <= index < len(choices):
        return index

    return -1


def find_choice_index(state: RouteState) -> int:
    """确定这次要写的是哪条路线；没选或选歪了就用系统推荐。"""
    index = find_picked_index(
        str(state.get("choice_id") or "").strip(),
        state.get("choices") or [],
    )

    if index >= 0:
        return index

    return state.get("recommended_index", 0)


def compare_routes_node(state: RouteState) -> dict:
    """把候选路线写成对比，标出用户选的那条。"""
    index = find_choice_index(state)
    choice = state["choices"][index]

    prompt = (ROUTE_COMPARE_PROMPT
              .replace("{need_text}", state["need_text"])
              .replace("{candidate_text}", state["candidate_text"])
              .replace("{chosen_name}", get_choice_name(index))
              .replace("{chosen_label}", format_choice_label(choice)))

    text = get_llm().invoke(prompt).content.strip()

    # 模型偶尔会把“你选的”标到别的方案上，这里按模板自己重写，保证标对
    text = mark_chosen_plan(text, get_choice_name(index))

    return {
        "choice_index": index,
        "route_compare": text or "（这次没能生成路线对比，请重试）",
        "node_path": ["compare_routes"],
    }


def decide_route_node(state: RouteState) -> dict:
    """说明为什么选这条，再给一个备选。"""
    index = state["choice_index"]
    choice = state["choices"][index]

    # 用户自己选的和系统推荐的可能不是同一条
    user_picked = state.get("choice_id_name") or get_choice_name(index)
    system_picked = get_choice_name(state.get("recommended_index", index))

    prompt = (ROUTE_DECISION_PROMPT
              .replace("{need_text}", state["need_text"])
              .replace("{candidate_text}", state["candidate_text"])
              .replace("{chosen_name}", get_choice_name(index))
              .replace("{chosen_label}", format_choice_label(choice))
              .replace("{user_picked}", user_picked)
              .replace("{system_picked}", system_picked))

    text = get_llm().invoke(prompt).content.strip()

    # 行首必须写成用户真正选的那条，防止模型拿系统推荐顶替
    text = force_line_prefix(text, f"推荐：{get_choice_name(index)}（{choice['mode_name']}）")

    return {
        "route_decision": text or "（这次没能生成推荐理由，请重试）",
        "node_path": ["decide_route"],
    }


def write_tips_node(state: RouteState) -> dict:
    """写出发时间和路上要注意的事。"""
    index = state["choice_index"]
    choice = state["choices"][index]

    prompt = (ROUTE_TIPS_PROMPT
              .replace("{need_text}", state["need_text"])
              .replace("{chosen_name}", get_choice_name(index))
              .replace("{chosen_label}", format_choice_label(choice)))

    text = get_llm().invoke(prompt).content.strip()

    return {
        "route_tips": text or "（这次没能生成出发提醒，请重试）",
        "node_path": ["write_tips"],
    }


def build_route_graph(checkpointer):
    """组装路线决策图。"""
    graph = StateGraph(RouteState)

    graph.add_node("collect_routes", collect_routes_node)
    graph.add_node("ask_user", ask_user_node)
    graph.add_node("compare_routes", compare_routes_node)
    graph.add_node("decide_route", decide_route_node)
    graph.add_node("write_tips", write_tips_node)
    graph.add_node("tell_problem", tell_problem_node)

    graph.add_edge(START, "collect_routes")
    graph.add_conditional_edges("collect_routes", route_after_collect, {
        "ask": "ask_user",
        "problem": "tell_problem",
    })
    graph.add_edge("tell_problem", END)
    graph.add_edge("ask_user", "compare_routes")
    graph.add_edge("compare_routes", "decide_route")
    graph.add_edge("decide_route", "write_tips")
    graph.add_edge("write_tips", END)

    return graph.compile(checkpointer=checkpointer)


# 检查点文件：刷新页面不影响，服务重启也能接着选
CHECKPOINT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "databases"
    / "route_checkpoints.sqlite"
)


def mark_chosen_plan(text, chosen_name):
    """对比文本里只让选中的那个方案带“（你选的）”。"""
    if not text:
        return text

    lines = []
    for line in text.split("\n"):
        body = line.replace("（你选的）", "").replace("(你选的)", "")
        if body.startswith(chosen_name + "｜"):
            body = body + "（你选的）"
        lines.append(body)

    return "\n".join(lines)


def force_line_prefix(text, prefix):
    """把第一行强制改成指定内容；模型写歪了也纠正回来。"""
    if not text:
        return prefix

    lines = text.split("\n")
    lines[0] = prefix
    return "\n".join(lines)


def make_checkpointer():
    """优先用文件存；文件打不开就退回内存，至少不影响其他模块。"""
    try:
        CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
        return SqliteSaver(connection)
    except Exception as e:
        print(f"[路线] 检查点文件打不开，改用内存：{e}")
        return MemorySaver()


# 路线决策和攻略共用这个检查点文件，靠线程号区分（攻略的线程号以 guide- 开头）
route_checkpointer = make_checkpointer()
route_graph = build_route_graph(route_checkpointer)
guide_checkpointer = route_checkpointer
