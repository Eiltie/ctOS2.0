"""闲聊模块的表和增删改查。

表：
    sessions  一次会话，主键 id
    messages  会话里的每条消息，外键 session_id 指向 sessions.id（删除时级联）

连接和数据库路径统一在 ctOS2_db.py 里，本文件只用不重写。
"""

from ctOS2_databases.ctOS2_db import open_database

# 消息允许的角色，只有用户和 AI 两种
ALLOWED_ROLES = ("user", "assistant")


# ---------------------------------------------------------------- 建表
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
    """建闲聊的两张表，已存在就跳过。"""
    database = open_database()
    try:
        with database:
            database.execute(CREATE_SESSIONS_TABLE)
            database.execute(CREATE_MESSAGES_TABLE)
            database.execute(CREATE_MESSAGES_INDEX)
    finally:
        database.close()


# ---------------------------------------------------------------- 会话
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
    """列出所有会话，最近更新的排在最前面。"""
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
    """删除一个会话，它下面的消息会一起删掉。返回删掉的行数。"""
    database = open_database()
    try:
        with database:
            delete_result = database.execute(
                "DELETE FROM `sessions` WHERE `id` = ?", (session_id,))
            return delete_result.rowcount
    finally:
        database.close()


# ---------------------------------------------------------------- 消息
def add_message(session_id, role, content):
    """给会话追加一条消息，返回新消息的 id。"""
    if role not in ALLOWED_ROLES:
        raise ValueError(f"role 只能是 {ALLOWED_ROLES}，收到的是 {role!r}")

    database = open_database()
    try:
        with database:
            insert_result = database.execute(
                "INSERT INTO `messages` (`session_id`, `role`, `content`) "
                "VALUES (?, ?, ?)", (session_id, role, content))
            new_message_id = insert_result.lastrowid

            # 顺便刷新会话的更新时间，这样会话列表的排序才有意义
            database.execute(
                "UPDATE `sessions` SET `updated_at` = datetime('now', 'localtime') "
                "WHERE `id` = ?", (session_id,))
            return new_message_id
    finally:
        database.close()


def get_recent_messages(session_id, limit=20):
    """取最近几条消息，按时间从早到晚返回。"""
    database = open_database()
    try:
        found_rows = database.execute(
            "SELECT `id`, `session_id`, `role`, `content`, `created_at` "
            "FROM `messages` WHERE `session_id` = ? "
            "ORDER BY `id` DESC LIMIT ?", (session_id, limit)
        ).fetchall()
        # 查询时是从晚到早（为了取到最近几条），这里翻回来
        return list(reversed([dict(row) for row in found_rows]))
    finally:
        database.close()


def get_session_messages(session_id):
    """取某个会话的全部消息，按时间从早到晚返回。"""
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
