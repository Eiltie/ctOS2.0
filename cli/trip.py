"""出行的终端入口：跑这个文件就能在终端看出行 Agent 怎么判断。

    python -X utf8 -m cli.trip

出行 Agent 会自己判断这一句该干嘛：
  自己答 / 交给路线规划子图 / 交给旅游攻略子图。
所以这里能看到「一句话进来，它决定走哪条路」。

输入 exit 退出。
"""

import asyncio
import json

from modules.trip.stream import trip_stream

# 数据库里默认租户的 id
TENANT_ID = 435


async def main():
    print("智能出行（输入 exit 退出）")
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
            async for chunk in trip_stream(query, history, tenant_id=TENANT_ID):
                _show(chunk)
        except Exception as e:
            print(f"\n（这次没跑通：{e}）")

        print()
        history.append(query)


def _show(chunk):
    """把一条 SSE 事件打印成人看得懂的样子。"""
    try:
        event = json.loads(chunk.removeprefix("data: ").strip())
    except Exception:
        return

    kind = event.get("kind")

    if kind == "TOKEN":
        # 逐字吐的内容，不换行
        print(event.get("text", ""), end="", flush=True)
    elif kind == "DONE":
        # 一段定稿了，补一个换行分开
        print("\n")
    elif kind == "CHAT":
        print(event.get("message", ""))
    elif kind == "SAY":
        print(f"  [{event.get('text', '')}]")
    elif kind == "START":
        print(f"  → 进入 {event.get('mode', '')} 流程")
    elif kind == "ERROR":
        print(f"  （出错了：{event.get('message', '')}）")


if __name__ == "__main__":
    asyncio.run(main())
