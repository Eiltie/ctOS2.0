"""数据库清理工具

做什么：按菜单清理访客账号、某个账号的聊天/出行记录，或者全部记录。
怎么用：
    本机数据库（5432）：
        python -X utf8 -m databases.clean_db
    Docker 数据库（5433）：
        python -X utf8 -m databases.clean_db --docker
    直接在容器里（连的是容器自己的库）：
        docker exec -it ctos2-app python -m databases.clean_db

安全约定：
    删除前都会先显示有多少条，并要求输入确认词。
    访客账号只认 trial_ 开头、@ctos-trial.local 结尾的邮箱，不会碰真实账号。
"""

import os
import sys

# --docker：从宿主机连 Docker 映射出来的 5433 端口。
# 必须在 import core.db 之前设置，保证 load_dotenv 不覆盖它。
if "--docker" in sys.argv:
    os.environ["PG_HOST"] = "127.0.0.1"
    os.environ["PG_PORT"] = "5433"

from core.db import query, query_one, transaction

GUEST_EMAIL_LIKE = "trial_%@ctos-trial.local"

# 各张表在菜单里显示的中文名
TABLE_LABELS = {
    "messages": "聊天消息",
    "sessions": "聊天会话",
    "trip_user_inputs": "出行用户输入",
    "trip_ai_outputs": "出行 AI 产出",
    "trip_sessions": "出行轮次",
    "trip_chats": "出行会话",
    "feedback": "反馈",
    "users": "用户",
    "tenants": "租户",
}

# 删一个租户时，先删子表，再删父表
TENANT_TABLES = (
    "messages",
    "sessions",
    "trip_user_inputs",
    "trip_ai_outputs",
    "trip_sessions",
    "trip_chats",
    "feedback",
    "users",
)

# 只删聊天和出行，保留账号本身
BUSINESS_TABLES = (
    "messages",
    "sessions",
    "trip_user_inputs",
    "trip_ai_outputs",
    "trip_sessions",
    "trip_chats",
)


def ask(prompt):
    """读一行输入；管道结束时不崩。"""
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def confirm(word):
    """必须原样输入确认词才返回 True。"""
    return ask(f"确认请输入 {word}，其他任意内容取消：") == word


def print_connection():
    """打印当前连的是哪个库，避免清错地方。"""
    host = os.getenv("PG_HOST", "127.0.0.1")
    port = os.getenv("PG_PORT", "5432")
    dbname = os.getenv("PG_DBNAME", "ctos2")
    user = os.getenv("PG_USER", "ctos_app")
    print(f"当前数据库：{host}:{port}/{dbname}（用户 {user}）")

    if port == "5433" or host == "db":
        print("（这是 Docker 的数据库，8080 页面用的就是它）")
    else:
        print("（这是本机 5432 的数据库；8080 页面用的是 Docker 的 5433，要清那套请加 --docker）")


def count_table(table, where="", params=()):
    """数一张表有多少行；where 只由本文件写死，不接用户输入。"""
    sql = f"SELECT COUNT(*) AS n FROM {table}"
    if where:
        sql += f" WHERE {where}"
    row = query_one(sql, params)
    return row["n"] if row else 0


def find_guest_accounts():
    """找出所有访客账号。"""
    return query(
        "SELECT u.id AS user_id, u.email, u.tenant_id, u.created_at, t.name AS tenant_name "
        "FROM users u JOIN tenants t ON t.id = u.tenant_id "
        "WHERE u.email LIKE %s ORDER BY u.id",
        (GUEST_EMAIL_LIKE,),
    )


def find_account_by_email(email):
    """按邮箱找一个账号，找不到返回 None。"""
    return query_one(
        "SELECT u.id AS user_id, u.email, u.tenant_id, u.created_at, t.name AS tenant_name "
        "FROM users u JOIN tenants t ON t.id = u.tenant_id "
        "WHERE u.email = %s",
        ((email or "").strip().lower(),),
    )


def show_status():
    """打印数据库现状。"""
    print()
    print("===== 数据库现状 =====")
    print(f"租户：{count_table('tenants')}")
    print(f"用户：{count_table('users')}（其中访客 {count_table('users', 'email LIKE %s', (GUEST_EMAIL_LIKE,))}）")
    print(f"闲聊：会话 {count_table('sessions')}，消息 {count_table('messages')}")
    print(
        "出行："
        f"会话 {count_table('trip_chats')}，"
        f"轮次 {count_table('trip_sessions')}，"
        f"用户输入 {count_table('trip_user_inputs')}，"
        f"AI 产出 {count_table('trip_ai_outputs')}"
    )
    print(f"反馈：{count_table('feedback')}")

    guests = find_guest_accounts()
    if guests:
        print()
        print(f"访客账号（最多显示 10 个，共 {len(guests)} 个）：")
        for row in guests[:10]:
            print(f"  - {row['email']}（租户 {row['tenant_id']}）")
        if len(guests) > 10:
            print("  ...")


def print_deleted(result):
    """打印每张表删了多少行。"""
    for table, count in result.items():
        if count:
            print(f"  {TABLE_LABELS.get(table, table)}：{count} 行")


def delete_tenant_rows(cur, tenant_id):
    """删掉一个租户下的全部数据和租户本身。"""
    result = {}
    for table in TENANT_TABLES:
        cur.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))
        result[table] = cur.rowcount

    cur.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
    result["tenants"] = cur.rowcount
    return result


def delete_business_rows(cur, tenant_id):
    """只删聊天和出行记录，保留用户和租户。"""
    result = {}
    for table in BUSINESS_TABLES:
        cur.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))
        result[table] = cur.rowcount
    return result


def clean_guest_accounts():
    """清理所有访客账号及其数据。"""
    guests = find_guest_accounts()
    if not guests:
        print("\n没有访客账号，不用清理。")
        return

    print(f"\n找到 {len(guests)} 个访客账号：")
    for row in guests[:20]:
        print(f"  - {row['email']}（租户 {row['tenant_id']}）")
    if len(guests) > 20:
        print("  ...")

    print("\n会删掉这些账号的聊天、出行、反馈和账号本身，真实账号不受影响。")
    if not confirm("DELETE"):
        print("已取消。")
        return

    tenant_ids = sorted({row["tenant_id"] for row in guests})
    totals = {}

    with transaction() as cur:
        for tenant_id in tenant_ids:
            result = delete_tenant_rows(cur, tenant_id)
            for table, count in result.items():
                totals[table] = totals.get(table, 0) + count

    print("\n清理完成，删除了：")
    print_deleted(totals)


def clean_account_data():
    """清掉某个账号的聊天和出行记录，但保留账号。"""
    email = ask("\n要清理的账号邮箱：").strip().lower()
    account = find_account_by_email(email)
    if not account:
        print("没找到这个账号。")
        return

    print(f"\n账号：{account['email']}（租户 {account['tenant_id']}）")
    print("会删掉它的聊天和出行记录，账号保留。")
    if not confirm("DELETE"):
        print("已取消。")
        return

    with transaction() as cur:
        result = delete_business_rows(cur, account["tenant_id"])

    if any(result.values()):
        print("\n清理完成，删除了：")
        print_deleted(result)
    else:
        print("\n这个账号没有聊天或出行记录，没有可删的。")


def delete_account():
    """删掉某个账号、租户和全部数据。"""
    email = ask("\n要删除的账号邮箱：").strip().lower()
    account = find_account_by_email(email)
    if not account:
        print("没找到这个账号。")
        return

    print(f"\n账号：{account['email']}（租户 {account['tenant_id']}）")
    print("会删掉账号、租户、聊天、出行和反馈，无法恢复。")
    if not confirm("DELETE ACCOUNT"):
        print("已取消。")
        return

    with transaction() as cur:
        result = delete_tenant_rows(cur, account["tenant_id"])

    print("\n清理完成，删除了：")
    print_deleted(result)


def clean_all_chats():
    """清掉所有闲聊记录，账号保留。"""
    sessions = count_table("sessions")
    messages = count_table("messages")
    if not sessions and not messages:
        print("\n没有闲聊记录。")
        return

    print(f"\n会删掉所有闲聊：会话 {sessions} 个，消息 {messages} 条。账号和出行记录保留。")
    if not confirm("DELETE ALL"):
        print("已取消。")
        return

    with transaction() as cur:
        cur.execute("DELETE FROM messages")
        deleted_messages = cur.rowcount
        cur.execute("DELETE FROM sessions")
        deleted_sessions = cur.rowcount

    print(f"\n清理完成：聊天消息 {deleted_messages} 行，聊天会话 {deleted_sessions} 行。")


def clean_all_trips():
    """清掉所有出行记录，账号保留。"""
    counts = {
        "trip_chats": count_table("trip_chats"),
        "trip_sessions": count_table("trip_sessions"),
        "trip_user_inputs": count_table("trip_user_inputs"),
        "trip_ai_outputs": count_table("trip_ai_outputs"),
    }
    if not any(counts.values()):
        print("\n没有出行记录。")
        return

    print("\n会删掉所有出行记录：")
    print_deleted(counts)
    print("账号和闲聊记录保留。")
    if not confirm("DELETE ALL"):
        print("已取消。")
        return

    with transaction() as cur:
        result = {}
        for table in ("trip_user_inputs", "trip_ai_outputs", "trip_sessions", "trip_chats"):
            cur.execute(f"DELETE FROM {table}")
            result[table] = cur.rowcount

    print("\n清理完成，删除了：")
    print_deleted(result)


def clean_all_feedback():
    """清掉所有反馈。"""
    total = count_table("feedback")
    if not total:
        print("\n没有反馈。")
        return

    print(f"\n会删掉所有反馈，共 {total} 条。")
    if not confirm("DELETE ALL"):
        print("已取消。")
        return

    with transaction() as cur:
        cur.execute("DELETE FROM feedback")
        deleted = cur.rowcount

    print(f"\n清理完成：反馈 {deleted} 行。")


def show_menu():
    print()
    print("===== 数据库清理工具 =====")
    print("1. 查看数据库现状")
    print("2. 清理访客账号（trial_...）及其全部数据")
    print("3. 清理某个账号的聊天和出行记录（保留账号）")
    print("4. 删除某个账号及其全部数据")
    print("5. 清理所有闲聊记录（账号保留）")
    print("6. 清理所有出行记录（账号保留）")
    print("7. 清理所有反馈")
    print("0. 退出")


def main():
    print_connection()

    while True:
        show_menu()
        choice = ask("请选择：")

        if choice == "0":
            print("再见。")
            break
        if choice == "1":
            show_status()
        elif choice == "2":
            clean_guest_accounts()
        elif choice == "3":
            clean_account_data()
        elif choice == "4":
            delete_account()
        elif choice == "5":
            clean_all_chats()
        elif choice == "6":
            clean_all_trips()
        elif choice == "7":
            clean_all_feedback()
        else:
            print("没有这个选项，请输入 0~7。")


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("用法：")
        print("  python -X utf8 -m databases.clean_db            清理本机 5432")
        print("  python -X utf8 -m databases.clean_db --docker   清理 Docker 5433")
        print("  docker exec -it ctos2-app python -m databases.clean_db   在容器里清理")
        sys.exit(0)

    try:
        main()
    except Exception as e:
        print("\n出错了：", e)
        print("检查 config/.env 里的 PG_* 配置，以及数据库/Docker 是否启动。")
