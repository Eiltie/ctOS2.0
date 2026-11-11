"""角色扮演的表：记录“这个会话用的是哪个角色”。

为什么单独一张表：
    角色扮演的聊天还是用原来的 sessions / messages 存，
    只在旁边记一句“这个会话是哪个角色”，普通闲聊不受影响。

注意：预设角色不存这里，直接写在 modules/roleplay/presets.py。
"""

from core.db import execute, query_one

CREATE_ROLE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS role_play_sessions (
    session_id  INTEGER     PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role_id     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_ROLE_SESSIONS_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_role_sessions_tenant ON role_play_sessions (tenant_id)",
)


def create_roleplay_tables():
    """建角色扮演的表，已存在就跳过。"""
    execute(CREATE_ROLE_SESSIONS_TABLE)
    for sql in CREATE_ROLE_SESSIONS_INDEX:
        execute(sql)


def link_role_session(session_id, tenant_id, role_id):
    """把一个聊天会话和角色绑在一起；重复绑定时覆盖成新的角色。"""
    execute(
        "INSERT INTO role_play_sessions (session_id, tenant_id, role_id) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (session_id) DO UPDATE SET role_id = EXCLUDED.role_id",
        (session_id, tenant_id, role_id),
    )


def get_role_id(session_id, tenant_id):
    """查这个会话是哪个角色；普通聊天返回 None。"""
    row = query_one(
        "SELECT role_id FROM role_play_sessions "
        "WHERE session_id = %s AND tenant_id = %s",
        (session_id, tenant_id),
    )
    return row["role_id"] if row else None


def is_my_session(session_id, tenant_id):
    """确认这个会话属于当前租户，防止拿别人的会话 id 来用。"""
    row = query_one(
        "SELECT id FROM sessions WHERE id = %s AND tenant_id = %s",
        (session_id, tenant_id),
    )
    return row is not None
