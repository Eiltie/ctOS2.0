"""出行｜旅游攻略图上的暂停节点

做什么：景点清单出来后停下来等用户勾选；用户确认后才排行程。
被谁用：modules/trip/graph.py 注册成节点，modules/trip/stream.py 发事件。
"""

from langgraph.types import interrupt

from modules.trip.state import AgentState


def ask_spots_node(state: AgentState) -> dict:
    """停在这里，把景点清单交给用户过目。"""
    answer = interrupt({
        "question": "这些景点可以吗？可以去掉不想去的，也可以补一个你想去的",
        "spots": state.get("spots", ""),
        "spot_names": state.get("spot_names") or [],
    })

    # 前端正常会传一个字典回来；传歪了就当成“不改，直接排”
    if not isinstance(answer, dict):
        answer = {}

    removed = [str(name) for name in (answer.get("removed") or []) if str(name).strip()]
    added = str(answer.get("added") or "").strip()

    return {
        "removed_spots": removed,
        "added_spot": added,
        "node_path": ["ask_spots"],
    }
