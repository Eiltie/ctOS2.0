import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATABASE_FILE = Path(__file__).resolve().parent / "ctOS2_db.db"


# 数据库公共地基：文件位置、开连接、统一建表入口

# 分区约定：只有这一个 open_database()，各模块的表和读写在各自文件里
def open_database():
    """打开数据库连接（外键、WAL、按列名取值已设好），用完要关。"""
    database = sqlite3.connect(DATABASE_FILE)

    # SQLite 默认不检查外键，每条连接都得手动打开，否则级联删除静默失效
    database.execute("PRAGMA foreign_keys = ON")

    # WAL：写库时不挡读库
    database.execute("PRAGMA journal_mode = WAL")

    # 查询结果可按列名取值
    database.row_factory = sqlite3.Row

    return database


def create_all_tables():
    """建好所有模块的表；表已存在就跳过，不动已有数据。"""
    # 新模块的建表函数要加进这里，否则用它之前表还不存在
    from ctOS2_databases.ctOS2_db_chat import create_chat_tables
    from ctOS2_databases.ctOS2_db_trip import create_trip_tables

    create_chat_tables()
    create_trip_tables()


if __name__ == "__main__":
    create_all_tables()
    print(f"建表完成：{DATABASE_FILE}")
