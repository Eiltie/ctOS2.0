"""路线规划的终端入口：跑这个文件就能在终端看路线决策子图。

    python -X utf8 -m cli.route

注意：路线要中途暂停让你选方案（人在回路）。终端里没有界面，
所以这里会自动替你选第一个方案，把后面的对比、推荐、提醒跑完。
想真选方案还是在网页里用。

输入 exit 退出。
"""

import json

from modules.trip.route.stream import start_route_decision

# 数据库里默认租户的 id
TENANT_ID = 435


def main():
    print("路线规划（输入 exit 退出）")
    history = []

    while True:
        try:
            query = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if query.lower() in ("exit", "quit", "q", "退出"):
            print("再见！")
            break
        if not query:
            continue

        print()
        try:
            events = start_route_decision(query, history, tenant_id=TENANT_ID)
            thread_id = _run(events, tenant_id=TENANT_ID)

            # 停在「选哪个方案」时，替用户选第一个
            if thread_id:
                print("\n  → 自动选方案 1")
                from modules.trip.route.stream import resume_route_decision

                _run(resume_route_decision(thread_id, "1", tenant_id=TENANT_ID),
                     tenant_id=TENANT_ID)
        except Exception as e:
            print(f"\n（这次没跑通：{e}）")

        print()
        history.append(query)


def _run(events, tenant_id):
    """跑完一串事件；返回要恢复的 thread_id（没暂停就返回 None）。"""
    thread_id = None

    for chunk in events:
        try:
            event = json.loads(chunk.removeprefix("data: ").strip())
        except Exception:
            continue

        kind = event.get("kind")

        if kind == "TOKEN":
            print(event.get("text", ""), end="", flush=True)
        elif kind == "DONE":
            print("\n")
        elif kind == "CHAT":
            print(event.get("message", ""))
        elif kind == "ASK":
            # 暂停等用户选：记下 thread_id，方便后面恢复
            thread_id = event.get("thread_id")
            print(f"  （需要选择：{event.get('message', event.get('question', ''))}）")
        elif kind == "ERROR":
            print(f"  （出错了：{event.get('message', '')}）")

    return thread_id


if __name__ == "__main__":
    main()
