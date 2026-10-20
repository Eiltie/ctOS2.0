"""智能客服 · 流式封装（对应出行侧的 ctOS2_Trip_stream.py）。

这是模块对外唯一的出入口。Web 层只要 import 这一个函数：

    customer_stream(query)  ->  async 生成器，吐 SSE 文本片段

调用方（将来的 /customer/chat 路由）拿它直接塞进 StreamingResponse 就行，
不需要知道图长什么样、有几个节点、三层检索怎么跑。

设计约定：
    · 检索过程【不给用户看】，事件里只带最终答案。
      三层命中什么是调试信息，终端入口 main.py 会打印，但不走 Web。
    · 事件协议和出行模块保持同一套命名，前端好复用。

事件协议（前端按 kind 分派）：
    START  开始跑图（前端显示「正在检索…」）
    TOKEN  答案逐字碎片（打字机效果）
    DONE   答案定稿（前端用它重渲染，纠正逐字拼接的偏差）
    ERROR  跑图途中出错
"""

import asyncio
import json
import sys
import threading
from pathlib import Path

from langchain_core.messages import AIMessageChunk

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.create_graph import INITIAL_STATE, build_graph
from ctOS2_modules.ctOS2_customer_AI.rag_store import load_store

# 图只编译一次，之后所有请求复用（编译有开销）
customer_graph = build_graph()

# 逐字推送的字数上限，防止极端情况下无限推送
MAX_TOKENS = 20000

# 产出答案的字段名。图以后改名就改这里，外部不用动。
ANSWER_KEY = "answer"


def sse(event: dict) -> str:
    """把事件数据打包成一条 SSE 消息（末尾空行即本条结束）。"""
    # ensure_ascii=False：中文原样发送，不转成 \uXXXX
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


def startup_check() -> None:
    """启动检查：确认知识库、向量库、密钥都正常。

    加载不出来会抛 RuntimeError，由调用方决定怎么处理。
    放在这里是为了让 Web 层不用关心知识库在哪、依赖什么。
    """
    load_store()


async def customer_stream(query: str):
    """跑一次客服图，边跑边吐 SSE 文本片段。

    这是模块对外唯一需要调用的东西。
    """
    yield sse({"kind": "START"})

    token_count = 0          # 已推送的字数（上限用）

    try:
        # 【关键】graph.stream() 是【同步】的：它跑的时候会一直占着当前线程，
        # 如果直接在这里 for，整个服务的事件循环会被卡住——
        # 期间其他接口（连首页 / 都算）全部无响应。
        # 所以把它丢进线程池跑，事件循环就空出来了，其他请求照常处理。
        async for mode, payload in _stream_in_thread(query):
            if mode == "messages":
                # payload = (消息片段, 元信息)
                chunk, meta = payload

                # 只要生成节点产出的文字，检索节点不产正文
                if meta.get("langgraph_node") != "generate":
                    continue
                if not isinstance(chunk, AIMessageChunk) or not chunk.content:
                    continue

                if token_count >= MAX_TOKENS:
                    continue
                token_count += len(chunk.content)
                yield sse({"kind": "TOKEN", "text": chunk.content})

            else:
                # 某个节点跑完了：如果这轮产出了答案，就发一条 DONE
                for _, update in payload.items():
                    if update.get(ANSWER_KEY):
                        yield sse({"kind": "DONE", "text": update[ANSWER_KEY]})

    except Exception as e:
        # 出错也别让流断掉：把错误当一条事件发出去，前端好显示
        yield sse({"kind": "ERROR", "message": f"这次没跑通：{e}"})


async def _stream_in_thread(query: str):
    """在线程池里跑同步的图，把产出逐条转交回异步侧。

    做法：图在工作线程里跑，每产出一条就丢进队列；
    异步侧从队列取，取到一条就 yield 一条。
    这样两边互不阻塞，事件循环始终是空的。
    """
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    DONE = object()                 # 队列结束的哨兵

    def worker():
        """工作线程：跑图，把每条产出塞进队列。"""
        try:
            for item in customer_graph.stream(
                {**INITIAL_STATE, "user_query": query},
                stream_mode=["updates", "messages"],
            ):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        finally:
            # 无论成功失败都要通知异步侧收工，否则它会一直等下去
            loop.call_soon_threadsafe(queue.put_nowait, DONE)

    # 起一个后台线程跑图（跑完自己结束）
    threading.Thread(target=worker, daemon=True).start()

    while True:
        item = await queue.get()
        if item is DONE:
            break
        yield item


if __name__ == "__main__":
    # 单独运行本文件 = 用一条假问题跑一遍封装，确认事件能正常吐出来
    import asyncio

    async def demo():
        count = 0                                   # 收到多少个 TOKEN（看流式是否真的逐字）
        async for chunk in customer_stream("这个项目有哪些模块？"):
            # chunk 形如 "data: {...}\n\n"，这里只把内容抠出来看
            event = json.loads(chunk.removeprefix("data: ").strip())

            if event["kind"] == "START":
                print("收到 START（前端此时显示：正在检索…）\n")
            elif event["kind"] == "TOKEN":
                count += 1
                print(event["text"], end="", flush=True)    # 逐字吐，不换行
            elif event["kind"] == "DONE":
                print(f"\n\n收到 DONE（定稿 {len(event['text'])} 字，"
                      f"过程收到 {count} 个 TOKEN）")
            elif event["kind"] == "ERROR":
                print(f"\n收到 ERROR：{event['message']}")

    asyncio.run(demo())
