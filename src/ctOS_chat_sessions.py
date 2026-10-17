"""会话读写。

数据库层在 ctOS2_databases/ 下（连接层 ctOS2_db.py，闲聊表 ctOS2_db_chat.py），
本文件只负责：
    · 把数据库的错误兜住，不让它拖垮聊天
    · 把数据库的行转成前端/模型要的格式

对外函数名和签名保持不变，所以 src/ctOS_chat_api.py 不需要改。
"""

import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

# 让 ctOS2_databases 这个包能被 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ctOS2_databases.ctOS2_db_chat import (
    add_message,
    create_session,
    delete_session,
    get_recent_messages,
    get_session_messages,
    list_sessions,
)

# 会话标题取用户第一句话的前多少个字
TITLE_LIMIT = 14

# 给模型回看的历史条数上限
HISTORY_LIMIT = 10


def load_history(session_id) -> list:
    """取某个会话的历史消息，给模型当多轮上下文。读失败时返回空列表。"""
    history_messages = []

    if session_id is None:
        return history_messages

    try:
        for message in get_recent_messages(session_id, limit=HISTORY_LIMIT):
            if message["role"] == "user":
                history_messages.append(HumanMessage(content=message["content"]))
            else:
                history_messages.append(AIMessage(content=message["content"]))
    except Exception as e:
        print(f"[数据库] 读取历史失败：{e}")

    return history_messages


def resolve_session(session_id, first_message):
    """确定本轮用哪个会话 id。传了就用传的，没传就新建一个。"""
    if session_id is not None:
        return session_id

    try:
        return create_session(first_message[:TITLE_LIMIT])
    except Exception as e:
        print(f"[数据库] 新建会话失败：{e}")
        return None


def save_ai_reply(session_id, content):
    """把 AI 的回复存进会话。存失败只打印，不影响已经返回给用户的内容。"""
    if session_id is None or not content:
        return

    try:
        add_message(session_id, "assistant", content)
    except Exception as e:
        print(f"[数据库] 写入 AI 回复失败：{e}")


def save_user_message(session_id, content):
    """把用户说的话存进会话。

    注意：必须在 load_history() 之后调用。
    若先存后读，本轮这句话会出现在历史里，再拼一次就重复了。
    """
    if session_id is None or not content:
        return

    try:
        add_message(session_id, "user", content)
    except Exception as e:
        print(f"[数据库] 写入用户消息失败：{e}")


def all_sessions() -> list:
    """列出所有会话，最近活跃的排在前面。出错时返回空列表。"""
    try:
        return list_sessions()
    except Exception as e:
        print(f"[数据库] 读取会话列表失败：{e}")
        return []


def session_messages(session_id) -> list:
    """取某个会话的全部消息（给前端画历史用）。

    只返回前端需要的字段，datetime 之类的没法直接转 JSON。
    """
    if session_id is None:
        return []

    try:
        found_rows = get_session_messages(session_id)
    except Exception as e:
        print(f"[数据库] 读取会话消息失败：{e}")
        return []

    # 只挑前端要的两个字段，时间戳之类的没法直接转 JSON
    return [{"role": row["role"], "content": row["content"]} for row in found_rows]


def remove_session(session_id) -> bool:
    """删除一个会话（它的消息会被外键级联一起删掉）。

    返回 True 表示确实删掉了一条，False 表示不存在或出错。
    """
    if session_id is None:
        return False

    try:
        return delete_session(session_id) > 0
    except Exception as e:
        print(f"[数据库] 删除会话失败：{e}")
        return False
