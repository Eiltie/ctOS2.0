"""数据库公共地基：PostgreSQL 连接与通用操作。

从 SQLite 迁过来的原因（SaaS 需要）：
  - SQLite 是单文件，写操作锁整个文件，多进程/多实例同时写会排队
  - SQLite 没有 schema 概念，做不了租户隔离
  - 云上部署时文件不持久，容器一重建数据就没了

关于连接方式：
  没有用 psycopg_pool。它在 Python 3.14 上退出时会有线程清理报错
  （PythonFinalizationError: cannot join thread at interpreter shutdown），
  我们的请求量很小，每个操作开一个短连接足够快，
  PG 的建连开销约 1~3 毫秒，比维护连接池的复杂度划算。
  以后并发上来了，再换回连接池并加显式生命周期管理。

关于 SQL 写法（跟 SQLite 的差异，写新代码时注意）：
  占位符      ?              →  %s
  自增主键    AUTOINCREMENT  →  GENERATED ALWAYS AS IDENTITY
  当前时间    datetime('now') →  CURRENT_TIMESTAMP / NOW()
  拿插入的 id lastrowid      →  INSERT ... RETURNING id
  标识符      `col`          →  col（小写名不用引号）
"""

import importlib
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

# 项目根：本文件在 core/ 下，往上两级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 复用 core/llm.py 已经加载的 .env（load_dotenv 幂等，再调一次不影响）
load_dotenv(_PROJECT_ROOT / "config" / ".env")

# 默认租户：多租户功能上线前，所有数据都归到这个租户
DEFAULT_TENANT_ID = 1


def _conninfo() -> dict:
    """拼出连接参数。

    为什么返回 dict 而不是 DSN 字符串：
      DSN 是 "key=value key=value" 的格式，value 里如果有空格或反斜杠
      就必须转义，很容易出错（我们的密码里就有反斜杠）。
      直接把 dict 交给 psycopg，它内部会正确转义。
    """
    return {
        "host": os.getenv("PG_HOST", "127.0.0.1"),
        "port": int(os.getenv("PG_PORT", "5432")),
        "dbname": os.getenv("PG_DBNAME", "ctos2"),
        "user": os.getenv("PG_USER", "ctos_app"),
        "password": os.getenv("PG_PASSWORD", ""),
        "connect_timeout": 10,
        "row_factory": dict_row,
    }


@contextmanager
def get_conn():
    """开一个连接，用完自动关；出错自动回滚。

    用法：
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ...")
                rows = cur.fetchall()
    """
    conn = psycopg.connect(**_conninfo())
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction():
    """一个事务：块内全部成功才提交，有异常整体回滚。

    用法：
        with transaction() as cur:
            cur.execute("INSERT ...")
            cur.execute("INSERT ...")
    """
    with get_conn() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                yield cur


def query(sql: str, params: tuple = ()) -> list[dict]:
    """查多条，返回 list[dict]。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """查一条，没有返回 None。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def execute(sql: str, params: tuple = ()) -> int:
    """执行一条写语句，返回影响行数。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount


def execute_returning_id(sql: str, params: tuple = ()) -> int:
    """执行 INSERT，返回新行 id。SQL 里必须带 RETURNING id。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
            return row["id"] if row else 0


def create_all_tables():
    """建好所有表；表已存在就跳过，不动已有数据。

    顺序有讲究：tenants 是全局身份表，users / sessions / trip_* 都外键引用它，
    所以必须最先建（定义在 databases/db_tenant.py）。

    各业务模块的表由各自模块负责：新加模块时，把 (模块路径, 建表函数名)
    加进下面的列表即可。某个模块被删掉时这一项会自动跳过，不影响其他表。
    """
    from databases.db_tenant import create_tenant_tables

    create_tenant_tables()

    module_builders = (
        ("databases.db_chat", "create_chat_tables"),
        ("databases.db_auth", "create_user_tables"),
        ("databases.db_trip", "create_trip_tables"),
    )
    for module_path, func_name in module_builders:
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            print(f"[建表] 跳过 {module_path}：{e}")
            continue
        getattr(module, func_name)()


def check_connection() -> dict:
    """连一下数据库，返回基本信息，用来做启动自检。"""
    row = query_one("SELECT current_database() AS db, current_user AS usr, version() AS ver")
    return row or {}


if __name__ == "__main__":
    info = check_connection()
    print(f"数据库：{info.get('db')}")
    print(f"用户：  {info.get('usr')}")
    print(f"版本：  {str(info.get('ver'))[:60]}")
    print()
    create_all_tables()
    print("建表完成")
