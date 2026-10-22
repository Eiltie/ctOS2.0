from ctOS_chat_state import AgentState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from ctOS_chat_promtps import ctOS_chat_promtps
from ctOS_chat_llm import get_llm

# 对话图里唯一的节点：拼系统提示词后调一次模型，返回回复


def ctOS_chat_node(state: AgentState):
    """对话图节点：拼上系统提示词，调一次模型，返回回复消息。"""
    promtp = ctOS_chat_promtps
    full_content = [SystemMessage(content=promtp)] + state["messages"]

    chat_AI = get_llm()
    response = chat_AI.invoke(full_content)

    return {"messages": [response]}
