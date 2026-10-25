from ctOS2_databases.ctOS2_db import open_database

# 出行模块的表和增删改查：trip_chats 存会话，下面挂轮次、用户输入、AI 产出

ALLOWED_TURN_KINDS = ("TRAVEL", "CHAT")

CREATE_TRIP_CHATS_TABLE = """
CREATE TABLE IF NOT EXISTS `trip_chats` (
    `id`         INTEGER PRIMARY KEY AUTOINCREMENT,
    `title`      TEXT NOT NULL,
    `created_at` TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    `updated_at` TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
)
"""

CREATE_TRIP_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS `trip_sessions` (
    `id`          INTEGER PRIMARY KEY AUTOINCREMENT,
    `chat_id`     INTEGER,
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
    "CREATE INDEX IF NOT EXISTS `ix_trip_sessions_chat_id` "
    "ON `trip_sessions` (`chat_id`)",
)


def create_trip_tables():
    """建出行的四张表和索引；旧库自动补 chat_id 列并回填会话。"""
    database = open_database()
    try:
        with database:
            database.execute(CREATE_TRIP_CHATS_TABLE)
            database.execute(CREATE_TRIP_SESSIONS_TABLE)

            columns = {row["name"] for row in database.execute("PRAGMA table_info(`trip_sessions`)")}
            if "chat_id" not in columns:
                database.execute("ALTER TABLE `trip_sessions` ADD COLUMN `chat_id` INTEGER")

            database.execute(CREATE_TRIP_USER_INPUTS_TABLE)
            database.execute(CREATE_TRIP_AI_OUTPUTS_TABLE)
            for create_index in CREATE_TRIP_INDEXES:
                database.execute(create_index)

        _backfill_chats(database)
    finally:
        database.close()


def _backfill_chats(database):
    """给没有会话的旧轮次各补一个独立会话。"""
    # 这些轮次是加 chat_id 之前的旧数据，一轮补一个会话，跟以前一样
    with database:
        orphan_rows = database.execute(
            "SELECT `id`, `title`, `created_at` FROM `trip_sessions` "
            "WHERE `chat_id` IS NULL ORDER BY `id`"
        ).fetchall()
        for row in orphan_rows:
            cursor = database.execute(
                "INSERT INTO `trip_chats` (`title`, `created_at`, `updated_at`) VALUES (?, ?, ?)",
                (row["title"] or "出行记录", row["created_at"], row["created_at"]))
            database.execute(
                "UPDATE `trip_sessions` SET `chat_id` = ? WHERE `id` = ?",
                (cursor.lastrowid, row["id"]))


def save_trip_turn(user_query, ai_output, turn_kind="TRAVEL", chat_id=None):
    """把一轮出行对话整体存进会话，返回所属会话 id。"""
    if turn_kind not in ALLOWED_TURN_KINDS:
        raise ValueError(f"turn_kind 只能是 {ALLOWED_TURN_KINDS}，收到的是 {turn_kind!r}")

    ai_output = ai_output or {}

    destination = (ai_output.get("destination") or "").strip()
    title = (destination or user_query or "")[:14]

    database = open_database()
    try:
        with database:
            # 一次事务：中途报错整体回滚，不会留下没有子表数据的轮次
            if chat_id is None:
                cursor = database.execute(
                    "INSERT INTO `trip_chats` (`title`) VALUES (?)", (title,))
                chat_id = cursor.lastrowid
            else:
                # chat_id 不存在就新建，别把这一轮写成孤儿
                exists = database.execute(
                    "SELECT 1 FROM `trip_chats` WHERE `id` = ?", (chat_id,)).fetchone()
                if not exists:
                    cursor = database.execute(
                        "INSERT INTO `trip_chats` (`title`) VALUES (?)", (title,))
                    chat_id = cursor.lastrowid

            insert_result = database.execute(
                "INSERT INTO `trip_sessions` "
                "(`chat_id`, `title`, `turn_kind`, `destination`, `days`, `start_date`) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id,
                 title,
                 turn_kind,
                 destination,
                 int(ai_output.get("days") or 0),
                 ai_output.get("start_date") or ""))
            trip_id = insert_result.lastrowid

            # 两张子表都靠这个 trip_id 挂到本轮
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

            # 刷新排序用的时间戳，标题保持第一次的
            database.execute(
                "UPDATE `trip_chats` SET `updated_at` = datetime('now', 'localtime') "
                "WHERE `id` = ?", (chat_id,))

            return chat_id
    finally:
        database.close()


def list_trips(limit=50):
    """列出最近的出行会话（一个会话一行），新的在前面。"""
    database = open_database()
    try:
        found_rows = database.execute(
            "SELECT c.`id`, c.`title`, c.`created_at`, c.`updated_at`, "
            "       (SELECT COUNT(*) FROM `trip_sessions` t WHERE t.`chat_id` = c.`id`) AS `turn_count`, "
            "       COALESCE((SELECT t.`turn_kind` FROM `trip_sessions` t "
            "                 WHERE t.`chat_id` = c.`id` ORDER BY t.`id` DESC LIMIT 1), '') AS `last_kind` "
            "FROM `trip_chats` c "
            "ORDER BY c.`updated_at` DESC, c.`id` DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in found_rows]
    finally:
        database.close()


def get_trip(chat_id):
    """取一个会话的完整对话，按时间顺序给出每一轮；不存在返回 None。"""
    database = open_database()
    try:
        chat_row = database.execute(
            "SELECT `id`, `title`, `created_at`, `updated_at` FROM `trip_chats` WHERE `id` = ?",
            (chat_id,)
        ).fetchone()
        if not chat_row:
            return None

        turn_rows = database.execute(
            "SELECT * FROM `trip_sessions` WHERE `chat_id` = ? ORDER BY `id`", (chat_id,)
        ).fetchall()

        turns = []
        for row in turn_rows:
            trip_id = row["id"]
            user_row = database.execute(
                "SELECT `content` FROM `trip_user_inputs` "
                "WHERE `trip_id` = ? ORDER BY `id` LIMIT 1", (trip_id,)
            ).fetchone()
            ai_row = database.execute(
                "SELECT * FROM `trip_ai_outputs` "
                "WHERE `trip_id` = ? ORDER BY `id` LIMIT 1", (trip_id,)
            ).fetchone()

            turn = dict(row)
            turn["user_query"] = user_row["content"] if user_row else ""
            turn["ai_output"] = dict(ai_row) if ai_row else {}
            turns.append(turn)

        result = dict(chat_row)
        result["turns"] = turns
        return result
    finally:
        database.close()


def delete_trip(chat_id):
    """删除会话及其全部轮次，返回删掉的会话行数。"""
    database = open_database()
    try:
        with database:
            # 子表没有到 chat_id 的外键，只能手动按会话删
            database.execute(
                "DELETE FROM `trip_user_inputs` WHERE `trip_id` IN "
                "(SELECT `id` FROM `trip_sessions` WHERE `chat_id` = ?)", (chat_id,))
            database.execute(
                "DELETE FROM `trip_ai_outputs` WHERE `trip_id` IN "
                "(SELECT `id` FROM `trip_sessions` WHERE `chat_id` = ?)", (chat_id,))
            database.execute(
                "DELETE FROM `trip_sessions` WHERE `chat_id` = ?", (chat_id,))
            delete_result = database.execute(
                "DELETE FROM `trip_chats` WHERE `id` = ?", (chat_id,))
            return delete_result.rowcount
    finally:
        database.close()


def delete_trips(chat_ids):
    """批量删除多个会话，返回真正删掉的个数。

    一个会话删失败不影响其他会话，逐个删，最后只报成功数量。
    """
    deleted = 0
    for chat_id in chat_ids:
        try:
            if delete_trip(chat_id) > 0:
                deleted += 1
        except Exception as e:
            print(f"[数据库] 删除出行会话 {chat_id} 失败：{e}")

    return deleted
