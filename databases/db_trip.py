"""出行模块的表和增删改查。

表结构：trip_chats 存会话，下面挂 trip_sessions（每一轮）、
        trip_user_inputs（用户原话）、trip_ai_outputs（AI 四段产出）。

PostgreSQL 版本，与 SQLite 版的差异同 db_chat.py：
  - IDENTITY 主键、TIMESTAMPTZ 时间、%s 占位符、RETURNING id
  - 所有表带 tenant_id，所有查询带上它
"""

from core.db import (
    DEFAULT_TENANT_ID,
    execute,
    execute_returning_id,
    query,
    query_one,
    transaction,
)

ALLOWED_TURN_KINDS = ("TRAVEL", "CHAT")

CREATE_TRIP_CHATS_TABLE = """
CREATE TABLE IF NOT EXISTS trip_chats (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_TRIP_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS trip_sessions (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    chat_id     INTEGER     REFERENCES trip_chats(id) ON DELETE CASCADE,
    title       TEXT        NOT NULL,
    turn_kind   TEXT        NOT NULL DEFAULT 'TRAVEL',
    destination TEXT        NOT NULL DEFAULT '',
    days        INTEGER     NOT NULL DEFAULT 0,
    start_date  TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_TRIP_USER_INPUTS_TABLE = """
CREATE TABLE IF NOT EXISTS trip_user_inputs (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    trip_id     INTEGER     NOT NULL REFERENCES trip_sessions(id) ON DELETE CASCADE,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_TRIP_AI_OUTPUTS_TABLE = """
CREATE TABLE IF NOT EXISTS trip_ai_outputs (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    trip_id     INTEGER     NOT NULL REFERENCES trip_sessions(id) ON DELETE CASCADE,
    weather     TEXT        NOT NULL DEFAULT '',
    spots       TEXT        NOT NULL DEFAULT '',
    itinerary   TEXT        NOT NULL DEFAULT '',
    route_plan  TEXT        NOT NULL DEFAULT '',
    chat_reply  TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_TRIP_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_trip_chats_tenant ON trip_chats (tenant_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_trip_sessions_chat ON trip_sessions (chat_id)",
    "CREATE INDEX IF NOT EXISTS ix_trip_user_inputs_trip ON trip_user_inputs (trip_id)",
    "CREATE INDEX IF NOT EXISTS ix_trip_ai_outputs_trip ON trip_ai_outputs (trip_id)",
)


def create_trip_tables():
    """建出行的四张表和索引，已存在就跳过。"""
    execute(CREATE_TRIP_CHATS_TABLE)
    execute(CREATE_TRIP_SESSIONS_TABLE)
    execute(CREATE_TRIP_USER_INPUTS_TABLE)
    execute(CREATE_TRIP_AI_OUTPUTS_TABLE)
    for create_index in CREATE_TRIP_INDEXES:
        execute(create_index)


def _ensure_chat(cur, chat_id, title, tenant_id):
    """确保 chat_id 存在且属于本租户；不存在就新建，返回可用的 chat_id。"""
    if chat_id is not None:
        cur.execute(
            "SELECT 1 FROM trip_chats WHERE id = %s AND tenant_id = %s",
            (chat_id, tenant_id),
        )
        if cur.fetchone():
            return chat_id

    # 没有，或者传的 id 不属于本租户：新建一个
    cur.execute(
        "INSERT INTO trip_chats (tenant_id, title) VALUES (%s, %s) RETURNING id",
        (tenant_id, title),
    )
    return cur.fetchone()["id"]


def save_trip_turn(user_query, ai_output, turn_kind="TRAVEL", chat_id=None,
                   tenant_id=DEFAULT_TENANT_ID):
    """把一轮出行对话整体存进会话，返回所属会话 id。"""
    if turn_kind not in ALLOWED_TURN_KINDS:
        raise ValueError(f"turn_kind 只能是 {ALLOWED_TURN_KINDS}，收到的是 {turn_kind!r}")

    ai_output = ai_output or {}

    destination = (ai_output.get("destination") or "").strip()
    title = (destination or user_query or "")[:14]

    # 一次事务：中途报错整体回滚，不会留下没有子表数据的轮次
    with transaction() as cur:
        chat_id = _ensure_chat(cur, chat_id, title, tenant_id)

        cur.execute(
            "INSERT INTO trip_sessions "
            "(tenant_id, chat_id, title, turn_kind, destination, days, start_date) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, chat_id, title, turn_kind, destination,
             int(ai_output.get("days") or 0), ai_output.get("start_date") or ""),
        )
        trip_id = cur.fetchone()["id"]

        # 两张子表都靠这个 trip_id 挂到本轮
        cur.execute(
            "INSERT INTO trip_user_inputs (tenant_id, trip_id, content) VALUES (%s, %s, %s)",
            (tenant_id, trip_id, user_query or ""),
        )

        cur.execute(
            "INSERT INTO trip_ai_outputs "
            "(tenant_id, trip_id, weather, spots, itinerary, route_plan, chat_reply) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (tenant_id, trip_id,
             ai_output.get("weather") or "",
             ai_output.get("spots") or "",
             ai_output.get("itinerary") or "",
             ai_output.get("route_plan") or "",
             ai_output.get("chat_reply") or ""),
        )

        # 刷新排序用的时间戳，标题保持第一次的
        cur.execute(
            "UPDATE trip_chats SET updated_at = CURRENT_TIMESTAMP "
            "WHERE id = %s AND tenant_id = %s",
            (chat_id, tenant_id),
        )

    return chat_id


def list_trips(limit=50, tenant_id=DEFAULT_TENANT_ID):
    """列出最近的出行会话（一个会话一行），新的在前面。"""
    return query(
        "SELECT c.id, c.title, c.created_at, c.updated_at, "
        "       (SELECT COUNT(*) FROM trip_sessions t "
        "         WHERE t.chat_id = c.id AND t.tenant_id = c.tenant_id) AS turn_count, "
        "       COALESCE((SELECT t.turn_kind FROM trip_sessions t "
        "                  WHERE t.chat_id = c.id AND t.tenant_id = c.tenant_id "
        "                  ORDER BY t.id DESC LIMIT 1), '') AS last_kind "
        "FROM trip_chats c "
        "WHERE c.tenant_id = %s "
        "ORDER BY c.updated_at DESC, c.id DESC LIMIT %s",
        (tenant_id, limit),
    )


def get_trip(chat_id, tenant_id=DEFAULT_TENANT_ID):
    """取一个会话的完整对话，按时间顺序给出每一轮；不存在返回 None。"""
    chat_row = query_one(
        "SELECT id, title, created_at, updated_at FROM trip_chats "
        "WHERE id = %s AND tenant_id = %s",
        (chat_id, tenant_id),
    )
    if not chat_row:
        return None

    turn_rows = query(
        "SELECT * FROM trip_sessions WHERE chat_id = %s AND tenant_id = %s ORDER BY id",
        (chat_id, tenant_id),
    )

    turns = []
    for row in turn_rows:
        trip_id = row["id"]
        user_row = query_one(
            "SELECT content FROM trip_user_inputs "
            "WHERE trip_id = %s AND tenant_id = %s ORDER BY id LIMIT 1",
            (trip_id, tenant_id),
        )
        ai_row = query_one(
            "SELECT * FROM trip_ai_outputs "
            "WHERE trip_id = %s AND tenant_id = %s ORDER BY id LIMIT 1",
            (trip_id, tenant_id),
        )

        turn = dict(row)
        turn["user_query"] = user_row["content"] if user_row else ""
        turn["ai_output"] = dict(ai_row) if ai_row else {}
        turns.append(turn)

    result = dict(chat_row)
    result["turns"] = turns
    return result


def delete_trip(chat_id, tenant_id=DEFAULT_TENANT_ID):
    """删除会话及其全部轮次，返回删掉的会话行数。

    子表现在有 ON DELETE CASCADE，删 trip_chats 会自动清掉下游，
    但这里仍然显式按顺序删，方便以后去掉外键也不会留孤儿。
    """
    with transaction() as cur:
        cur.execute(
            "DELETE FROM trip_user_inputs WHERE trip_id IN "
            "(SELECT id FROM trip_sessions WHERE chat_id = %s AND tenant_id = %s)",
            (chat_id, tenant_id),
        )
        cur.execute(
            "DELETE FROM trip_ai_outputs WHERE trip_id IN "
            "(SELECT id FROM trip_sessions WHERE chat_id = %s AND tenant_id = %s)",
            (chat_id, tenant_id),
        )
        cur.execute(
            "DELETE FROM trip_sessions WHERE chat_id = %s AND tenant_id = %s",
            (chat_id, tenant_id),
        )
        cur.execute(
            "DELETE FROM trip_chats WHERE id = %s AND tenant_id = %s",
            (chat_id, tenant_id),
        )
        return cur.rowcount


def delete_trips(chat_ids, tenant_id=DEFAULT_TENANT_ID):
    """批量删除多个会话，返回真正删掉的个数。

    一个会话删失败不影响其他会话，逐个删，最后只报成功数量。
    """
    deleted = 0
    for chat_id in chat_ids:
        try:
            if delete_trip(chat_id, tenant_id) > 0:
                deleted += 1
        except Exception as e:
            print(f"[数据库] 删除出行会话 {chat_id} 失败：{e}")

    return deleted


if __name__ == "__main__":
    create_trip_tables()
    print("出行表建好了")
