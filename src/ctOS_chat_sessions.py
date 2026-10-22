import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ctOS2_databases.ctOS2_db_chat import (
    add_message,
    create_session,
    delete_session,
    get_recent_messages,
    get_session_messages,
    list_sessions,
)

# 闲聊会话的读写层：在数据库之上包一层，出错不拖垮聊天
# 会话列表里显示的标题长度
TITLE_LIMIT = 14

# 喂给模型的多轮上下文条数
HISTORY_LIMIT = 10


def load_history(session_id) -> list:
    """取最近 HISTORY_LIMIT 条消息，转成模型可用的消息列表；读失败返回空列表。"""
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
    """本轮用哪个会话：传了就用传的，没传就新建一个；建失败返回 None。"""
    if session_id is not None:
        return session_id

    try:
        return create_session(first_message[:TITLE_LIMIT])
    except Exception as e:
        print(f"[数据库] 新建会话失败：{e}")
        return None


def save_ai_reply(session_id, content):
    """存一条 AI 回复，失败只打印，不影响已返回的内容。"""
    if session_id is None or not content:
        return

    try:
        add_message(session_id, "assistant", content)
    except Exception as e:
        print(f"[数据库] 写入 AI 回复失败：{e}")


def save_user_message(session_id, content):
    """存一条用户消息，失败只打印。"""
    # 必须晚于 load_history()：先存会让本轮问题重复进历史
    if session_id is None or not content:
        return

    try:
        add_message(session_id, "user", content)
    except Exception as e:
        print(f"[数据库] 写入用户消息失败：{e}")


def all_sessions() -> list:
    """列出所有会话，读取失败返回空列表。"""
    try:
        return list_sessions()
    except Exception as e:
        print(f"[数据库] 读取会话列表失败：{e}")
        return []


def session_messages(session_id) -> list:
    """取会话全部消息，只保留前端要的 role / content。"""
    # 时间戳之类的字段没法直接转 JSON
    if session_id is None:
        return []

    try:
        found_rows = get_session_messages(session_id)
    except Exception as e:
        print(f"[数据库] 读取会话消息失败：{e}")
        return []

    return [{"role": row["role"], "content": row["content"]} for row in found_rows]


def remove_session(session_id) -> bool:
    """删除会话及其消息，返回是否真的删掉了。"""
    if session_id is None:
        return False

    try:
        return delete_session(session_id) > 0
    except Exception as e:
        print(f"[数据库] 删除会话失败：{e}")
        return False
