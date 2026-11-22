"""智能出行路由：唯一的入口 /trip/chat，加上路线选择、地点选择、会话管理。

出行只有一个入口：用户说一句话，Agent 判断该自己答、走路线、还是做攻略。
路线和攻略都是它内部的能力，用户不需要（也没法）选。
"""

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import resolve_images, sse_headers, tenant_of
from modules.trip.sse import stream_from_thread
from databases.modules.db_trip import delete_trip, delete_trips, get_trip, list_trips
from modules.chat.sessions import build_user_message
from modules.trip.route.stream import resume_with_place, route_choose_stream
from modules.trip.stream import trip_stream

router = APIRouter(prefix="/trip", tags=["智能出行"])


class TripRequest(BaseModel):
    query: str
    history: list[str] = []
    # 不传 = 新开一个出行会话
    chat_id: int | None = None
    # 本轮的图片，和 /chat 一样先上传拿 id
    image_ids: list[int] = []


class RouteChoiceRequest(BaseModel):
    """路线决策暂停后，用户点了哪个方案。"""
    thread_id: str
    choice_id: str
    chat_id: int | None = None


class PlaceChoiceRequest(BaseModel):
    """地点没认准、用户从候选里挑了一个。"""
    thread_id: str
    place: str


class TripDeleteBatch(BaseModel):
    """批量删除的请求体：要删的会话 id 列表。"""
    ids: list[int] = []


@router.get("/ping")
async def trip_ping():
    """出行模块存活检测（不需要登录，给监控用）。"""
    return {"ok": True, "module": "智能出行"}


@router.post("/chat")
async def trip_chat(req: TripRequest, authorization: str | None = Header(default=None)):
    """智能出行的唯一入口：一句话进来，Agent 判断该干嘛。

    路线规划、旅游攻略都是它内部的能力，用户不需要（也没法）选。
    带 image_ids 时，图片会让 Agent 看到，它据此决定 action 和写出的需求。
    """
    tenant_id = tenant_of(authorization)

    # 出行这边只把图交给 Agent 判断，不落库到闲聊的消息表
    _, image_paths = resolve_images(req.image_ids, tenant_id)

    # 有图就把这一轮用户消息做成块数组，没有图就保持纯文字（老行为）
    user_content = build_user_message(req.query, image_paths, tenant_id=tenant_id).content

    return StreamingResponse(
        trip_stream(req.query, req.history, chat_id=req.chat_id, tenant_id=tenant_id,
                    user_content=user_content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/route/choose")
async def trip_route_choose(
    req: RouteChoiceRequest,
    authorization: str | None = Header(default=None),
):
    """路线决策暂停后，用户选完方案，继续把对比、推荐、提醒写完。"""
    tenant_id = tenant_of(authorization)

    return StreamingResponse(
        route_choose_stream(
            req.thread_id,
            req.choice_id,
            chat_id=req.chat_id,
            tenant_id=tenant_id,
        ),
        media_type="text/event-stream",
        headers=sse_headers(),
    )


@router.post("/route/place")
async def trip_route_place(
    req: PlaceChoiceRequest,
    authorization: str | None = Header(default=None),
):
    """地点没认准、用户从候选里挑了一个之后，从原来那份需求接着查。

    和 /trip/chat 的区别：不重新解析、不重新判断。
    用户点的就是哪个地点，就用哪个地点继续。
    """
    tenant_id = tenant_of(authorization)

    async def gen():
        async for event in stream_from_thread(
            resume_with_place(req.thread_id, req.place, tenant_id=tenant_id)
        ):
            yield event

    return StreamingResponse(gen(), media_type="text/event-stream", headers=sse_headers())


@router.get("/list")
async def trip_list(authorization: str | None = Header(default=None)):
    """列出本租户最近的出行会话，前端左侧列表用。"""
    return list_trips(tenant_id=tenant_of(authorization))


@router.get("/{trip_id}")
async def trip_detail(trip_id: int, authorization: str | None = Header(default=None)):
    """取一个出行会话的全部轮次，不存在返回 404。"""
    record = get_trip(trip_id, tenant_id=tenant_of(authorization))
    if record is None:
        raise HTTPException(status_code=404, detail=f"没有 id 为 {trip_id} 的出行会话")
    return record


@router.delete("/{trip_id}")
async def trip_delete(trip_id: int, authorization: str | None = Header(default=None)):
    """删除一个出行会话及其全部轮次。"""
    deleted = delete_trip(trip_id, tenant_id=tenant_of(authorization))
    return {"deleted": deleted > 0}


@router.post("/delete-batch")
async def trip_delete_batch(req: TripDeleteBatch, authorization: str | None = Header(default=None)):
    """批量删除出行会话，返回真正删掉的个数。

    用 POST 而不是 DELETE：DELETE 带请求体不规范，
    这里要传一串 id，用 POST 传 JSON 更省事。
    """
    return {"deleted": delete_trips(req.ids, tenant_id=tenant_of(authorization))}
