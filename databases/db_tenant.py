"""全局身份表：tenants（租户）。

为什么单独一个文件：
  这张表不属于任何一个业务模块——users / sessions / trip_chats / trip_sessions
  全都外键引用它。以前它是由「闲聊」模块的 create_chat_tables() 顺带创建的，
  结果是：删掉闲聊模块，认证和出行也跟着坏。

  现在它独立出来当作共用底座的一部分：
    - 谁都可以引用它，但它不反过来依赖任何业务模块
    - 建表顺序固定：tenants 最先，其余表都排在它后面
"""

from core.db import execute, query, query_one

# 默认租户：早期还没接入登录时的兜底数据都挂在它下面。
# 现在每个注册用户有自己的租户，这一行主要给「建表即能用」和本地调试兜底。
DEFAULT_TENANT_NAME = "默认租户"
DEFAULT_TENANT_SLUG = "default"

CREATE_TENANTS_TABLE = """
CREATE TABLE IF NOT EXISTS tenants (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT        NOT NULL,
    slug        TEXT        NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def create_tenant_tables():
    """建 tenants 表并确保默认租户存在；已存在就跳过，不动已有数据。"""
    execute(CREATE_TENANTS_TABLE)
    execute(
        "INSERT INTO tenants (name, slug) VALUES (%s, %s) "
        "ON CONFLICT (slug) DO NOTHING",
        (DEFAULT_TENANT_NAME, DEFAULT_TENANT_SLUG),
    )


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


if __name__ == "__main__":
    create_tenant_tables()
    print(f"tenants 表建好了，当前租户数：{count_tenants()}")
