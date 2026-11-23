"""建库入口：把 databases/schema.sql 整个跑一遍。

    python -X utf8 -m databases.schema

留这个入口是为了省事，不用为了建表专门去开 psql。
用的是 .sql 文件而不是 Python 字符串列表：建表属于数据库结构，
放在 .sql 里能直接用 psql 打开、改、复制到别的库，
混在 db_*.py 里想找某张表得翻一遍。

schema.sql 里全是 CREATE ... IF NOT EXISTS 和 ADD COLUMN IF NOT EXISTS，
跑在已有数据的库上不会动任何东西，可以放心重复执行。
"""

import sys
from pathlib import Path

from databases.conn import check_connection, get_conn

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def apply_schema(verbose=True):
    """执行 schema.sql。返回执行的语句条数。"""
    sql_text = SCHEMA_PATH.read_text(encoding="utf-8")

    # psycopg 支持一次执行多条语句（无参数时），这里整份交给数据库
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()

    if verbose:
        # 统计一下有多少条 DDL，纯粹给人看个进度
        statements = [
            line for line in sql_text.splitlines()
            if line.strip().upper().startswith(("CREATE", "ALTER", "INSERT"))
        ]
        print(f"已执行 {SCHEMA_PATH.name}（{len(statements)} 条语句）")

    return 0


if __name__ == "__main__":
    info = check_connection()
    print(f"数据库：{info.get('db')}")
    print(f"用户：  {info.get('usr')}")
    print(f"版本：  {str(info.get('ver'))[:60]}")
    print()

    try:
        apply_schema()
    except Exception as e:
        print(f"建库失败：{e}")
        print("检查 .env 里的 PG_* 配置，以及 PostgreSQL 是否启动。")
        sys.exit(1)

    print("建库完成")
