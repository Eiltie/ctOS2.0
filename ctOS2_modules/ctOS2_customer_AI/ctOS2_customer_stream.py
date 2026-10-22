import asyncio
import json
import sys
import threading
from pathlib import Path

from langchain_core.messages import AIMessageChunk

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.create_graph import INITIAL_STATE, build_graph
from ctOS2_modules.ctOS2_customer_AI.rag_store import load_store

# 客服模块的对外出口：ctOS_chat_api 只 import 这里的 customer_stream
customer_graph = build_graph()

# 逐字推送与事件字段
MAX_TOKENS = 20000

# 产出答案的字段名；图里改了名就改这里
ANSWER_KEY = "answer"


def sse(event: dict) -> str:
    """把事件打包成一条 SSE 消息（末尾空行即结束）。"""
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def startup_check() -> None:
    """启动检查：确认知识库、向量库、密钥都正常，有问题抛 RuntimeError。"""
    load_store()


async def customer_stream(query: str):
    """跑一次客服图，边跑边吐 SSE 事件，对外唯一入口。"""
    yield sse({"kind": "START"})

    token_count = 0

    try:
        # graph.stream() 是同步的，直接 for 会卡死事件循环，所以放进线程池跑
        async for mode, payload in _stream_in_thread(query):
            if mode == "messages":
                chunk, meta = payload

                if meta.get("langgraph_node") != "generate":
                    continue
                if not isinstance(chunk, AIMessageChunk) or not chunk.content:
                    continue

                if token_count >= MAX_TOKENS:
                    continue
                token_count += len(chunk.content)
                yield sse({"kind": "TOKEN", "text": chunk.content})

            else:
                for _, update in payload.items():
                    if update.get(ANSWER_KEY):
                        yield sse({"kind": "DONE", "text": update[ANSWER_KEY]})

    except Exception as e:
        yield sse({"kind": "ERROR", "message": f"这次没跑通：{e}"})


async def _stream_in_thread(query: str):
    """在线程池里跑同步的图，把产出逐条转回异步侧。"""
    # 图在工作线程里跑，产出丢进队列；异步侧从队列取，两边互不阻塞
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    DONE = object()

    def worker():
        """工作线程：跑图，把每条产出塞进队列，结束再塞一个哨兵。"""
        try:
            for item in customer_graph.stream(
                {**INITIAL_STATE, "user_query": query},
                stream_mode=["updates", "messages"],
            ):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, DONE)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        item = await queue.get()
        if item is DONE:
            break
        yield item


if __name__ == "__main__":
    # 单独跑这个文件 = 用一条问题验一遍事件能否正常吐出来
    async def demo():
        """用一条问题跑一遍封装，确认事件能正常吐出来。"""
        count = 0
        async for chunk in customer_stream("这个项目有哪些模块？"):
            event = json.loads(chunk.removeprefix("data: ").strip())

            if event["kind"] == "START":
                print("收到 START（前端此时显示：正在检索…）\n")
            elif event["kind"] == "TOKEN":
                count += 1
                print(event["text"], end="", flush=True)
            elif event["kind"] == "DONE":
                print(f"\n\n收到 DONE（定稿 {len(event['text'])} 字，"
                      f"过程收到 {count} 个 TOKEN）")
            elif event["kind"] == "ERROR":
                print(f"\n收到 ERROR：{event['message']}")

    asyncio.run(demo())
