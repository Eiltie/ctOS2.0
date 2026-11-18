"""闲聊模块的表和增删改查：sessions 存会话，messages 存消息（级联删除）。

PostgreSQL 版本，与 SQLite 版的主要差异：
  - id 用 GENERATED ALWAYS AS IDENTITY（PG 标准写法，比 SERIAL 更规范）
  - 时间用 TIMESTAMPTZ，默认 CURRENT_TIMESTAMP（带时区，不会有时差问题）
  - 占位符用 %s
  - 插入后拿 id 用 RETURNING id
  - 每张表都有 tenant_id，所有查询必须带上它（多租户隔离）

多租户约定：tenant_id 由调用方传进来，默认走 core.db.DEFAULT_TENANT_ID。
生产路径上由 api 层从登录 token 取，不会走默认值。

注意：tenants 表不在本文件创建，见 databases/db_tenant.py。
"""

from core.db import DEFAULT_TENANT_ID, execute, execute_returning_id, query

# 闲聊模块的表和增删改查

ALLOWED_ROLES = ("user", "assistant")

# 注意：tenants 表不在这里建。它是全局身份表，见 databases/db_tenant.py。
# 以前放在这里，导致删掉闲聊模块会连带坏掉认证和出行。

CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id  INTEGER     NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# 图片附件：消息正文只存纯文字，图单独记在这里
# 为什么不塞进 messages.content：
#   历史回放是 HumanMessage(content=正文)。正文里若混着图片块，
#   读出来是 "..." 这种字符串，模型会当成用户在念代码。
#   存纯文字 + 另表记图，回放逻辑一行不用改，老数据也不受影响。
CREATE_MESSAGE_IMAGES_TABLE = """
CREATE TABLE IF NOT EXISTS message_images (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id  INTEGER     REFERENCES sessions(id) ON DELETE CASCADE,
    message_id  INTEGER     REFERENCES messages(id) ON DELETE CASCADE,
    rel_path    TEXT        NOT NULL,
    mime        TEXT        NOT NULL,
    byte_size   INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_sessions_tenant ON sessions (tenant_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_messages_session ON messages (session_id)",
    "CREATE INDEX IF NOT EXISTS ix_messages_tenant ON messages (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_message_images_message ON message_images (message_id)",
    "CREATE INDEX IF NOT EXISTS ix_message_images_tenant ON message_images (tenant_id)",
)


def create_chat_tables():
    """建闲聊的表和索引，已存在就跳过。

    前置条件：tenants 表必须先存在（sessions / messages 都外键引用它）。
    正常由 core.db.create_all_tables() 保证顺序；单独跑本文件时见 __main__。
    """
    execute(CREATE_SESSIONS_TABLE)
    execute(CREATE_MESSAGES_TABLE)
    execute(CREATE_MESSAGE_IMAGES_TABLE)
    for create_index in CREATE_INDEXES:
        execute(create_index)


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


if __name__ == "__main__":
    # 单独跑本文件时手动保证顺序：先建全局身份表
    from databases.db_tenant import create_tenant_tables

    create_tenant_tables()
    create_chat_tables()
    print("闲聊表建好了")
