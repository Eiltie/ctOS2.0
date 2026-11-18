"""智能客服路由：/customer/chat，RAG 问答。

客服目前不写库，但仍然要求登录，避免被未授权的人白嫖模型额度。
"""

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import tenant_of
from modules.customer.stream import customer_stream

router = APIRouter(prefix="/customer", tags=["智能客服"])


class CustomerRequest(BaseModel):
    query: str
    # 最近几轮对话，前端带上，用来理解「那它怎么配」这类追问
    history: list[dict] = []


@router.get("/ping")
async def customer_ping():
    """客服模块存活检测（不需要登录，给监控用）。"""
    return {"ok": True, "module": "智能客服"}


@router.post("/chat")
async def customer_chat(req: CustomerRequest, authorization: str | None = Header(default=None)):
    """把一个问题交给客服模块，返回 SSE 事件流。"""
    # 客服目前不写库，但仍然要求登录，避免被未授权的人白嫖模型额度
    tenant_of(authorization)

    return StreamingResponse(
        customer_stream(req.query, req.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
