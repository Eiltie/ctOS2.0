"""出行流程的 LangGraph 检查点（暂停现场）。

做什么：把"暂停现场存在哪、打不开怎么办、进程里几个实例"收在一处。
被谁用：路线决策（modules/trip/route/graph.py）、旅游攻略（拆分后）。

为什么要有这个文件：
  原来 make_checkpointer() 写在路线决策的图里，攻略要用就得
  `guide_checkpointer = route_checkpointer` 反过来 import 路线模块。
  拆成两个模块之后，两个图都从这里拿，谁也不用 import 谁。

注意：
  - 文件名**不要改**。改掉等于让所有正在暂停中的会话失效。
  - 全进程共用一个 saver：两份连接同时读写同一个 sqlite 文件容易互相锁。
"""

import sqlite3
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

# 检查点文件：刷新页面不影响，服务重启也能接着选。
# 放在单独的子目录里，Docker 部署时挂一个卷进去，容器重建也不会丢暂停中的流程。
CHECKPOINT_PATH = (
    Path(__file__).resolve().parent.parent
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
