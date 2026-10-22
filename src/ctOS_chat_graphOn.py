from ctOS_chat_graph import create_graph

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
