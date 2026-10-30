"""出行模块的终端调试入口。

只有手动运行时才会用到：
    python -X utf8 -m modules.trip.cli

不参与 Web 服务。真正的需求解析逻辑在 understand.py。
"""

from modules.trip.graph import build_graph
from modules.trip.understand import understand_query

# 输入这些词退出
EXIT_WORDS = {"exit", "quit", "q", "退出"}

# 节点名 → 中文名，调试时打印进度用
NODE_LABELS = {
    "weather": "查询天气",
    "spots_agent": "推荐景点",
    "tools": "搜索景点信息",
    "planner": "安排行程",
    "route_agent": "规划路线",
}

# 跑图的初始状态，字段要和 graph.AgentState 对齐
INITIAL_STATE = {
    "user_query": "",
    "destination": "",
    "days": 0,
    "start_date": "",
    "weather": "",
    "messages": [],
    "spots": "",
    "itinerary": "",
    "route_plan": "",
    "node_path": [],
}


def show(result: dict) -> None:
    """打印这一轮的产出：目的地信息加天气/景点/行程/路线四段。"""
    print("\n" + "=" * 56)
    print(f"目的地：{result['destination']}    天数：{result['days']}    出发：{result['start_date']}")
    print("=" * 56)
    print("\n【天气】\n" + result["weather"])
    print("\n【景点推荐】\n" + result["spots"])
    print("\n【行程安排】\n" + result["itinerary"])
    print("\n【详细路线】\n" + result["route_plan"])


def main() -> None:
    """终端主循环：读一句话 → 分流 → 跑图 → 打印。"""
    app = build_graph()
    history = []

    print("ctOS2.0-智能出行（输入 exit 退出）")

    while True:
        query = input("\n你：").strip()
        if query.lower() in EXIT_WORDS:
            print("再见！")
            break
        if not query:
            continue

        kind, content = understand_query(history, query)
        if kind == "CHAT":
            print(f"\n助手：{content}")
            history.append(query)
            continue

        print("\n正在规划中…")

        try:
            result = {}
            for chunk in app.stream(
                {**INITIAL_STATE, "user_query": content},
                stream_mode="updates",
            ):
                for node_name, update in chunk.items():
                    print(f"  √ {NODE_LABELS.get(node_name, node_name)}")
                    result.update(update)
            show(result)
        except Exception as e:
            print(f"\n（这次没跑通：{e}）")
            print("换个说法再试试？比如「下周想去杭州玩3天」")

        history.append(query)


if __name__ == "__main__":
    main()
