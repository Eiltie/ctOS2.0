"""后端唯一入口：一个 FastAPI app 装三个模块（闲聊 / 出行 / 客服）+ 认证。

认证说明：
  除了 /auth/* 和静态资源，所有接口都需要登录。
  登录状态通过请求头 Authorization: Bearer <token> 判断。
  每个请求解析出 tenant_id，传给下层做数据隔离。
"""

import asyncio
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from api.routes.auth import current_tenant, router as auth_router
from api.routes.trial import router as trial_router          # 访客账号（可删，见该文件头）
from modules.chat.stream import run_graph
from modules.trip.stream import (
    guide_choose_stream,
    guide_route_stream,
    trip_stream,
)
from modules.trip.route_decision_stream import route_choose_stream
from modules.customer.stream import customer_stream
from modules.roleplay.presets import all_presets, get_preset, public_role
from modules.roleplay.memory import refresh_memory
from modules.roleplay.stream import role_play_stream
from databases.db_trip import list_trips, get_trip, delete_trip, delete_trips
from databases.db_roleplay import (
    add_one_round,
    clear_memory,
    get_memory,
    get_role_id,
    is_my_session,
    link_role_session,
)
from modules.chat.sessions import (
    resolve_session,
    save_ai_reply,
    load_history,
    save_user_message,
    all_sessions,
    session_messages,
    remove_session,
)

app = FastAPI(title="ctOS 2.0")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class NoCacheStaticFiles(StaticFiles):
    """静态文件：每次都让浏览器/CDN 回源确认有没有更新。

    为什么要覆写：
      默认的 StaticFiles 只发 ETag 和 Last-Modified。Cloudflare 会把
      /static/*.css 这类文件缓存 4 小时（max-age=14400），
      结果就是「代码改了、源站是新的，但用户看到的还是旧样式」——
      改完前端上线，界面上却是白底黑字的默认按钮。

    这里显式发 Cache-Control: no-cache：
      - no-cache 不是「不缓存」，而是「用之前必须先问源站」
      - 配合 ETag，没变化时源站回 304，几乎不耗流量，速度不受影响
      - 一旦文件变了，立刻拿到新版本

    代价：每次请求多一次 304 往返。这个项目是给人演示用的，
    新鲜度比这点开销重要得多。
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")

# 认证路由：/auth/register、/auth/login、/auth/me
app.include_router(auth_router)

# 访客账号：POST /auth/trial（页面首次打开时自动创建并登录，免注册）
# 不需要了就删掉这两行 + api/routes/trial.py，其余代码不受影响
app.include_router(trial_router)


class ChatRequest(BaseModel):
    messages: str
    session_id: int | None = None
    # 传了就是角色扮演，不传就是普通闲聊
    role_id: str | None = None


class RoleStartRequest(BaseModel):
    role_id: str


class RoleMemoryClearRequest(BaseModel):
    role_id: str


class TripRequest(BaseModel):
    query: str
    history: list[str] = []
    # 不传 = 新开一个出行会话
    chat_id: int | None = None


class RouteChoiceRequest(BaseModel):
    """路线决策暂停后，用户点了哪个方案。"""
    thread_id: str
    choice_id: str
    chat_id: int | None = None


class GuideSpotsRequest(BaseModel):
    """攻略暂停在景点清单后，用户勾选的结果。"""
    thread_id: str
    removed: list[str] = []
    added: str = ""


class GuideRouteRequest(BaseModel):
    """攻略跑完后，用户要不要按真实路线再查一遍。"""
    thread_id: str
    want_route: bool = True
    query: str = ""
    city: str = ""
    chat_id: int | None = None


def sse_headers():
    """SSE 统一响应头。"""
    return {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }


class CustomerRequest(BaseModel):
    query: str
    # 最近几轮对话，前端带上，用来理解「那它怎么配」这类追问
    history: list[dict] = []


def tenant_of(authorization: str | None) -> int:
    """从请求头取当前租户；没登录抛 401。

    每个业务接口都调它，这就是多租户隔离的入口。
    """
    return current_tenant(authorization)


@app.get("/roleplay/roles")
def roleplay_roles(authorization: str | None = Header(default=None)):
    """列出所有预设角色，前端用来画角色卡片。"""
    tenant_of(authorization)
    return {"roles": all_presets()}


@app.post("/roleplay/start")
def roleplay_start(req: RoleStartRequest, authorization: str | None = Header(default=None)):
    """选一个角色开始：建一个聊天会话，把角色和会话绑起来，存下开场白。"""
    tenant_id = tenant_of(authorization)
    role = get_preset(req.role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="没有这个角色")

    session_id = resolve_session(None, role["name"], tenant_id=tenant_id)
    if session_id is None:
        raise HTTPException(status_code=500, detail="创建角色会话失败")

    link_role_session(session_id, tenant_id, role["id"])
    save_ai_reply(session_id, role["opening"], tenant_id=tenant_id)

    return {
        "session_id": session_id,
        "role": public_role(role),
        "opening": role["opening"],
        "memory": get_memory(tenant_id, role["id"]),
    }


@app.get("/roleplay/session/{session_id}")
def roleplay_session(session_id: int, authorization: str | None = Header(default=None)):
    """查一个会话是哪个角色，刷新页面后前端用它恢复角色。"""
    tenant_id = tenant_of(authorization)
    role_id = get_role_id(session_id, tenant_id)
    if role_id is None:
        raise HTTPException(status_code=404, detail="这个会话不是角色扮演")

    role = get_preset(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="这个角色已经不存在了")

    return {
        "session_id": session_id,
        "role": public_role(role),
        "memory": get_memory(tenant_id, role_id),
    }


@app.get("/roleplay/memory/{role_id}")
def roleplay_memory(role_id: str, authorization: str | None = Header(default=None)):
    """查这个角色记住了什么，前端可以显示“它还记着……”。"""
    tenant_id = tenant_of(authorization)
    if get_preset(role_id) is None:
        raise HTTPException(status_code=404, detail="没有这个角色")

    return {"role_id": role_id, "memory": get_memory(tenant_id, role_id)}


@app.post("/roleplay/memory/clear")
def roleplay_memory_clear(req: RoleMemoryClearRequest,
                          authorization: str | None = Header(default=None)):
    """把这个角色的记忆全部清掉。"""
    tenant_id = tenant_of(authorization)
    if get_preset(req.role_id) is None:
        raise HTTPException(status_code=404, detail="没有这个角色")

    clear_memory(tenant_id, req.role_id)
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    """闲聊：流式返回纯文本，会话 id 放在响应头 X-Session-Id。

    传了 role_id 就是角色扮演，没传就是普通闲聊，两条路共用会话和消息表。
    """
    tenant_id = tenant_of(authorization)

    # ---------- 角色扮演 ----------
    if req.role_id:
        role = get_preset(req.role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="没有这个角色")

        session_id = req.session_id
        if session_id is None:
            # 前端没先调 /roleplay/start，这里补一个会话和开场白
            session_id = resolve_session(None, role["name"], tenant_id=tenant_id)
            if session_id is None:
                raise HTTPException(status_code=500, detail="创建角色会话失败")
            link_role_session(session_id, tenant_id, role["id"])
            save_ai_reply(session_id, role["opening"], tenant_id=tenant_id)
        else:
            linked_role = get_role_id(session_id, tenant_id)
            if linked_role is None:
                if not is_my_session(session_id, tenant_id):
                    raise HTTPException(status_code=404, detail="没有这个会话")
                link_role_session(session_id, tenant_id, role["id"])
            elif linked_role != role["id"]:
                raise HTTPException(status_code=400, detail="这个会话不是这个角色")

        async def role_gen():
            """逐块产出角色的回复，全部发完再写库。"""
            memory = get_memory(tenant_id, role["id"])
            history = load_history(session_id, tenant_id=tenant_id)
            collection = []

            async for chunk in role_play_stream(role, history, req.messages, memory):
                collection.append(chunk)
                yield chunk

            save_user_message(session_id, req.messages, tenant_id=tenant_id)
            save_ai_reply(session_id, "".join(collection), tenant_id=tenant_id)

            # 每聊 6 轮整理一次记忆；放到后台做，不让用户等
            if add_one_round(tenant_id, role["id"]):
                asyncio.create_task(refresh_memory(tenant_id, role["id"], role["name"]))

        headers = {"X-Session-Id": str(session_id)}
        return StreamingResponse(role_gen(), media_type="text/plain", headers=headers)

    # ---------- 普通闲聊 ----------
    session_id = resolve_session(req.session_id, req.messages, tenant_id=tenant_id)

    async def gen():
        """逐块产出模型回复，全部发完后再把本轮问答写库。"""
        history = load_history(session_id, tenant_id=tenant_id)
        query = history + [HumanMessage(content=req.messages)]
        collection = []

        async for chunks in run_graph(query):
            collection.append(chunks)
            yield chunks

        save_user_message(session_id, req.messages, tenant_id=tenant_id)
        save_ai_reply(session_id, "".join(collection), tenant_id=tenant_id)

    headers = {"X-Session-Id": str(session_id)} if session_id else {}

    return StreamingResponse(gen(), media_type="text/plain", headers=headers)


@app.get("/trip/ping")
async def trip_ping():
    """出行模块存活检测（不需要登录，给监控用）。"""
    return {"ok": True, "module": "智能出行"}


@app.post("/trip/chat")
async def trip_chat(req: TripRequest, authorization: str | None = Header(default=None)):
    """把一句话交给出行模块，返回 SSE 事件流。"""
    tenant_id = tenant_of(authorization)

    return StreamingResponse(
        trip_stream(req.query, req.history, chat_id=req.chat_id, tenant_id=tenant_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/trip/route/choose")
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


@app.post("/trip/guide/spots")
async def trip_guide_spots(
    req: GuideSpotsRequest,
    authorization: str | None = Header(default=None),
):
    """攻略暂停在景点清单后，用户勾选完，继续排行程。"""
    tenant_id = tenant_of(authorization)
    answer = {"removed": req.removed, "added": req.added}

    return StreamingResponse(
        guide_choose_stream(req.thread_id, answer, tenant_id=tenant_id),
        media_type="text/event-stream",
        headers=sse_headers(),
    )


@app.post("/trip/guide/route")
async def trip_guide_route(
    req: GuideRouteRequest,
    authorization: str | None = Header(default=None),
):
    """攻略跑完后，按真实路线查行程里的移动，或者直接收尾。"""
    tenant_id = tenant_of(authorization)

    return StreamingResponse(
        guide_route_stream(
            req.thread_id,
            req.want_route,
            req.query,
            req.city,
            chat_id=req.chat_id,
            tenant_id=tenant_id,
        ),
        media_type="text/event-stream",
        headers=sse_headers(),
    )


@app.get("/trip/list")
async def trip_list(authorization: str | None = Header(default=None)):
    """列出本租户最近的出行会话，前端左侧列表用。"""
    return list_trips(tenant_id=tenant_of(authorization))


@app.get("/trip/{trip_id}")
async def trip_detail(trip_id: int, authorization: str | None = Header(default=None)):
    """取一个出行会话的全部轮次，不存在返回 404。"""
    record = get_trip(trip_id, tenant_id=tenant_of(authorization))
    if record is None:
        raise HTTPException(status_code=404, detail=f"没有 id 为 {trip_id} 的出行会话")
    return record


@app.delete("/trip/{trip_id}")
async def trip_delete(trip_id: int, authorization: str | None = Header(default=None)):
    """删除一个出行会话及其全部轮次。"""
    deleted = delete_trip(trip_id, tenant_id=tenant_of(authorization))
    return {"deleted": deleted > 0}


class TripDeleteBatch(BaseModel):
    """批量删除的请求体：要删的会话 id 列表。"""
    ids: list[int] = []


@app.post("/trip/delete-batch")
async def trip_delete_batch(req: TripDeleteBatch, authorization: str | None = Header(default=None)):
    """批量删除出行会话，返回真正删掉的个数。

    用 POST 而不是 DELETE：DELETE 带请求体不规范，
    这里要传一串 id，用 POST 传 JSON 更省事。
    """
    return {"deleted": delete_trips(req.ids, tenant_id=tenant_of(authorization))}


@app.get("/customer/ping")
async def customer_ping():
    """客服模块存活检测（不需要登录，给监控用）。"""
    return {"ok": True, "module": "智能客服"}


@app.post("/customer/chat")
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


@app.get("/sessions")
async def get_sessions(authorization: str | None = Header(default=None)):
    """列出本租户的所有闲聊会话。"""
    return all_sessions(tenant_id=tenant_of(authorization))


@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: int, authorization: str | None = Header(default=None)):
    """取某个会话的全部历史消息，供前端渲染。"""
    return session_messages(session_id, tenant_id=tenant_of(authorization))


@app.delete("/sessions/{session_id}")
async def delete_one_session(session_id: int, authorization: str | None = Header(default=None)):
    """删除一个会话及其消息。"""
    ok = remove_session(session_id, tenant_id=tenant_of(authorization))
    return {"deleted": ok}


@app.get("/health")
async def health():
    """健康检查：不需要登录，给部署平台和监控用。"""
    from core.db import check_connection

    try:
        info = check_connection()
        return {
            "ok": True,
            "database": info.get("db"),
            "user": info.get("usr"),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"数据库连接失败：{e}")


@app.get("/", include_in_schema=False)
async def index():
    """返回前端入口页 index.html。

    同样加 no-cache：HTML 一旦被 CDN 缓存，改版后用户看到的还是旧页面，
    /static 下面的新脚本也就用不上。
    """
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


# ===== 反馈 =====
#
# 独立功能，和三个业务模块没有关系，不碰 modules/ 下的任何代码。
# 不需要了，把这一段整体删掉 + 删 databases/db_feedback.py 和 feedback_view.py 即可。

import time

from fastapi import Request

from databases.db_feedback import VALID_PAGES, VALID_RATINGS, add_feedback


class FeedbackRequest(BaseModel):
    content: str = ""
    contact: str = ""
    rating: str | None = None       # 很满意 / 满意 / 一般 / 不太满意
    page: str = ""                  # chat / trip / customer / login


# 简单的频率限制：同一个 IP 每分钟最多 3 条。
# 存在进程内存里，重启服务就清空 —— 够用了，不值得为此引入 Redis。
_feedback_hits: dict[str, list[float]] = {}
FEEDBACK_LIMIT_PER_MINUTE = 3


def _client_ip(request: Request) -> str:
    """取真实客户端 IP。

    线上走 Cloudflare，request.client.host 拿到的是 Cloudflare 的地址，
    真实 IP 在 CF-Connecting-IP 头里。
    """
    forwarded = request.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded
    return request.client.host if request.client else ""


@app.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    request: Request,
    authorization: str | None = Header(default=None),
):
    """提交反馈。不需要登录，未登录时 tenant_id 记为空。

    刻意不强制登录：万一登录态出问题，也不能让用户提不了反馈。
    """
    # 1. 频率限制
    ip = _client_ip(request)
    now = time.time()
    recent = [t for t in _feedback_hits.get(ip, []) if now - t < 60]
    if len(recent) >= FEEDBACK_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="提交太频繁了，请稍后再试")
    recent.append(now)
    _feedback_hits[ip] = recent

    # 2. 内容校验：评价和内容至少有一个
    content = (req.content or "").strip()[:500]
    contact = (req.contact or "").strip()[:100]
    rating = req.rating if req.rating in VALID_RATINGS else None
    page = req.page if req.page in VALID_PAGES else ""

    if not content and not rating:
        raise HTTPException(status_code=400, detail="请至少选择一个评价或填写反馈内容")

    # 3. 登录了就顺带记下是谁；拿不到也不影响提交
    tenant_id = None
    if authorization:
        try:
            tenant_id = tenant_of(authorization)
        except Exception:
            tenant_id = None

    # 4. 落库
    try:
        add_feedback(
            content=content,
            contact=contact,
            rating=rating,
            page=page,
            tenant_id=tenant_id,
            user_agent=request.headers.get("user-agent", ""),
        )
    except Exception as e:
        print(f"[反馈] 写入失败（不影响其他功能）：{e}")
        raise HTTPException(status_code=500, detail="提交失败，请稍后再试")

    return {"ok": True}


if __name__ == "__main__":
    import os
    import uvicorn

    # 监听地址：
    #   本机开发用 127.0.0.1（只有自己能访问，安全）
    #   容器里必须用 0.0.0.0（否则 Docker 的端口映射转发不进来）
    # 用环境变量 HOST 控制，Dockerfile 里设为 0.0.0.0
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8080"))

    uvicorn.run(app, host=host, port=port)
