import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ctOS_chat_graphOn import run_graph
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_stream import trip_stream
from ctOS2_modules.ctOS2_customer_AI.ctOS2_customer_stream import customer_stream
from ctOS2_databases.ctOS2_db_trip import list_trips, get_trip, delete_trip
from ctOS_chat_sessions import (
    resolve_session,
    save_ai_reply,
    load_history,
    save_user_message,
    all_sessions,
    session_messages,
    remove_session,
)

# 后端唯一入口：一个 FastAPI app 装三个模块（闲聊 / 出行 / 客服）
app = FastAPI()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    messages: str
    session_id: int | None = None


class ChatResponse(BaseModel):
    response: str


class TripRequest(BaseModel):
    query: str
    history: list[str] = []
    # 不传 = 新开一个出行会话
    chat_id: int | None = None


class CustomerRequest(BaseModel):
    query: str


@app.post("/chat")
async def chat(req: ChatRequest):
    """闲聊：流式返回纯文本，会话 id 放在响应头 X-Session-Id。"""
    session_id = resolve_session(req.session_id, req.messages)

    async def gen():
        """逐块产出模型回复，全部发完后再把本轮问答写库。"""
        history = load_history(session_id)
        query = history + [HumanMessage(content=req.messages)]
        collection = []

        async for chunks in run_graph(query):
            collection.append(chunks)
            yield chunks

        save_user_message(session_id, req.messages)
        save_ai_reply(session_id, "".join(collection))

    headers = {"X-Session-Id": str(session_id)} if session_id else {}

    return StreamingResponse(gen(), media_type="text/plain", headers=headers)


@app.get("/trip/ping")
async def trip_ping():
    """出行模块存活检测。"""
    return {"ok": True, "module": "智能出行"}


@app.post("/trip/chat")
async def trip_chat(req: TripRequest):
    """把一句话交给出行模块，返回 SSE 事件流。"""
    # 出行链路：分流 → 天气 → 景点 → 行程 → 路线 → 存库
    return StreamingResponse(
        trip_stream(req.query, req.history, chat_id=req.chat_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/trip/list")
async def trip_list():
    """列出最近的出行会话，前端左侧列表用。"""
    return list_trips()


@app.get("/trip/{trip_id}")
async def trip_detail(trip_id: int):
    """取一个出行会话的全部轮次，不存在返回 404。"""
    record = get_trip(trip_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"没有 id 为 {trip_id} 的出行会话")
    return record


@app.delete("/trip/{trip_id}")
async def trip_delete(trip_id: int):
    """删除一个出行会话及其全部轮次。"""
    deleted = delete_trip(trip_id)
    return {"deleted": deleted > 0}


@app.get("/customer/ping")
async def customer_ping():
    """客服模块存活检测。"""
    return {"ok": True, "module": "智能客服"}


@app.post("/customer/chat")
async def customer_chat(req: CustomerRequest):
    """把一个问题交给客服模块，返回 SSE 事件流。"""
    return StreamingResponse(
        customer_stream(req.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/sessions")
async def get_sessions():
    """列出所有闲聊会话。"""
    return all_sessions()


@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: int):
    """取某个会话的全部历史消息，供前端渲染。"""
    return session_messages(session_id)


@app.delete("/sessions/{session_id}")
async def delete_one_session(session_id: int):
    """删除一个会话及其消息。"""
    ok = remove_session(session_id)
    return {"deleted": ok}


@app.get("/", include_in_schema=False)
async def index():
    """返回前端入口页 index.html。"""
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8080)
