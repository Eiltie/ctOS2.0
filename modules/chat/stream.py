"""闲聊｜模块对外唯一出口

做什么：把图包成异步生成器 run_graph()，逐块吐纯文本。
被谁用：api/main.py 的 POST /chat。
注意：本模块吐的是纯文本，不是 SSE；事件格式不在这里定。
"""

from modules.chat.graph import create_graph

# 对话图的对外出口：ctOS_chat_api 只 import 这里的 run_graph
graph = create_graph()


async def run_graph(query):
    """按消息流式跑对话图，逐块产出文本，对外唯一入口。"""
    async for chunk in graph.astream(
        {"messages": query},
        stream_mode="messages",
    ):
        msg, meta = chunk
        if msg.content:
            yield msg.content
