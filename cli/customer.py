"""客服的终端入口：跑这个文件就能在终端问客服。

    python -X utf8 -m cli.customer

输入 exit 退出。
"""

import asyncio
import json

from modules.customer.stream import customer_stream


async def main():
    print("智能客服（输入 exit 退出）")
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

        print("\n客服：", end="", flush=True)
        reply = ""
        try:
            # customer_stream 吐的是 SSE 字符串，要解析成事件再打印
            async for chunk in customer_stream(query, history):
                event = json.loads(chunk.removeprefix("data: ").strip())

                if event["kind"] == "TOKEN":
                    reply += event["text"]
                    print(event["text"], end="", flush=True)
                elif event["kind"] == "DONE":
                    # TOKEN 是逐字吐的，DONE 是定稿全文；
                    # 以 DONE 为准，避免两边都打印导致重复
                    reply = event["text"]
                elif event["kind"] == "ERROR":
                    print(f"\n（出错了：{event['message']}）")
        except Exception as e:
            print(f"\n（这次没跑通：{e}）")

        print()
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    asyncio.run(main())
