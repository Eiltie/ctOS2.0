"""会话和消息的增删改查：sessions 存会话，messages 存消息（删会话时级联删）。

每张表都有 tenant_id，所有查询都要带上它做租户隔离。tenant_id 由调用方传进来，
生产路径上由 api 层从登录 token 取出，只有本地调试才会用默认值。

tenants 表不在这个文件里建，见 databases/common/db_tenant.py。
"""

from databases.conn import DEFAULT_TENANT_ID, execute, execute_returning_id, query

# 闲聊模块的表和增删改查

ALLOWED_ROLES = ("user", "assistant")

# 注意：tenants 表不在这里建。它是全局身份表，见 databases/common/db_tenant.py。
# 以前放在这里，导致删掉闲聊模块会连带坏掉认证和出行。

# sessions / messages / message_images 的建表语句在 databases/schema.sql

def create_session(title, tenant_id=DEFAULT_TENANT_ID):
    """新建一个会话，返回它的 id。"""
    return execute_returning_id(
        "INSERT INTO sessions (tenant_id, title) VALUES (%s, %s) RETURNING id",
        (tenant_id, title),
    )


def list_sessions(tenant_id=DEFAULT_TENANT_ID):
    """列出该租户的所有会话，最近更新的排在前面。"""
    return query(
        "SELECT id, title, created_at, updated_at "
        "FROM sessions WHERE tenant_id = %s "
        "ORDER BY updated_at DESC, id DESC",
        (tenant_id,),
    )


def delete_session(session_id, tenant_id=DEFAULT_TENANT_ID):
    """删除会话，它的消息级联删掉，返回删掉的行数。"""
    return execute(
        "DELETE FROM sessions WHERE id = %s AND tenant_id = %s",
        (session_id, tenant_id),
    )


def add_message(session_id, role, content, tenant_id=DEFAULT_TENANT_ID):
    """给会话追加一条消息并刷新会话时间，返回新消息 id。"""
    if role not in ALLOWED_ROLES:
        raise ValueError(f"role 只能是 {ALLOWED_ROLES}，收到的是 {role!r}")

    new_message_id = execute_returning_id(
        "INSERT INTO messages (tenant_id, session_id, role, content) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (tenant_id, session_id, role, content),
    )

    # 刷新排序用的时间戳
    execute(
        "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP "
        "WHERE id = %s AND tenant_id = %s",
        (session_id, tenant_id),
    )

    return new_message_id


def get_recent_messages(session_id, limit=20, tenant_id=DEFAULT_TENANT_ID):
    """取最近 limit 条消息，按时间从早到晚返回。"""
    rows = query(
        "SELECT id, session_id, role, content, created_at "
        "FROM messages WHERE session_id = %s AND tenant_id = %s "
        "ORDER BY id DESC LIMIT %s",
        (session_id, tenant_id, limit),
    )
    return list(reversed(rows))


def get_session_messages(session_id, tenant_id=DEFAULT_TENANT_ID):
    """取会话全部消息，按时间从早到晚返回。"""
    return query(
        "SELECT id, session_id, role, content, created_at "
        "FROM messages WHERE session_id = %s AND tenant_id = %s ORDER BY id ASC",
        (session_id, tenant_id),
    )


def add_message_image(message_id, rel_path, mime, byte_size,
                      session_id=None, tenant_id=DEFAULT_TENANT_ID):
    """给某条消息挂一张图，返回图片记录 id。"""
    return execute_returning_id(
        "INSERT INTO message_images "
        "(tenant_id, session_id, message_id, rel_path, mime, byte_size) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (tenant_id, session_id, message_id, rel_path, mime, byte_size),
    )


def images_of_message(message_id, tenant_id=DEFAULT_TENANT_ID):
    """某条消息挂了哪些图，按挂上去的顺序返回。"""
    return query(
        "SELECT id, rel_path, mime, byte_size "
        "FROM message_images WHERE message_id = %s AND tenant_id = %s "
        "ORDER BY id ASC",
        (message_id, tenant_id),
    )


def images_of_messages(message_ids, tenant_id=DEFAULT_TENANT_ID):
    """一批消息各自挂了哪些图，返回 {message_id: [图片记录 id, ...]}。

    给前端渲染历史消息用，只给 id，前端拿 id 去 /chat/attachment/{id} 取图。
    一次查完，不要每条消息查一次。
    """
    ids = [int(i) for i in (message_ids or [])]
    if not ids:
        return {}

    rows = query(
        "SELECT id, message_id FROM message_images "
        "WHERE message_id = ANY(%s) AND tenant_id = %s ORDER BY id ASC",
        (ids, tenant_id),
    )

    grouped = {}
    for row in rows:
        grouped.setdefault(row["message_id"], []).append(row["id"])
    return grouped


def get_image(image_id, tenant_id=DEFAULT_TENANT_ID):
    """按图片记录 id 取一行；不属于这个租户就返回 None。"""
    rows = query(
        "SELECT id, rel_path, mime, byte_size, message_id FROM message_images "
        "WHERE id = %s AND tenant_id = %s",
        (image_id, tenant_id),
    )
    return rows[0] if rows else None


def claim_image(image_id, message_id, session_id=None, tenant_id=DEFAULT_TENANT_ID):
    """把上传时占位的图片记录认领到某条消息上。

    为什么不是再插一条：
      上传接口先插一行占位（message_id 为空），发消息时如果又插一行新的，
      同一个文件就会有两条记录，旧的那条永远挂着空 message_id 变成孤儿。
      所以这里用 UPDATE 认领原来那条。

    返回是否认领成功（记录不存在或不属于该租户时返回 False）。
    """
    return execute(
        "UPDATE message_images SET message_id = %s, session_id = %s "
        "WHERE id = %s AND tenant_id = %s",
        (message_id, session_id, image_id, tenant_id),
    ) > 0


def delete_message_images(message_id, tenant_id=DEFAULT_TENANT_ID):
    """删某条消息的图片记录，返回被删掉的行（含 rel_path，便于删盘上的文件）。"""
    rows = query(
        "SELECT id, rel_path FROM message_images "
        "WHERE message_id = %s AND tenant_id = %s",
        (message_id, tenant_id),
    )
    if rows:
        execute(
            "DELETE FROM message_images WHERE message_id = %s AND tenant_id = %s",
            (message_id, tenant_id),
        )
    return rows
