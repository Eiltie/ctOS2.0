"""旅游攻略的终端入口：跑这个文件就能在终端看攻略子图。

    python -X utf8 -m cli.guide

做法：直接跑攻略图，把四段产出打印出来。
注意：攻略会在景点清单处暂停等你勾选，终端里替你选「不改，直接排」接着跑完。
      想在「勾景点」这步真做选择，用网页。
"""

import uuid

from langgraph.types import Command

from databases.conn import query
from modules.trip.guide.stream import GUIDE_SECTION_KEYS, guide_graph


def _tenant_id():
    """取库里第一个租户的 id（一人一户，本地调试固定用它）。"""
    row = query("SELECT id FROM tenants ORDER BY id LIMIT 1")
    return row[0]["id"] if row else None


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
    """跑一次攻略。

    攻略会在「景点清单」处暂停等用户勾选。终端里没有界面，
    所以这里替用户点「不改，直接排」，一直恢复到跑完为止。
    """
    config = {"configurable": {"thread_id": "cli-" + uuid.uuid4().hex}}
    result = {}

    def drain(chunks):
        """消费一段事件流；返回 True 表示这次停下来等用户。"""
        paused = False
        for chunk in chunks:
            for node_name, update in chunk.items():
                if node_name == "__interrupt__":
                    paused = True
                    continue
                print(f"  √ {NODE_LABELS.get(node_name, node_name)}")
                if isinstance(update, dict):
                    result.update(update)
        return paused

    chunks = guide_graph.stream(
        {**INITIAL_STATE, "tenant_id": _tenant_id(), "user_query": query,
         "history": list(history)},
        config,
        stream_mode="updates",
    )
    paused = drain(chunks)

    # 每停一次就替用户确认一次，接着跑；直到不再暂停
    while paused:
        state = guide_graph.get_state(config)
        if not state.next:
            break
        print("  √ 景点清单出来了，按「不改，直接排」继续")
        paused = drain(
            guide_graph.stream(Command(resume={"removed": [], "added": ""}), config,
                               stream_mode="updates")
        )

    result.update(guide_graph.get_state(config).values)
    return result


def main() -> None:
    """终端主循环：读一句话 → 跑图 → 打印四段。"""
    history = []
    print("旅游攻略（输入 exit 退出）")
    print("（路线规划请用 python -X utf8 -m cli.route）")

    while True:
        try:
            query = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
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
