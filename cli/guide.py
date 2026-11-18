"""旅游攻略的终端调试入口（不需要 Web 服务）。

    python -X utf8 -m modules.trip.guide.cli

做法：直接跑攻略图，把四段产出打印出来。
注意：路线决策要在网页里用（中途要暂停让你选方案），终端里只支持攻略。
      攻略本身也会在景点清单处暂停，终端里按"不改，直接排"继续。
"""

import sys
import uuid

from langgraph.types import Command

from modules.trip.guide.stream import GUIDE_SECTION_KEYS, guide_graph

# 输入这些词退出
EXIT_WORDS = {"exit", "quit", "q", "退出"}

# 节点名 → 中文名，调试时打印进度用
NODE_LABELS = {
    "weather": "查询天气",
    "spots_agent": "推荐景点",
    "tools": "搜索景点信息",
    "ask_spots": "确认景点",
    "planner": "安排行程",
    "advice": "写游玩建议",
}

# 跑图的初始状态，字段要和 modules/guide/state.py 的 GuideState 对齐
INITIAL_STATE = {
    "user_query": "",
    "history": [],
    "tenant_id": None,
    "chat_id": None,
    "destination": "",
    "days": 0,
    "start_date": "",
    "weather": "",
    "messages": [],
    "spots": "",
    "itinerary": "",
    "advice": "",
    "node_path": [],
}

# 四段正文的标题
SECTION_TITLES = {
    "weather": "【天气】",
    "spots": "【景点推荐】",
    "itinerary": "【行程安排】",
    "advice": "【游玩建议】",
}


def show(result: dict) -> None:
    """打印这一轮的产出：目的地信息加四段正文。"""
    print("\n" + "=" * 56)
    print(f"目的地：{result.get('destination')}    "
          f"天数：{result.get('days')}    出发：{result.get('start_date')}")
    print("=" * 56)

    for key in GUIDE_SECTION_KEYS:
        print("\n" + SECTION_TITLES[key] + "\n" + (result.get(key) or "（没有产出）"))


def run_once(query, history):
    """跑一次攻略；停在景点清单就替用户点"确认"，接着跑完。"""
    config = {"configurable": {"thread_id": "cli-" + uuid.uuid4().hex}}
    result = {}

    chunks = guide_graph.stream(
        {**INITIAL_STATE, "user_query": query, "history": list(history)},
        config,
        stream_mode="updates",
    )

    for chunk in chunks:
        for node_name, update in chunk.items():
            if node_name == "__interrupt__":
                print("  √ 景点清单出来了，按「不改，直接排」继续")
                continue
            print(f"  √ {NODE_LABELS.get(node_name, node_name)}")
            result.update(update)

    # 停在景点清单时，替用户确认，接着跑完
    state = guide_graph.get_state(config)
    if state.next:
        print("  √ 继续排行程")
        for chunk in guide_graph.stream(Command(resume={}), config, stream_mode="updates"):
            for node_name, update in chunk.items():
                print(f"  √ {NODE_LABELS.get(node_name, node_name)}")
                result.update(update)

        result.update(guide_graph.get_state(config).values)

    return result


def main() -> None:
    """终端主循环：读一句话 → 跑图 → 打印四段。"""
    if "--mode=route" in sys.argv or "--route" in sys.argv:
        print("路线决策需要在网页里用（中途要暂停让你选方案），终端只能跑旅游攻略。")
        return

    history = []
    print("ctOS2.0-旅游攻略（输入 exit 退出）")

    while True:
        query = input("\n你：").strip()
        if query.lower() in EXIT_WORDS:
            print("再见！")
            break
        if not query:
            continue

        print("\n正在规划中…")
        try:
            show(run_once(query, history))
        except Exception as e:
            print(f"\n（这次没跑通：{e}）")
            print("换个说法再试试？比如「下周想去杭州玩3天」")

        history.append(query)


if __name__ == "__main__":
    main()
