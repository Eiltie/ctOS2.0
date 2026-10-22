from ctOS2_databases.ctOS2_db import open_database

# 闲聊模块的表和增删改查：sessions 存会话，messages 存消息（级联删除）

ALLOWED_ROLES = ("user", "assistant")

CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS `sessions` (
    `id`         INTEGER PRIMARY KEY AUTOINCREMENT,
    `title`      TEXT NOT NULL,
    `created_at` TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    `updated_at` TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
)
"""

CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS `messages` (
    `id`         INTEGER PRIMARY KEY AUTOINCREMENT,
    `session_id` INTEGER NOT NULL,
    `role`       TEXT NOT NULL,
    `content`    TEXT NOT NULL,
    `created_at` TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (`session_id`) REFERENCES `sessions` (`id`) ON DELETE CASCADE
)
"""

CREATE_MESSAGES_INDEX = """
CREATE INDEX IF NOT EXISTS `ix_messages_session_id` ON `messages` (`session_id`)
"""


def create_chat_tables():
    """建闲聊的两张表和索引，已存在就跳过。"""
    database = open_database()
    try:
        with database:
            database.execute(CREATE_SESSIONS_TABLE)
            database.execute(CREATE_MESSAGES_TABLE)
            database.execute(CREATE_MESSAGES_INDEX)
    finally:
        database.close()


def create_session(title):
    """新建一个会话，返回它的 id。"""
    database = open_database()
    try:
        with database:
            insert_result = database.execute(
                "INSERT INTO `sessions` (`title`) VALUES (?)", (title,))
            return insert_result.lastrowid
    finally:
        database.close()


def list_sessions():
    """列出所有会话，最近更新的排在前面。"""
    database = open_database()
    try:
        found_rows = database.execute(
            "SELECT `id`, `title`, `created_at`, `updated_at` "
            "FROM `sessions` ORDER BY `updated_at` DESC, `id` DESC"
        ).fetchall()
        return [dict(row) for row in found_rows]
    finally:
        database.close()


def delete_session(session_id):
    """删除会话，它的消息级联删掉，返回删掉的行数。"""
    database = open_database()
    try:
        with database:
            delete_result = database.execute(
                "DELETE FROM `sessions` WHERE `id` = ?", (session_id,))
            return delete_result.rowcount
    finally:
        database.close()


def add_message(session_id, role, content):
    """给会话追加一条消息并刷新会话时间，返回新消息 id。"""
    if role not in ALLOWED_ROLES:
        raise ValueError(f"role 只能是 {ALLOWED_ROLES}，收到的是 {role!r}")

    database = open_database()
    try:
        with database:
            insert_result = database.execute(
                "INSERT INTO `messages` (`session_id`, `role`, `content`) "
                "VALUES (?, ?, ?)", (session_id, role, content))
            new_message_id = insert_result.lastrowid

            database.execute(
                "UPDATE `sessions` SET `updated_at` = datetime('now', 'localtime') "
                "WHERE `id` = ?", (session_id,))
            return new_message_id
    finally:
        database.close()


def get_recent_messages(session_id, limit=20):
    """取最近 limit 条消息，按时间从早到晚返回。"""
    database = open_database()
    try:
        found_rows = database.execute(
            "SELECT `id`, `session_id`, `role`, `content`, `created_at` "
            "FROM `messages` WHERE `session_id` = ? "
            "ORDER BY `id` DESC LIMIT ?", (session_id, limit)
        ).fetchall()
        return list(reversed([dict(row) for row in found_rows]))
    finally:
        database.close()


def get_session_messages(session_id):
    """取会话全部消息，按时间从早到晚返回。"""
    database = open_database()
    try:
        found_rows = database.execute(
            "SELECT `id`, `session_id`, `role`, `content`, `created_at` "
            "FROM `messages` WHERE `session_id` = ? ORDER BY `id` ASC",
            (session_id,)
        ).fetchall()
        return [dict(row) for row in found_rows]
    finally:
        database.close()
