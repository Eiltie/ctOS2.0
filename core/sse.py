"""SSE 事件的统一打包：三个模块都用这一份。

原来出行和客服各写了一份一模一样的 sse()，改动时容易只改一边。
"""

import json


def sse(event: dict) -> str:
    """把事件打包成一条 SSE 消息（末尾空行即结束）。"""
    # ensure_ascii=False：中文原样输出，不要转成 \u4f60 这种
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
