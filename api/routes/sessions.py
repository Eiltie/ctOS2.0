"""会话路由：列出 / 读消息 / 删除闲聊会话。

会话是闲聊和角色扮演共用的，所以这条路由不属于任何一个业务模块。
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import tenant_of
from databases.modules.db_roleplay import all_role_session_ids
from modules.chat.sessions import all_sessions, remove_session, session_messages

router = APIRouter(prefix="/sessions", tags=["会话"])


class BatchDeleteRequest(BaseModel):
    """批量删除会话的请求体。"""

    ids: list[int] = []


@router.get("")
async def get_sessions(authorization: str | None = Header(default=None)):
    """列出本租户的所有闲聊会话。

    每条带一个 role_id：是角色会话就有值，普通聊天是 None。
    前端靠它区分两种会话，不用再一个个去问。
    """
    tenant_id = tenant_of(authorization)
    sessions = all_sessions(tenant_id=tenant_id)
    role_ids = all_role_session_ids(tenant_id)

    for item in sessions:
        item["role_id"] = role_ids.get(item["id"])

    return sessions


@router.get("/{session_id}/messages")
async def get_messages(session_id: int, authorization: str | None = Header(default=None)):
    """取某个会话的全部历史消息，供前端渲染。"""
    return session_messages(session_id, tenant_id=tenant_of(authorization))


@router.delete("/{session_id}")
async def delete_one_session(session_id: int, authorization: str | None = Header(default=None)):
    """删除一个会话及其消息。"""
    ok = remove_session(session_id, tenant_id=tenant_of(authorization))
    return {"deleted": ok}


@router.post("/delete-batch")
async def delete_many_sessions(
    req: BatchDeleteRequest,
    authorization: str | None = Header(default=None),
):
    """批量删除会话。

    为什么是 POST 而不是 DELETE：
      DELETE 带请求体不规范（有些代理会丢掉 body），
      出行那边的批量删除也是 POST，两边保持一致。

    返回实际删掉的数量：
      传进来的 id 里可能有别人的、或者已经被删掉的，
      前端据此判断要不要提示「有些没删成」。
    """
    tenant_id = tenant_of(authorization)

    deleted = 0
    for session_id in req.ids:
        try:
            if remove_session(session_id, tenant_id=tenant_id):
                deleted += 1
        except Exception as e:
            # 单个删失败不影响其他的
            print(f"[会话] 删除 {session_id} 失败：{e}")

    return {"deleted": deleted}
