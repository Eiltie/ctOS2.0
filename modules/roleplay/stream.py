"""角色扮演的对话出口：把角色提示词、历史消息和这句话交给模型，逐块吐出来。"""

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm import get_llm
from modules.roleplay.prompts import build_role_prompt

# 角色扮演要活泼一点，和闲聊一样
ROLE_TEMPERATURE = 0.8


async def role_play_stream(role, history, query):
    """流式产出角色的回复。

    history 是 LangChain 的消息列表，query 是用户刚说的一句话。
    """
    messages = [SystemMessage(content=build_role_prompt(role))]
    messages.extend(history)
    messages.append(HumanMessage(content=query))

    llm = get_llm(temperature=ROLE_TEMPERATURE)

    async for chunk in llm.astream(messages):
        if chunk.content:
            yield chunk.content
