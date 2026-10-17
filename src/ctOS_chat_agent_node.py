from ctOS_chat_state import AgentState
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from ctOS_chat_promtps import ctOS_chat_promtps
from ctOS_chat_llm import get_llm

def ctOS_chat_node(state: AgentState):
    promtp = ctOS_chat_promtps

    full_content = [SystemMessage(content=promtp)] + state['messages']

    chat_AI = get_llm()

    response = chat_AI.invoke(full_content)

    return {"messages": [response]}