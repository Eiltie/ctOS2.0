import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_create_graph import build_graph
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_llm import get_llm
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_prompts import UNDERSTAND_QUERY_PROMPT

EXIT_WORDS = {"exit", "quit", "q", "退出"}

NODE_LABELS = {
    "weather": "查询天气",
    "spots_agent": "推荐景点",
    "tools": "搜索景点信息",
    "planner": "安排行程",
    "route_agent": "规划路线",
}


def understand_query(history: list[str], query: str) -> tuple[str, str]:
    """判定这一句是出行需求（TRAVEL，内容是合并后的完整需求）还是闲聊（CHAT，内容是回复）。"""
    prompt = (UNDERSTAND_QUERY_PROMPT
              .replace("{history}", "\n".join(history) or "（还没聊过）")
              .replace("{query}", query))
    reply = get_llm().invoke(prompt).content.strip()

    # 约定：第一行只写 TRAVEL 或 CHAT，第二行开始是正文
    lines = reply.split("\n", 1)
    kind = lines[0].strip().upper()
    body = lines[1].strip() if len(lines) > 1 else ""

    if kind.startswith("CHAT"):
        return "CHAT", body
    return "TRAVEL", body or reply      # 模型没守格式时按出行需求处理，避免卡住


def show(result: dict) -> None:
    """打印这一轮的产出：目的地信息 + 天气 / 景点 / 行程 / 路线 四段。"""
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
    history = []                        # 用户说过的话，一句一条

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
            continue                # 闲聊直接等下一句

        ##print(f"（理解为：{content}）")
        print("\n正在规划中…")

        try:
            result = {}
            # 用 stream 而非 invoke：每跑完一个节点就吐一次，可逐行报告进度
            for chunk in app.stream({
                "user_query": content,
                "destination": "",
                "days": 0,
                "start_date": "",
                "weather": "",
                "messages": [],      # ReAct 循环的中间消息，初始为空，由景点节点填充
                "spots": "",
                "itinerary": "",
                "route_plan": "",
                "node_path": [],
            }, stream_mode="updates"):
                for node_name, update in chunk.items():
                    print(f"  √ {NODE_LABELS.get(node_name, node_name)}")
                    result.update(update)
            show(result)
        except Exception as e:
            # 兜底：万一哪一步出了意外，也别让程序退出，下一句还能接着聊
            print(f"\n（这次没跑通：{e}）")
            print("换个说法再试试？比如「下周想去杭州玩3天」")

        history.append(query)


if __name__ == "__main__":
    main()
