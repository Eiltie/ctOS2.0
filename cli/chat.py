"""对话的终端入口：跑这个文件就能在终端跟对话 bot 聊天。

    python -X utf8 -m cli.chat

输入 exit 退出。
"""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage

from modules.chat.stream import run_graph

# 数据库里默认租户的 id（一人一户，本地调试固定用它）
TENANT_ID = 435


async def main():
    print("对话（输入 exit 退出）")
    history = []

    while True:
        try:
            query = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            # 管道输入读完 / Ctrl+C：直接退出，不打一堆报错
            print("\n再见！")
            break
        if query.lower() in ("exit", "quit", "q", "退出"):
            print("再见！")
            break
        if not query:
            continue

        print("\nbot：", end="", flush=True)
        reply = ""
        try:
            # run_graph 要传「消息列表」，和 api/routes/chat.py 一样
            async for chunk in run_graph(history + [HumanMessage(content=query)],
                                         tenant_id=TENANT_ID):
                reply += chunk
                print(chunk, end="", flush=True)
        except Exception as e:
            print(f"\n（这次没跑通：{e}）")

        print()

        # 把这一轮存进历史，下一句能接着聊
        history.append(HumanMessage(content=query))
        history.append(AIMessage(content=reply))


if __name__ == "__main__":
    asyncio.run(main())
