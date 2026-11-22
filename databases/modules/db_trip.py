"""出行模块的表和增删改查。

表结构：trip_chats 存会话，下面挂 trip_sessions（每一轮）、
        trip_user_inputs（用户原话）、trip_ai_outputs（AI 四段产出）。

PostgreSQL 版本，与 SQLite 版的差异同 db_chat.py：
  - IDENTITY 主键、TIMESTAMPTZ 时间、%s 占位符、RETURNING id
  - 所有表带 tenant_id，所有查询带上它
"""

from databases.conn import (
    DEFAULT_TENANT_ID,
    execute,
    execute_returning_id,
    query,
    query_one,
    transaction,
)

ALLOWED_TURN_KINDS = ("TRAVEL", "CHAT", "ROUTE")

# trip_* 四张表的建表语句在 databases/schema.sql


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
    title = (ai_output.get("title") or destination or user_query or "")[:14]

    # 一轮对话要写进 trip_ai_outputs 的列。
    # 列全部由 databases/schema.sql 建好，这里直接写，不用再判断列在不在。
    columns = {
        "weather": ai_output.get("weather") or "",
        "spots": ai_output.get("spots") or "",
        "itinerary": ai_output.get("itinerary") or "",
        "advice": ai_output.get("advice") or "",
        "route_plan": ai_output.get("route_plan") or "",
        "route_need": ai_output.get("route_need") or "",
        "route_compare": ai_output.get("route_compare") or "",
        "route_decision": ai_output.get("route_decision") or "",
        "route_tips": ai_output.get("route_tips") or "",
        "chat_reply": ai_output.get("chat_reply") or "",
    }

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

        # 列名来自上面写死的字典，不是外部输入，拼进 SQL 是安全的
        names = list(columns)
        placeholders = ", ".join(["%s"] * (len(names) + 2))
        cur.execute(
            f"INSERT INTO trip_ai_outputs (tenant_id, trip_id, {', '.join(names)}) "
            f"VALUES ({placeholders})",
            (tenant_id, trip_id, *columns.values()),
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
