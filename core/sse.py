"""SSE 事件的统一打包，以及“同步代码放进工作线程再吐 SSE”的小工具。

原来出行和客服各写了一份一模一样的 sse()，改动时容易只改一边。
出行模块的图是同步的，不能直接放在事件循环里跑，所以也把线程包装放在这里，
让 /trip/chat 和 /trip/route/choose 共用同一套逻辑。
"""

import asyncio
import json
import threading


def sse(event: dict) -> str:
    """把事件打包成一条 SSE 消息（末尾空行即结束）。"""
    # ensure_ascii=False：中文原样输出，不要转成 \u4f60 这种
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"


async def stream_from_thread(worker_generator, heartbeat_seconds=8):
    """把一个同步生成器放到工作线程里跑，边跑边把 SSE 字符串取回来。

    为什么要这样：
      同步的 LangGraph、数据库、高德请求都会卡住事件循环，
      期间已经 yield 的数据发不出去，浏览器会白屏到整个流程结束。
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    done = object()

    def worker():
        try:
            for item in worker_generator:
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", e))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, done)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
        except asyncio.TimeoutError:
            yield sse({"kind": "SAY", "text": "仍在处理中，请稍等…"})
            continue

        if item is done:
            break
        if isinstance(item, tuple) and item and item[0] == "error":
            yield sse({"kind": "ERROR", "message": f"这次没跑通：{item[1]}"})
            continue
        yield item
