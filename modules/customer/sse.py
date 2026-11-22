"""客服的 SSE 事件打包。

客服的检索和生成是同步的（jieba、Chroma、模型调用都会卡住事件循环），
所以 stream.py 会把它们放进工作线程，这里只负责把事件打包成 SSE。

注意：出行模块有一份自己的 sse.py，两边内容相同但各自独立。
     改事件格式时要两边一起改。
"""

import json


def sse(event: dict) -> str:
    """把事件打包成一条 SSE 消息（末尾空行即结束）。"""
    # ensure_ascii=False：中文原样输出，不要转成 \u4f60 这种
    return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
