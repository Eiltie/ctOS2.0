"""旅游攻略路由：景点勾选后继续跑。

攻略的启动不在这里——用户从 /trip/chat 进来，Agent 判断该做攻略后自己调。
这个文件只有"暂停后继续"的接口。
"""

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import sse_headers, tenant_of
from modules.trip.sse import stream_from_thread
from modules.trip.guide.stream import resume_guide

router = APIRouter(prefix="/guide", tags=["旅游攻略"])


class GuideSpotsRequest(BaseModel):
    """攻略暂停在景点清单后，用户勾选的结果。"""
    thread_id: str
    removed: list[str] = []
    added: str = ""


@router.get("/ping")
async def guide_ping():
    """旅游攻略存活检测（不需要登录，给监控用）。"""
    return {"ok": True, "module": "旅游攻略"}


@router.post("/spots")
async def guide_spots(
    req: GuideSpotsRequest,
    authorization: str | None = Header(default=None),
):
    """攻略暂停在景点清单后，用户勾选完，继续排行程、写游玩建议。"""
    tenant_id = tenant_of(authorization)

    async def gen():
        answer = {"removed": req.removed, "added": req.added}
        async for event in stream_from_thread(
            resume_guide(req.thread_id, answer, tenant_id=tenant_id)
        ):
            yield event

    return StreamingResponse(gen(), media_type="text/event-stream", headers=sse_headers())
