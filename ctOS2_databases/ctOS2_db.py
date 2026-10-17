"""ctOS 2.0 数据库的公共地基：数据库文件位置、开连接、统一建表入口。

所有模块（闲聊 / 出行 / 客服）共用这一个文件，共用一个 .db 文件。

分文件规则（很重要）：
    · open_database() 只能有这一个，不要在别的模块里再写一份
      —— 否则某个模块忘了开外键，就会悄悄出 bug
    · 各个模块自己的表和增删改查，放在各自的文件里：
          ctOS2_db_chat.py   闲聊（sessions / messages）
          （出行的以后加 ctOS2_db_trip.py，客服的加 ctOS2_db_customer.py）
    · 新增模块后，记得把它的建表函数加进下面的 create_all_tables()
"""

import sqlite3
import sys
from pathlib import Path

# 直接运行本文件时（python ctOS2_db.py），项目根目录不在搜索路径里，
# 包路径 ctOS2_databases.xxx 就 import 不到。在这里补一次（被 import 时加的是同一个，重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 数据库文件的完整路径，所有模块共用
DATABASE_FILE = Path(__file__).resolve().parent / "ctOS2_db.db"


def open_database():
    """打开数据库连接，用完要关掉。"""
    database = sqlite3.connect(DATABASE_FILE)

    # SQLite 默认不检查外键，必须每条连接都手动打开
    database.execute("PRAGMA foreign_keys = ON")

    # WAL 模式：写数据库时不会挡住读数据库
    database.execute("PRAGMA journal_mode = WAL")

    # 查出来的每一行可以按列名取值，比如 row["title"]
    database.row_factory = sqlite3.Row

    return database


def create_all_tables():
    """建好所有模块的表。表已存在就跳过，不会动已有数据。

    以后新增模块时，在下面加一行就行。
    """
    from ctOS2_databases.ctOS2_db_chat import create_chat_tables
    from ctOS2_databases.ctOS2_db_trip import create_trip_tables

    create_chat_tables()     # 闲聊：sessions / messages
    create_trip_tables()     # 出行：trip_sessions / trip_user_inputs / trip_ai_outputs


if __name__ == "__main__":
    create_all_tables()
    print(f"建表完成：{DATABASE_FILE}")
