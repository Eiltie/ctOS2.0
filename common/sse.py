"""SSE 事件的统一打包，以及“同步代码放进工作线程再吐 SSE”的小工具。

原来出行和客服各写了一份一模一样的 sse()，改动时容易只改一边。
出行模块的图是同步的，不能直接放在事件循环里跑，所以也把线程包装放在这里，
让 /trip/chat 和 /trip/route/choose 共用同一套逻辑。
"""

import asyncio
import contextvars
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

    # 复制当前的 contextvars 传给工作线程。
    #
    # 为什么必须做：
    #   contextvars 是「按协程/线程隔离」的，新起的 threading.Thread
    #   拿到的是空白上下文。统计模块靠 contextvars 记「当前是哪次请求」，
    #   不复制的话线程里 stats.current() 永远是 None，
    #   出行的 token 和工具调用就全记不上（踩过：模型调了 20 秒，记了 0 次）。
    #
    # 为什么在创建线程之前复制：
    #   copy_context() 复制的是「调用这一刻」的上下文，
    #   必须在 start() 之前拿，之后拿到的已经是空的（主协程可能已经切走）。
    ctx = contextvars.copy_context()

    def worker_streaming():
        """在工作线程里逐条推进生成器。

        为什么要用 ctx.run 包住 next()：
          只有包住才能在复制过来的上下文里执行，
          业务代码里 stats.current() 才拿得到当前请求的记录。
        """
        try:
            while True:
                try:
                    item = ctx.run(lambda: next(worker_generator))
                except StopIteration:
                    break
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as e:
            # 生成器内部抛了异常（真正的业务错误）
            loop.call_soon_threadsafe(queue.put_nowait, ("error", e))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, done)

    threading.Thread(target=worker_streaming, daemon=True).start()

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
