"""闲聊会话的读写层：在数据库之上包一层，出错不拖垮聊天。

tenant_id 说明：
  以前这里是常量 DEFAULT_TENANT_ID，所有人都共用一份数据。
  现在改成每个函数都要传 tenant_id，由 API 层从登录 token 里取。
  这样每个用户看到的是自己的会话，永远不会跨用户。
"""

from langchain_core.messages import AIMessage, HumanMessage

from common.db import DEFAULT_TENANT_ID
from databases.modules.db_chat import (
    add_message,
    add_message_image,
    claim_image,
    create_session,
    delete_session,
    delete_message_images,
    get_recent_messages,
    get_session_messages,
    images_of_message,
    images_of_messages,
    list_sessions,
)

# 会话列表里显示的标题长度
TITLE_LIMIT = 14

# 喂给模型的多轮上下文条数
HISTORY_LIMIT = 10


def load_history(session_id, tenant_id=DEFAULT_TENANT_ID) -> list:
    """取最近 HISTORY_LIMIT 条消息，转成模型可用的消息列表；读失败返回空列表。"""
    history_messages = []

    if session_id is None:
        return history_messages

    try:
        for message in get_recent_messages(session_id, limit=HISTORY_LIMIT, tenant_id=tenant_id):
            if message["role"] == "user":
                history_messages.append(HumanMessage(content=message["content"]))
            else:
                history_messages.append(AIMessage(content=message["content"]))
    except Exception as e:
        print(f"[数据库] 读取历史失败：{e}")

    return history_messages


def resolve_session(session_id, first_message, tenant_id=DEFAULT_TENANT_ID):
    """本轮用哪个会话：传了就用传的，没传就新建一个；建失败返回 None。"""
    if session_id is not None:
        return session_id

    try:
        return create_session(first_message[:TITLE_LIMIT], tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 新建会话失败：{e}")
        return None


def save_ai_reply(session_id, content, tenant_id=DEFAULT_TENANT_ID):
    """存一条 AI 回复，返回 message_id；失败只打印，不影响已返回的内容。

    为什么返回 id：
      生图场景要把生成的图挂到这条回复上（message_images.message_id），
      没有 id 就挂不上，回放历史时图就丢了。
    """
    if session_id is None or not content:
        return None

    try:
        return add_message(session_id, "assistant", content, tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 写入 AI 回复失败：{e}")
        return None


def save_user_message(session_id, content, tenant_id=DEFAULT_TENANT_ID):
    """存一条用户消息，失败只打印。

    content 必须是**纯文字**：消息表只存文字，图片另存 message_images。
    如果调用方手里是带图的 HumanMessage，先用 text_of() 取文字再传进来。
    """
    # 必须晚于 load_history()：先存会让本轮问题重复进历史
    if session_id is None or not content:
        return None

    try:
        return add_message(session_id, "user", content, tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 写入用户消息失败：{e}")
        return None


def attach_images(message_id, image_records, session_id=None, tenant_id=DEFAULT_TENANT_ID):
    """把本轮用到的图片认领到某条消息上。

    image_records: [(image_id, rel_path, mime, byte_size), ...]
    这些记录是上传接口先插好的占位（message_id 为空），这里 UPDATE 认领，
    不再插新行——否则同一个文件会有两条记录，旧的那条变成孤儿。

    失败只打印——图挂不上不该让整轮对话失败。
    """
    if message_id is None or not image_records:
        return

    for image_id, rel_path, mime, byte_size in image_records:
        if not image_id:
            continue
        try:
            claim_image(
                image_id, message_id,
                session_id=session_id, tenant_id=tenant_id,
            )
        except Exception as e:
            print(f"[数据库] 认领图片失败（不影响本轮回复）：{e}")


def text_of(message) -> str:
    """从消息里取出纯文字部分。

    为什么需要：
      加识图之后，HumanMessage 的 content 可能是块数组而不是字符串
      （见 build_user_message）。项目里所有「把消息当文字用」的地方
      都必须过一遍这个函数，否则会 TypeError。
      content 是字符串时原样返回——老路径行为完全不变。
    """
    content = getattr(message, "content", message)

    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")

    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def build_user_message(text, image_paths=None, tenant_id=DEFAULT_TENANT_ID):
    """文字 + 图片 → 一条能直接喂模型的 HumanMessage。

    这是「让模型识图」的全部形式：content 从 str 换成块数组。
      没有图  → HumanMessage(content="纯文字")，和加识图之前一模一样
      有图    → HumanMessage(content=[文本块, 图片块, ...])

    image_paths 是 attachments 表里的 rel_path 列表，不是内存里的字节。
    tenant_id 只用于日志，图片归属在查表时已经校验过了。
    """
    text = (text or "").strip()

    # 没有图就完全走老路：返回的东西和以前一致，不引入任何差异
    if not image_paths:
        return HumanMessage(content=text)

    from modules.chat.attachments import blocks_of

    image_blocks = blocks_of(list(image_paths))

    # 一张图都没读出来时退回纯文字，避免发出一个只有文本的空壳
    if not image_blocks:
        return HumanMessage(content=text)

    blocks = []
    if text:
        blocks.append({"type": "text", "text": text})
    blocks.extend(image_blocks)

    return HumanMessage(content=blocks)


def all_sessions(tenant_id=DEFAULT_TENANT_ID) -> list:
    """列出该租户的所有会话，读取失败返回空列表。"""
    try:
        return list_sessions(tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 读取会话列表失败：{e}")
        return []


def session_messages(session_id, tenant_id=DEFAULT_TENANT_ID) -> list:
    """取会话全部消息，只保留前端要的 role / content / images。

    images 这一项是加识图后才有的：每条消息带上它挂的图片 id，
    前端可以按 id 去 /chat/attachment/{id} 取图。
    老数据没有图，这一项就是空列表，前端不渲染即可。
    """
    # 时间戳之类的字段没法直接转 JSON
    if session_id is None:
        return []

    try:
        found_rows = get_session_messages(session_id, tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 读取会话消息失败：{e}")
        return []

    # 一次把所有图查出来分组，不要每条消息查一次
    try:
        grouped = images_of_messages([row["id"] for row in found_rows], tenant_id=tenant_id)
    except Exception as e:
        print(f"[数据库] 读取消息图片失败：{e}")
        grouped = {}

    result = []
    for row in found_rows:
        result.append({
            "role": row["role"],
            "content": row["content"],
            "images": grouped.get(row["id"], []),
        })
    return result


def remove_session(session_id, tenant_id=DEFAULT_TENANT_ID) -> bool:
    """删除会话及其消息，返回是否真的删掉了。"""
    if session_id is None:
        return False

    try:
        return delete_session(session_id, tenant_id=tenant_id) > 0
    except Exception as e:
        print(f"[数据库] 删除会话失败：{e}")
        return False
