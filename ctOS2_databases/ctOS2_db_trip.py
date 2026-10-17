"""智能出行模块的表和增删改查。

三张表的关系：
    trip_sessions      一轮出行对话的完整记录，主键 id
    trip_user_inputs   用户这轮说的话，外键 trip_id 指向 trip_sessions.id
    trip_ai_outputs    AI 这轮的产出，外键 trip_id 指向 trip_sessions.id

    删掉一条 trip_sessions，它的用户输入和 AI 输出会跟着一起删（级联）。

一次「存库」= 主表插一行 + 子表各插一行，在同一个事务里，
要么全成、要么全不成，不会出现「有主表没子表」的半截数据。

连接和数据库路径统一在 ctOS2_db.py 里，本文件只用不重写。
"""

from ctOS2_databases.ctOS2_db import open_database

# 这一轮是「真跑了出行图」还是「被判为闲聊、直接回了一句」
ALLOWED_TURN_KINDS = ("TRAVEL", "CHAT")


# ---------------------------------------------------------------- 建表
CREATE_TRIP_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS `trip_sessions` (
    `id`          INTEGER PRIMARY KEY AUTOINCREMENT,
    `title`       TEXT NOT NULL,
    `turn_kind`   TEXT NOT NULL DEFAULT 'TRAVEL',
    `destination` TEXT NOT NULL DEFAULT '',
    `days`        INTEGER NOT NULL DEFAULT 0,
    `start_date`  TEXT NOT NULL DEFAULT '',
    `created_at`  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
)
"""

CREATE_TRIP_USER_INPUTS_TABLE = """
CREATE TABLE IF NOT EXISTS `trip_user_inputs` (
    `id`         INTEGER PRIMARY KEY AUTOINCREMENT,
    `trip_id`    INTEGER NOT NULL,
    `content`    TEXT NOT NULL,
    `created_at` TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (`trip_id`) REFERENCES `trip_sessions` (`id`) ON DELETE CASCADE
)
"""

CREATE_TRIP_AI_OUTPUTS_TABLE = """
CREATE TABLE IF NOT EXISTS `trip_ai_outputs` (
    `id`         INTEGER PRIMARY KEY AUTOINCREMENT,
    `trip_id`    INTEGER NOT NULL,
    `weather`    TEXT NOT NULL DEFAULT '',
    `spots`      TEXT NOT NULL DEFAULT '',
    `itinerary`  TEXT NOT NULL DEFAULT '',
    `route_plan` TEXT NOT NULL DEFAULT '',
    `chat_reply` TEXT NOT NULL DEFAULT '',
    `created_at` TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (`trip_id`) REFERENCES `trip_sessions` (`id`) ON DELETE CASCADE
)
"""

CREATE_TRIP_INDEXES = (
    "CREATE INDEX IF NOT EXISTS `ix_trip_user_inputs_trip_id` "
    "ON `trip_user_inputs` (`trip_id`)",
    "CREATE INDEX IF NOT EXISTS `ix_trip_ai_outputs_trip_id` "
    "ON `trip_ai_outputs` (`trip_id`)",
)


def create_trip_tables():
    """建出行的三张表，已存在就跳过。"""
    database = open_database()
    try:
        with database:
            database.execute(CREATE_TRIP_SESSIONS_TABLE)
            database.execute(CREATE_TRIP_USER_INPUTS_TABLE)
            database.execute(CREATE_TRIP_AI_OUTPUTS_TABLE)
            for create_index in CREATE_TRIP_INDEXES:
                database.execute(create_index)
    finally:
        database.close()


# ---------------------------------------------------------------- 存
def save_trip_turn(user_query, ai_output, turn_kind="TRAVEL"):
    """把一轮出行对话完整存下来，返回新记录的 trip_id。

    参数:
        user_query: 用户这轮说的话
        ai_output:  AI 这轮的产出，字典，可含 destination / days / start_date /
                    weather / spots / itinerary / route_plan / chat_reply
        turn_kind:  "TRAVEL"（跑了图）或 "CHAT"（闲聊分流）
    """
    if turn_kind not in ALLOWED_TURN_KINDS:
        raise ValueError(f"turn_kind 只能是 {ALLOWED_TURN_KINDS}，收到的是 {turn_kind!r}")

    ai_output = ai_output or {}

    # 标题：优先用目的地，没有就取用户问的第一句
    destination = (ai_output.get("destination") or "").strip()
    title = (destination or user_query or "")[:14]

    database = open_database()
    try:
        # with database 是一个事务：中途报错自动回滚，不会留半截数据
        with database:
            insert_result = database.execute(
                "INSERT INTO `trip_sessions` "
                "(`title`, `turn_kind`, `destination`, `days`, `start_date`) "
                "VALUES (?, ?, ?, ?, ?)",
                (title,
                 turn_kind,
                 destination,
                 int(ai_output.get("days") or 0),
                 ai_output.get("start_date") or ""))
            trip_id = insert_result.lastrowid      # 主键，下面两个子表都用它

            database.execute(
                "INSERT INTO `trip_user_inputs` (`trip_id`, `content`) VALUES (?, ?)",
                (trip_id, user_query or ""))

            database.execute(
                "INSERT INTO `trip_ai_outputs` "
                "(`trip_id`, `weather`, `spots`, `itinerary`, `route_plan`, `chat_reply`) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (trip_id,
                 ai_output.get("weather") or "",
                 ai_output.get("spots") or "",
                 ai_output.get("itinerary") or "",
                 ai_output.get("route_plan") or "",
                 ai_output.get("chat_reply") or ""))

            return trip_id
    finally:
        database.close()


# ---------------------------------------------------------------- 读
def list_trips(limit=50):
    """列出最近的若干轮记录，新的排在前面。"""
    database = open_database()
    try:
        found_rows = database.execute(
            "SELECT `id`, `title`, `turn_kind`, `destination`, `days`, "
            "       `start_date`, `created_at` "
            "FROM `trip_sessions` ORDER BY `id` DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in found_rows]
    finally:
        database.close()


def get_trip(trip_id):
    """取一轮完整记录，把主表 + 两张子表拼成一个字典；不存在返回 None。"""
    database = open_database()
    try:
        main_row = database.execute(
            "SELECT * FROM `trip_sessions` WHERE `id` = ?", (trip_id,)
        ).fetchone()
        if not main_row:
            return None

        user_row = database.execute(
            "SELECT `content` FROM `trip_user_inputs` "
            "WHERE `trip_id` = ? ORDER BY `id` LIMIT 1", (trip_id,)
        ).fetchone()

        ai_row = database.execute(
            "SELECT * FROM `trip_ai_outputs` "
            "WHERE `trip_id` = ? ORDER BY `id` LIMIT 1", (trip_id,)
        ).fetchone()

        result = dict(main_row)
        result["user_query"] = user_row["content"] if user_row else ""
        result["ai_output"] = dict(ai_row) if ai_row else {}
        return result
    finally:
        database.close()


# ---------------------------------------------------------------- 删
def delete_trip(trip_id):
    """删除一轮记录，它的用户输入和 AI 输出会一起删掉。返回删掉的行数。"""
    database = open_database()
    try:
        with database:
            delete_result = database.execute(
                "DELETE FROM `trip_sessions` WHERE `id` = ?", (trip_id,))
            return delete_result.rowcount
    finally:
        database.close()
