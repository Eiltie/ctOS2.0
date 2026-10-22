import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctOS2_databases.ctOS2_db import open_database, DATABASE_FILE

# 命令行小工具：查看、搜索、导出现有数据，不参与 Web 服务


def line(char="=", width=60):
    """打印一条分隔线。"""
    print(char * width)


def list_sessions():
    """列出所有会话，带消息数和最后更新时间。"""
    database = open_database()
    try:
        sessions = database.execute(
            "SELECT `id`, `title`, `created_at`, `updated_at` "
            "FROM `sessions` ORDER BY `id`"
        ).fetchall()

        line()
        print(f"数据库：{DATABASE_FILE.name}")
        line()

        if not sessions:
            print("（数据库是空的，还没有任何会话）")
            print("\n去网页上聊几句，再回来看看。")
            return

        print(f"共 {len(sessions)} 个会话：\n")
        print(f"  {'ID':>4}  {'消息数':>6}  {'最后更新':<20} 标题")
        print(f"  {'-'*4}  {'-'*6}  {'-'*20} {'-'*30}")

        for session_row in sessions:
            session_id = session_row["id"]
            message_count = database.execute(
                "SELECT COUNT(*) FROM `messages` WHERE `session_id` = ?",
                (session_id,)
            ).fetchone()[0]
            title = session_row["title"]
            if len(title) > 30:
                title = title[:30] + "…"
            print(f"  {session_id:>4}  {message_count:>6}  "
                  f"{session_row['updated_at']:<20} {title}")

        print(f"\n看某个会话的完整对话：")
        print(f"  venv\\Scripts\\python.exe -X utf8 "
              f"ctOS2_databases\\ctOS2_db_view.py show 会话ID")
    finally:
        database.close()


def show_session(session_id):
    """打印某个会话的完整对话。"""
    database = open_database()
    try:
        session_row = database.execute(
            "SELECT `id`, `title`, `created_at`, `updated_at` "
            "FROM `sessions` WHERE `id` = ?", (session_id,)
        ).fetchone()

        if not session_row:
            print(f"找不到会话 {session_id}")
            return

        line()
        print(f"会话 {session_row['id']}：{session_row['title']}")
        print(f"创建 {session_row['created_at']}   更新 {session_row['updated_at']}")
        line()

        messages = database.execute(
            "SELECT `role`, `content`, `created_at` FROM `messages` "
            "WHERE `session_id` = ? ORDER BY `id`", (session_id,)
        ).fetchall()

        if not messages:
            print("（这个会话还没有消息）")
            return

        for message in messages:
            speaker = "你" if message["role"] == "user" else "AI"
            print(f"\n[{speaker}] {message['created_at']}")
            print(f"  {message['content']}")
    finally:
        database.close()


def search(keyword):
    """在所有消息内容里搜关键词。"""
    database = open_database()
    try:
        found_rows = database.execute(
            "SELECT m.`session_id`, m.`role`, m.`content`, m.`created_at`, "
            "       s.`title` "
            "FROM `messages` AS m "
            "JOIN `sessions` AS s ON s.`id` = m.`session_id` "
            "WHERE m.`content` LIKE ? "
            "ORDER BY m.`session_id`, m.`id`",
            (f"%{keyword}%",)
        ).fetchall()

        line()
        print(f"搜索「{keyword}」")
        line()

        if not found_rows:
            print("没找到。")
            return

        print(f"找到 {len(found_rows)} 条：\n")
        for row in found_rows:
            speaker = "你" if row["role"] == "user" else "AI"
            text = row["content"].replace("\n", " ")
            if len(text) > 70:
                text = text[:70] + "…"
            print(f"  [会话{row['session_id']}] {row['title'][:16]}")
            print(f"    [{speaker}] {text}\n")
    finally:
        database.close()


def export_session(session_id):
    """把某个会话导出成 txt，放在数据库目录下。"""
    database = open_database()
    try:
        session_row = database.execute(
            "SELECT `id`, `title`, `created_at` FROM `sessions` WHERE `id` = ?",
            (session_id,)
        ).fetchone()

        if not session_row:
            print(f"找不到会话 {session_id}")
            return

        messages = database.execute(
            "SELECT `role`, `content`, `created_at` FROM `messages` "
            "WHERE `session_id` = ? ORDER BY `id`", (session_id,)
        ).fetchall()

        export_file = DATABASE_FILE.parent / f"会话{session_id}_导出.txt"

        content_lines = [
            f"会话 {session_row['id']}：{session_row['title']}",
            f"创建时间：{session_row['created_at']}",
            "=" * 50,
            "",
        ]
        for message in messages:
            speaker = "你" if message["role"] == "user" else "AI"
            content_lines.append(f"[{speaker}] {message['created_at']}")
            content_lines.append(message["content"])
            content_lines.append("")

        export_file.write_text("\n".join(content_lines), encoding="utf-8")
        print(f"已导出 {len(messages)} 条消息到：\n  {export_file}")
    finally:
        database.close()


def show_stats():
    """打印会话数、消息数、孤儿数据等统计信息。"""
    database = open_database()
    try:
        session_count = database.execute("SELECT COUNT(*) FROM `sessions`").fetchone()[0]
        message_count = database.execute("SELECT COUNT(*) FROM `messages`").fetchone()[0]

        user_messages = database.execute(
            "SELECT COUNT(*) FROM `messages` WHERE `role` = 'user'").fetchone()[0]
        ai_messages = database.execute(
            "SELECT COUNT(*) FROM `messages` WHERE `role` = 'assistant'").fetchone()[0]

        line()
        print("统计")
        line()
        print(f"  数据库文件：{DATABASE_FILE}")
        print(f"  文件大小：  {DATABASE_FILE.stat().st_size:,} 字节")
        print(f"  会话数：    {session_count}")
        print(f"  消息总数：  {message_count}")
        print(f"    你发的：  {user_messages}")
        print(f"    AI 回的： {ai_messages}")

        if message_count:
            total_chars = database.execute(
                "SELECT SUM(LENGTH(`content`)) FROM `messages`").fetchone()[0] or 0
            print(f"  总字数：    {total_chars:,}")

        orphan_count = database.execute(
            "SELECT COUNT(*) FROM `messages` "
            "WHERE `session_id` NOT IN (SELECT `id` FROM `sessions`)"
        ).fetchone()[0]
        print(f"  孤儿消息：  {orphan_count} 条 "
              f"{'✓ 数据一致' if orphan_count == 0 else '⚠ 有残留，建议清理'}")
    finally:
        database.close()


def print_help():
    """打印用法。"""
    # 用法就是模块 docstring，改参数时记得同步
    print(__doc__)


def main():
    """按命令行参数分派到对应子命令。"""
    arguments = sys.argv[1:]

    if not arguments:
        list_sessions()
        return

    command = arguments[0].lower()

    if command == "sessions":
        list_sessions()
    elif command == "show":
        if len(arguments) < 2:
            print("用法：show 会话ID")
            return
        show_session(int(arguments[1]))
    elif command == "search":
        if len(arguments) < 2:
            print("用法：search 关键词")
            return
        search(arguments[1])
    elif command == "export":
        if len(arguments) < 2:
            print("用法：export 会话ID")
            return
        export_session(int(arguments[1]))
    elif command == "stats":
        show_stats()
    else:
        print_help()


if __name__ == "__main__":
    if not DATABASE_FILE.exists():
        print(f"数据库文件还不存在：{DATABASE_FILE}")
        print("先启动项目聊几句，或者先跑一次建表：")
        print("  venv\\Scripts\\python.exe ctOS2_databases\\ctOS2_db.py")
    else:
        main()
