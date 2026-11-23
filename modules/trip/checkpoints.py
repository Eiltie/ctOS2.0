"""出行的 LangGraph 检查点，也就是「暂停现场」存在哪、怎么取。

路线和攻略都会在关键处停下来等人操作，各自的图都要用这个。
放在这里而不是写进某一张图里，是为了让两个子图谁也不用 import 谁。

整个进程共用一个 saver。两份连接同时读写同一个 sqlite 文件会互相锁死。
文件名也不要改，改了等于让所有正在暂停中的会话失效。
"""

import sqlite3
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

# 检查点文件：刷新页面不影响，服务重启也能接着选。
# 放在单独的子目录里，别和代码混在一起，也方便备份和清理。
# 本文件在 modules/trip/ 下，往上三层才是项目根。
CHECKPOINT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "databases"
    / "checkpoints"
    / "route_checkpoints.sqlite"
)

# 进程内唯一实例。第一次取的时候建，之后一直复用
_saver = None


def make_checkpointer():
    """优先用文件存；文件打不开就退回内存，至少不影响其他模块。"""
    try:
        CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
        return SqliteSaver(connection)
    except Exception as e:
        print(f"[路线] 检查点文件打不开，改用内存：{e}")
        return MemorySaver()


def get_checkpointer():
    """取全进程共用的检查点实例。"""
    global _saver
    if _saver is None:
        _saver = make_checkpointer()
    return _saver
