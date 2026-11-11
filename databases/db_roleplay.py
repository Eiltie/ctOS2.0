"""角色扮演的表：会话对应哪个角色，以及每个角色的记忆。

两张表：
    role_play_sessions  这个聊天会话是哪个角色
    role_play_memories   这个角色记住了什么（按租户 + 角色存一份）

注意：预设角色不存这里，直接写在 modules/roleplay/presets.py。
"""

from core.db import execute, query, query_one, transaction

CREATE_ROLE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS role_play_sessions (
    session_id  INTEGER     PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role_id     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_ROLE_MEMORIES_TABLE = """
CREATE TABLE IF NOT EXISTS role_play_memories (
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role_id     TEXT        NOT NULL,
    summary     TEXT        NOT NULL DEFAULT '',
    rounds      INTEGER     NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, role_id)
)
"""

CREATE_CUSTOM_ROLES_TABLE = """
CREATE TABLE IF NOT EXISTS role_play_roles (
    id           INTEGER     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name         TEXT        NOT NULL,
    emoji        TEXT        NOT NULL DEFAULT '🙂',
    tagline      TEXT        NOT NULL DEFAULT '',
    personality  TEXT        NOT NULL DEFAULT '',
    speaking     TEXT        NOT NULL DEFAULT '',
    boundaries   TEXT        NOT NULL DEFAULT '',
    opening      TEXT        NOT NULL DEFAULT '',
    source       TEXT        NOT NULL DEFAULT 'custom',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_ROLE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_role_sessions_tenant ON role_play_sessions (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_role_memories_tenant ON role_play_memories (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_role_roles_tenant ON role_play_roles (tenant_id)",
)


def create_roleplay_tables():
    """建角色扮演的表，已存在就跳过。"""
    execute(CREATE_ROLE_SESSIONS_TABLE)
    execute(CREATE_ROLE_MEMORIES_TABLE)
    execute(CREATE_CUSTOM_ROLES_TABLE)
    for sql in CREATE_ROLE_INDEXES:
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


# 自定义角色的 id 统一长这样：custom_12
CUSTOM_ROLE_PREFIX = "custom_"


def custom_row_to_role(row):
    """把数据库里的一行自定义角色，转成和预设角色一样的结构。"""
    return {
        "id": f"{CUSTOM_ROLE_PREFIX}{row['id']}",
        "name": row["name"],
        "group": "我的角色",
        "emoji": row["emoji"],
        "tagline": row["tagline"],
        "personality": row["personality"],
        "speaking": row["speaking"],
        "boundaries": row["boundaries"],
        "opening": row["opening"],
        "source": row["source"],
    }


def create_custom_role(tenant_id, name, emoji, tagline, personality,
                       speaking, boundaries, opening, source="custom"):
    """新建一个自定义角色，返回数据库里的数字 id。"""
    with transaction() as cur:
        cur.execute(
            "INSERT INTO role_play_roles "
            "(tenant_id, name, emoji, tagline, personality, speaking, boundaries, opening, source) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "RETURNING id",
            (tenant_id, name, emoji, tagline, personality,
             speaking, boundaries, opening, source),
        )
        row = cur.fetchone()
        return row["id"]


def list_custom_roles(tenant_id):
    """列出这个租户自己写的角色，老的排前面。"""
    rows = query(
        "SELECT id, name, emoji, tagline, personality, speaking, boundaries, opening, source "
        "FROM role_play_roles WHERE tenant_id = %s ORDER BY id",
        (tenant_id,),
    )
    return [custom_row_to_role(row) for row in rows]


def get_custom_role(tenant_id, role_id):
    """按 custom_12 这样的 id 找自定义角色，找不到返回 None。"""
    if not role_id or not role_id.startswith(CUSTOM_ROLE_PREFIX):
        return None

    try:
        role_number = int(role_id[len(CUSTOM_ROLE_PREFIX):])
    except ValueError:
        return None

    row = query_one(
        "SELECT id, name, emoji, tagline, personality, speaking, boundaries, opening, source "
        "FROM role_play_roles WHERE id = %s AND tenant_id = %s",
        (role_number, tenant_id),
    )
    return custom_row_to_role(row) if row else None


def all_role_session_ids(tenant_id):
    """这个租户下，哪些会话是角色会话。返回 {会话id: 角色id}。"""
    rows = query(
        "SELECT session_id, role_id FROM role_play_sessions WHERE tenant_id = %s",
        (tenant_id,),
    )
    return {row["session_id"]: row["role_id"] for row in rows}


def get_memory(tenant_id, role_id):
    """取这个角色的记忆摘要；没有就返回空字符串。"""
    row = query_one(
        "SELECT summary FROM role_play_memories "
        "WHERE tenant_id = %s AND role_id = %s",
        (tenant_id, role_id),
    )
    return row["summary"] if row else ""


def save_memory(tenant_id, role_id, summary):
    """写入记忆摘要，并把“已经聊了几轮”清零。"""
    execute(
        "INSERT INTO role_play_memories (tenant_id, role_id, summary, rounds) "
        "VALUES (%s, %s, %s, 0) "
        "ON CONFLICT (tenant_id, role_id) DO UPDATE SET "
        "summary = EXCLUDED.summary, rounds = 0, updated_at = CURRENT_TIMESTAMP",
        (tenant_id, role_id, summary),
    )


def clear_memory(tenant_id, role_id):
    """把这个角色的记忆全部删掉。"""
    execute(
        "DELETE FROM role_play_memories WHERE tenant_id = %s AND role_id = %s",
        (tenant_id, role_id),
    )


def add_one_round(tenant_id, role_id, every=6):
    """记一轮对话，返回“是不是该总结了”。

    每聊一轮加一；到 6 轮返回 True，并清零重新数。
    """
    with transaction() as cur:
        cur.execute(
            "SELECT rounds FROM role_play_memories "
            "WHERE tenant_id = %s AND role_id = %s FOR UPDATE",
            (tenant_id, role_id),
        )
        row = cur.fetchone()
        old_rounds = row["rounds"] if row else 0
        new_rounds = old_rounds + 1
        should_summarize = new_rounds >= every
        next_rounds = 0 if should_summarize else new_rounds

        if row:
            cur.execute(
                "UPDATE role_play_memories SET rounds = %s, updated_at = CURRENT_TIMESTAMP "
                "WHERE tenant_id = %s AND role_id = %s",
                (next_rounds, tenant_id, role_id),
            )
        else:
            cur.execute(
                "INSERT INTO role_play_memories (tenant_id, role_id, rounds) "
                "VALUES (%s, %s, %s)",
                (tenant_id, role_id, next_rounds),
            )

        return should_summarize


def get_role_messages(tenant_id, role_id, limit=12):
    """取这个角色最近几条消息，用来做记忆摘要（所有会话合在一起）。"""
    rows = query(
        "SELECT m.role, m.content FROM messages m "
        "JOIN role_play_sessions r ON r.session_id = m.session_id "
        "WHERE m.tenant_id = %s AND r.role_id = %s "
        "ORDER BY m.id DESC LIMIT %s",
        (tenant_id, role_id, limit),
    )
    return list(reversed(rows))
