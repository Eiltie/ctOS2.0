"""租户表 tenants 的查询。建表语句在 databases/schema.sql 里。

这张表不属于任何业务模块，但 users / sessions / trip_chats 全都外键引用它。
以前它是被对话模块的建表函数顺带创建的，结果删掉对话模块，认证和出行也跟着坏。
现在独立出来：谁都能引用它，它不反过来依赖任何模块。
"""

from databases.conn import execute, query, query_one

# 默认租户：早期还没接入登录时的兜底数据都挂在它下面。
# 现在每个注册用户有自己的租户，这一行主要给「建库即能用」和本地调试兜底。
DEFAULT_TENANT_NAME = "默认租户"
DEFAULT_TENANT_SLUG = "default"


def list_tenants(limit=50):
    """列出最近的租户，调试用。"""
    return query(
        "SELECT id, name, slug, created_at FROM tenants ORDER BY id DESC LIMIT %s",
        (limit,),
    )


def count_tenants() -> int:
    """租户总数，统计用。"""
    row = query_one("SELECT COUNT(*) AS n FROM tenants")
    return row["n"] if row else 0
