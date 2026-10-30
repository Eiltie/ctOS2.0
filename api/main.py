"""后端唯一入口：一个 FastAPI app 装三个模块（闲聊 / 出行 / 客服）+ 认证。

认证说明：
  除了 /auth/* 和静态资源，所有接口都需要登录。
  登录状态通过请求头 Authorization: Bearer <token> 判断。
  每个请求解析出 tenant_id，传给下层做数据隔离。
"""

from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from api.routes.auth import current_tenant, router as auth_router
from modules.chat.stream import run_graph
from modules.trip.stream import trip_stream
from modules.customer.stream import customer_stream
from databases.db_trip import list_trips, get_trip, delete_trip, delete_trips
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

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 认证路由：/auth/register、/auth/login、/auth/me
app.include_router(auth_router)


class ChatRequest(BaseModel):
    messages: str
    session_id: int | None = None


class TripRequest(BaseModel):
    query: str
    history: list[str] = []
    # 不传 = 新开一个出行会话
    chat_id: int | None = None


class CustomerRequest(BaseModel):
    query: str
    # 最近几轮对话，前端带上，用来理解「那它怎么配」这类追问
    history: list[dict] = []


def tenant_of(authorization: str | None) -> int:
    """从请求头取当前租户；没登录抛 401。

    每个业务接口都调它，这就是多租户隔离的入口。
    """
    return current_tenant(authorization)


@app.post("/chat")
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    """闲聊：流式返回纯文本，会话 id 放在响应头 X-Session-Id。"""
    tenant_id = tenant_of(authorization)

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
    """返回前端入口页 index.html。"""
    return FileResponse(STATIC_DIR / "index.html")


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
