"""命令行小工具：查看数据库内容，不参与 Web 服务。

用法：
    python -X utf8 -m databases.db_view              列出所有用户和会话
    python -X utf8 -m databases.db_view stats        统计信息
    python -X utf8 -m databases.db_view show 5       看某个会话的完整对话
    python -X utf8 -m databases.db_view search 端口   在所有消息里搜关键词
    python -X utf8 -m databases.db_view users        列出所有用户
    python -X utf8 -m databases.db_view trips        列出出行会话

PostgreSQL 版本。和 SQLite 版的差异：
  - 占位符用 %s
  - 查询走 core.db 的 query / query_one
  - 多了 users / tenants 的查看（多租户之后才有）
"""

import sys

from core.db import check_connection, query, query_one


def line(char="=", width=64):
    """打印一条分隔线。"""
    print(char * width)


def _fmt_time(value) -> str:
    """时间字段转成好读的字符串。"""
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- 列表

def list_users():
    """列出所有用户，带租户和会话数。"""
    rows = query(
        "SELECT u.id, u.email, u.display_name, u.tenant_id, u.created_at, "
        "       (SELECT COUNT(*) FROM sessions s WHERE s.tenant_id = u.tenant_id) AS session_count, "
        "       (SELECT COUNT(*) FROM trip_chats t WHERE t.tenant_id = u.tenant_id) AS trip_count "
        "FROM users u ORDER BY u.id"
    )

    line()
    info = check_connection()
    print(f"数据库：{info.get('db')}    用户总数：{len(rows)}")
    line()

    if not rows:
        print("（还没有任何用户注册）")
        return

    print(f"  {'ID':>4}  {'租户':>5}  {'会话':>4}  {'出行':>4}  邮箱")
    print(f"  {'-'*4}  {'-'*5}  {'-'*4}  {'-'*4}  {'-'*32}")
    for row in rows:
        print(f"  {row['id']:>4}  {row['tenant_id']:>5}  "
              f"{row['session_count']:>4}  {row['trip_count']:>4}  {row['email']}")


def show_sessions(tenant_id=None):
    """列出所有会话（或某个租户的），带消息数和最后更新时间。"""
    sql = (
        "SELECT s.id, s.tenant_id, s.title, s.created_at, s.updated_at, "
        "       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count, "
        "       COALESCE(u.email, '（无用户）') AS email "
        "FROM sessions s "
        "LEFT JOIN users u ON u.tenant_id = s.tenant_id "
    )
    params = ()
    if tenant_id is not None:
        sql += "WHERE s.tenant_id = %s "
        params = (tenant_id,)
    sql += "ORDER BY s.updated_at DESC"

    rows = query(sql, params)

    line()
    info = check_connection()
    print(f"数据库：{info.get('db')}    会话数：{len(rows)}")
    line()

    if not rows:
        print("（还没有任何会话）")
        print("\n去网页上聊几句，再回来看看。")
        return

    print(f"  {'ID':>4}  {'租户':>4}  {'消息':>4}  {'最后更新':<16}  {'用户':<20} 标题")
    print(f"  {'-'*4}  {'-'*4}  {'-'*4}  {'-'*16}  {'-'*20} {'-'*20}")
    for row in rows:
        title = row["title"] or ""
        if len(title) > 20:
            title = title[:20] + "…"
        print(f"  {row['id']:>4}  {row['tenant_id']:>4}  {row['message_count']:>4}  "
              f"{_fmt_time(row['updated_at']):<16}  {row['email'][:20]:<20} {title}")

    print("\n看某个会话的完整对话：")
    print("  python -X utf8 -m databases.db_view show 会话ID")


def show_trips(tenant_id=None, limit=20):
    """列出出行会话，一个会话一行。"""
    sql = (
        "SELECT c.id, c.tenant_id, c.title, c.updated_at, "
        "       (SELECT COUNT(*) FROM trip_sessions t WHERE t.chat_id = c.id) AS turn_count, "
        "       COALESCE(u.email, '（无用户）') AS email "
        "FROM trip_chats c "
        "LEFT JOIN users u ON u.tenant_id = c.tenant_id "
    )
    params = ()
    if tenant_id is not None:
        sql += "WHERE c.tenant_id = %s "
        params = (tenant_id,)
    sql += "ORDER BY c.updated_at DESC LIMIT %s"
    params = params + (limit,)

    rows = query(sql, params)

    line()
    print(f"出行会话：{len(rows)} 条（最多显示 {limit} 条）")
    line()

    if not rows:
        print("（还没有出行会话）")
        return

    print(f"  {'ID':>4}  {'租户':>4}  {'轮数':>4}  {'最后更新':<16}  {'用户':<20} 标题")
    print(f"  {'-'*4}  {'-'*4}  {'-'*4}  {'-'*16}  {'-'*20} {'-'*20}")
    for row in rows:
        title = row["title"] or ""
        if len(title) > 20:
            title = title[:20] + "…"
        print(f"  {row['id']:>4}  {row['tenant_id']:>4}  {row['turn_count']:>4}  "
              f"{_fmt_time(row['updated_at']):<16}  {row['email'][:20]:<20} {title}")


# ---------------------------------------------------------------- 详情

def show_session(session_id):
    """打印某个会话的完整对话。"""
    session_row = query_one(
        "SELECT s.id, s.title, s.tenant_id, s.created_at, s.updated_at, "
        "       COALESCE(u.email, '（无用户）') AS email "
        "FROM sessions s LEFT JOIN users u ON u.tenant_id = s.tenant_id "
        "WHERE s.id = %s",
        (session_id,),
    )

    if not session_row:
        print(f"找不到会话 {session_id}")
        return

    line()
    print(f"会话 {session_row['id']}：{session_row['title']}")
    print(f"租户 {session_row['tenant_id']}    用户 {session_row['email']}")
    print(f"创建 {_fmt_time(session_row['created_at'])}   更新 {_fmt_time(session_row['updated_at'])}")
    line()

    messages = query(
        "SELECT role, content, created_at FROM messages "
        "WHERE session_id = %s ORDER BY id",
        (session_id,),
    )

    if not messages:
        print("（这个会话还没有消息）")
        return

    for message in messages:
        speaker = "用户" if message["role"] == "user" else "AI"
        print(f"\n[{speaker}] {_fmt_time(message['created_at'])}")
        print(f"  {message['content']}")


def show_trip(chat_id):
    """打印某个出行会话的完整内容。"""
    chat_row = query_one(
        "SELECT c.id, c.title, c.tenant_id, c.updated_at, "
        "       COALESCE(u.email, '（无用户）') AS email "
        "FROM trip_chats c LEFT JOIN users u ON u.tenant_id = c.tenant_id "
        "WHERE c.id = %s",
        (chat_id,),
    )

    if not chat_row:
        print(f"找不到出行会话 {chat_id}")
        return

    line()
    print(f"出行会话 {chat_row['id']}：{chat_row['title']}")
    print(f"租户 {chat_row['tenant_id']}    用户 {chat_row['email']}")
    line()

    turns = query(
        "SELECT id, turn_kind, destination, days, start_date, created_at "
        "FROM trip_sessions WHERE chat_id = %s ORDER BY id",
        (chat_id,),
    )

    if not turns:
        print("（这个会话还没有轮次）")
        return

    for turn in turns:
        print(f"\n--- 第 {turn['id']} 轮 · {turn['turn_kind']} · {_fmt_time(turn['created_at'])} ---")
        print(f"目的地：{turn['destination']}    天数：{turn['days']}    出发：{turn['start_date']}")

        user_row = query_one(
            "SELECT content FROM trip_user_inputs WHERE trip_id = %s ORDER BY id LIMIT 1",
            (turn["id"],),
        )
        if user_row:
            print(f"\n[用户] {user_row['content']}")

        ai_row = query_one(
            "SELECT weather, spots, itinerary, route_plan, chat_reply "
            "FROM trip_ai_outputs WHERE trip_id = %s ORDER BY id LIMIT 1",
            (turn["id"],),
        )
        if ai_row:
            if ai_row["chat_reply"]:
                print(f"\n[AI] {ai_row['chat_reply']}")
            for key, label in (("weather", "天气"), ("spots", "景点"),
                               ("itinerary", "行程"), ("route_plan", "路线")):
                if ai_row[key]:
                    print(f"\n【{label}】\n{ai_row[key][:300]}...")


# ---------------------------------------------------------------- 搜索和统计

def search(keyword):
    """在所有消息内容里搜关键词。"""
    rows = query(
        "SELECT m.session_id, m.role, m.content, m.created_at, s.title "
        "FROM messages m JOIN sessions s ON s.id = m.session_id "
        "WHERE m.content ILIKE %s "
        "ORDER BY m.session_id, m.id",
        (f"%{keyword}%",),
    )

    line()
    print(f"搜索「{keyword}」")
    line()

    if not rows:
        print("没找到。")
        return

    print(f"找到 {len(rows)} 条：\n")
    for row in rows:
        speaker = "用户" if row["role"] == "user" else "AI"
        text = row["content"].replace("\n", " ")
        if len(text) > 70:
            text = text[:70] + "…"
        print(f"  [会话{row['session_id']}] {(row['title'] or '')[:16]}")
        print(f"    [{speaker}] {text}\n")


def show_stats():
    """打印各张表的行数和数据库大小。"""
    info = check_connection()

    counts = query(
        "SELECT "
        "  (SELECT COUNT(*) FROM users) AS users, "
        "  (SELECT COUNT(*) FROM tenants) AS tenants, "
        "  (SELECT COUNT(*) FROM sessions) AS sessions, "
        "  (SELECT COUNT(*) FROM messages) AS messages, "
        "  (SELECT COUNT(*) FROM trip_chats) AS trip_chats, "
        "  (SELECT COUNT(*) FROM trip_sessions) AS trip_sessions"
    )[0]

    size = query_one(
        "SELECT pg_size_pretty(pg_database_size(current_database())) AS size"
    )

    line()
    print("统计")
    line()
    print(f"  数据库：  {info.get('db')}（{size['size'] if size else '?'}）")
    print(f"  连接用户：{info.get('usr')}")
    print()
    print(f"  用户：    {counts['users']}")
    print(f"  租户：    {counts['tenants']}")
    print(f"  闲聊会话：{counts['sessions']}")
    print(f"  消息：    {counts['messages']}")
    print(f"  出行会话：{counts['trip_chats']}")
    print(f"  出行轮次：{counts['trip_sessions']}")

    # 孤儿数据检查：子表有、父表没有
    orphans = query_one(
        "SELECT COUNT(*) AS n FROM messages m "
        "LEFT JOIN sessions s ON s.id = m.session_id WHERE s.id IS NULL"
    )
    n = orphans["n"] if orphans else 0
    print(f"\n  孤儿消息：{n} 条 {'✓ 数据一致' if n == 0 else '⚠ 有残留'}")


# ---------------------------------------------------------------- 入口

def print_help():
    """打印用法。"""
    print(__doc__)


def main():
    """按命令行参数分派到对应子命令。"""
    arguments = sys.argv[1:]

    if not arguments:
        list_users()
        print()
        show_sessions()
        return

    command = arguments[0].lower()

    if command == "users":
        list_users()
    elif command == "sessions":
        show_sessions()
    elif command == "trips":
        show_trips()
    elif command == "show":
        if len(arguments) < 2:
            print("用法：show 会话ID")
            return
        show_session(int(arguments[1]))
    elif command == "trip":
        if len(arguments) < 2:
            print("用法：trip 出行会话ID")
            return
        show_trip(int(arguments[1]))
    elif command == "search":
        if len(arguments) < 2:
            print("用法：search 关键词")
            return
        search(arguments[1])
    elif command == "stats":
        show_stats()
    else:
        print_help()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出")
