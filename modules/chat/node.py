"""闲聊｜唯一的图节点

做什么：把系统提示词拼在历史前面，调一次模型，返回回复。
被谁用：modules/chat/graph.py 注册为 chat_node。
"""

from modules.chat.state import AgentState
from langchain_core.messages import SystemMessage
from modules.chat.prompts import ctOS_chat_prompts
from core.llm import get_llm

# 对话图里唯一的节点：拼系统提示词后调一次模型，返回回复

# 闲聊的随机性，和其他模块不同：闲聊要活泼一点
TEMPERATURE = 0.7


def ctOS_chat_node(state: AgentState):
    """对话图节点：拼上系统提示词，调一次模型，返回回复消息。"""
    promtp = ctOS_chat_prompts
    full_content = [SystemMessage(content=promtp)] + state["messages"]

    chat_AI = get_llm(temperature=TEMPERATURE)
    response = chat_AI.invoke(full_content)

    return {"messages": [response]}
