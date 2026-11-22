from langgraph.graph import END, START, StateGraph

from modules.generate_prompts.node import prompt_node
from modules.generate_prompts.state import AgentState


def create():
    graph = StateGraph(AgentState)

    graph.add_node("prompt_node", prompt_node)

    graph.add_edge(START, "prompt_node")
    graph.add_edge("prompt_node", END)

    return graph.compile()
