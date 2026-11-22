"""用户认证的表和增删改查。

设计：一人一户（一个用户注册时自动创建一个租户）
  最小 SaaS 阶段，每个用户有自己的独立空间，相互看不到数据。
  以后要做团队协作，再加「用户-租户」多对多关系表即可。

为什么 users 表也有 tenant_id：
  它是“这个用户属于自己的那个租户”。
  数据查询用的都是这个 tenant_id，所以用户和租户目前是一对一。
"""

from common.db import execute, query_one, transaction

# users 表建表语句在 databases/schema.sql


def touch_last_seen(tenant_id: int) -> None:
    """记录最后一次活跃时间，用于统计在线人数。

    注意参数是 **tenant_id**，不是 user.id ——
    业务接口手里只有 tenant_id，而 users 表的 tenant_id 与 id 并不是同一个值，
    所以这里按 tenant_id 找行（一人一户，正好唯一）。

    失败不影响主流程：这只是统计字段，写不进去也不该让请求报错。
    """
    if not tenant_id:
        return
    try:
        execute(
            "UPDATE users SET last_seen_at = CURRENT_TIMESTAMP WHERE tenant_id = %s",
            (tenant_id,),
        )
    except Exception:
        pass


def count_online(minutes: int = 10) -> int:
    """最近 N 分钟内有活跃的用户数。

    口径说明：按 user 计，同一用户开多个标签页只算 1 人。
    访客也是 user，所以基本上等于「最近打开的浏览器数」。
    """
    try:
        row = query_one(
            "SELECT COUNT(*) AS n FROM users "
            "WHERE last_seen_at IS NOT NULL "
            "  AND last_seen_at > CURRENT_TIMESTAMP - (%s || ' minutes')::interval",
            (int(minutes),),
        )
        return row["n"] if row else 0
    except Exception:
        return 0


def normalize_email(email: str) -> str:
    """邮箱统一转小写去空格，避免 A@x.com 和 a@x.com 被当成两个账号。"""
    return (email or "").strip().lower()


def get_user_by_email(email: str) -> dict | None:
    """按邮箱查用户，注册登录都用它。"""
    return query_one(
        "SELECT id, tenant_id, email, password_hash, display_name, created_at "
        "FROM users WHERE email = %s",
        (normalize_email(email),),
    )


def get_user_by_id(user_id: int) -> dict | None:
    """按 id 查用户，每次请求校验 token 时用。"""
    return query_one(
        "SELECT id, tenant_id, email, display_name, created_at "
        "FROM users WHERE id = %s",
        (user_id,),
    )


def create_user(email: str, password_hash: str, display_name: str = "") -> dict:
    """注册：新建一个租户 + 一个用户，两者绑定，返回用户信息。

    为什么在一个事务里：如果租户建完、用户插入失败，
    会留下一个没有用户的空租户，越积越多。整体回滚更干净。

    返回的 dict 里**不含 password_hash**，避免它被意外传出去。
    """
    email = normalize_email(email)
    display_name = display_name.strip() or email.split("@")[0]

    with transaction() as cur:
        # 每个用户一个独立租户，slug 用邮箱保证唯一
        cur.execute(
            "INSERT INTO tenants (name, slug) VALUES (%s, %s) RETURNING id",
            (display_name, email),
        )
        tenant_id = cur.fetchone()["id"]

        cur.execute(
            "INSERT INTO users (tenant_id, email, password_hash, display_name) "
            "VALUES (%s, %s, %s, %s) RETURNING id, created_at",
            (tenant_id, email, password_hash, display_name),
        )
        row = cur.fetchone()

    return {
        "id": row["id"],
        "tenant_id": tenant_id,
        "email": email,
        "display_name": display_name,
        "created_at": row["created_at"],
    }


def touch_last_login(user_id: int) -> None:
    """记录最后一次登录时间，失败不影响登录。"""
    try:
        execute(
            "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s",
            (user_id,),
        )
    except Exception:
        # 这个字段只是统计用，写失败不该让用户登不进去
        pass


def count_users() -> int:
    """用户总数，用于判断是不是第一个用户。"""
    row = query_one("SELECT COUNT(*) AS n FROM users")
    return row["n"] if row else 0
