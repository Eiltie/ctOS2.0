from langgraph.graph import START, StateGraph, END
from ctOS_chat_agent_node import ctOS_chat_node
from ctOS_chat_state import AgentState

import time

def create_graph():
    graph = StateGraph(AgentState)

    graph.add_node("chat_node", ctOS_chat_node)
    graph.add_edge(START, "chat_node")
    graph.add_edge("chat_node", END)

    app = graph.compile()

    return app

if __name__ == "__main__":
    app = create_graph()

    print("构建智能图已完成", end="", flush=True)
    time.sleep(0.5)
    print(".", end="", flush=True)
    time.sleep(0.5)   
    print(".", end="", flush=True)  
    time.sleep(0.5) 
    print(".")  