from ctOS_chat_graph import create_graph

graph = create_graph()

async def run_graph(query):
    async for chunk in graph.astream(
        {"messages": query},
        stream_mode="messages",
    ):
        msg, meta = chunk
        if msg.content:
            yield msg.content
