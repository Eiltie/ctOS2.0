"""PostgreSQL 连接和通用操作。

所有增删改查都走这里的 query / execute / transaction，不要另写一份开连接的代码。

每个操作开一个短连接、用完就关，没有用连接池：请求量小，建连只要 1~3 毫秒，
而 psycopg_pool 在 Python 3.14 退出时会报线程清理错误。并发上来了再换。

用 SQLite 时要注意的差异（这张表现在是 PG）：占位符用 %s 不是 ?，
自增主键用 GENERATED ALWAYS AS IDENTITY，拿插入的 id 用 RETURNING id。
"""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

# 项目根：本文件在 core/ 下，往上两级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 复用 core/llm.py 已经加载的 .env（load_dotenv 幂等，再调一次不影响）
load_dotenv(_PROJECT_ROOT / ".env")

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

    建表语句统一在 databases/schema.sql，这里只是转发一下，
    保留这个函数名是给老调用方（和 `python -m databases.schema`）用的。
    真正的入口是 `python -X utf8 -m databases.schema`。
    """
    from databases.schema import apply_schema

    apply_schema()


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
