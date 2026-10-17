"""ctOS 2.0 后端入口：一个 app 装多个模块。

现有模块：
    /chat            闲聊图（ctOS_chat_graph）—— 流式纯文本
    /trip/chat       智能出行 agent 图（ctOS2_Trip_AI）—— SSE 事件流

两个模块共用一个 FastAPI 应用、一个端口、一套静态资源与会话接口。
出行模块不另立 app，它是 ctOS 的一项能力。
"""

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

# 让 ctOS2_modules 这个包能被 import（项目目前无数据库，没有 ctOS2_databases 目录）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ctOS_chat_graphOn import run_graph

# 出行模块：流式细节全封在 trip_stream 里（它顺带把 config/.env 读进来）
from ctOS2_modules.ctOS2_Trip_AI.ctOS2_Trip_stream import trip_stream

# 客服模块：同样只认这一个入口，图内部什么样这里不需要知道
from ctOS2_modules.ctOS2_customer_AI.ctOS2_customer_stream import customer_stream

# 出行历史：直接读出行库（和闲聊的会话表分开）
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


app = FastAPI()

# 前端静态资源目录：css / js 等文件由这里对外提供
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# 挂载静态目录，让浏览器能直接加载 /static/css/style.css、/static/js/app.js
# 注意：挂载在 /static 前缀下，不会影响 /chat、/sessions、/ 这些已有路由
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ChatRequest(BaseModel):
    messages: str
    session_id: int | None = None


class ChatResponse(BaseModel):
    response: str


# 模块一：闲聊（/chat）—— 流式纯文本，前端按字追加

@app.post("/chat")
async def chat(req: ChatRequest):
    session_id = resolve_session(req.session_id, req.messages)

    async def gen():
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


# 模块二：智能出行（/trip/chat）
#
# 这张图有四段产出（天气 / 景点 / 行程 / 路线）、内部还有 ReAct 循环，

class TripRequest(BaseModel):
    query: str
    history: list[str] = []


@app.get("/trip/ping")
async def trip_ping():
    """出行模块存活检测。"""
    return {"ok": True, "module": "智能出行"}


@app.post("/trip/chat")
async def trip_chat(req: TripRequest):
    """收一句话，返回出行规划的 SSE 事件流。"""
    return StreamingResponse(
        trip_stream(req.query, req.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",   # 流不缓存
            "X-Accel-Buffering": "no",     # 若前面挂 nginx：禁止攒包，逐条转发
        },
    )


# 出行历史（和闲聊的 /sessions 分开，两边的数据结构不一样）
# 一条出行记录 = 一轮规划，带四段产出，不能当闲聊消息渲染。

@app.get("/trip/list")
async def trip_list():
    """列出最近的出行记录，供前端左侧列表使用。"""
    return list_trips()


@app.get("/trip/{trip_id}")
async def trip_detail(trip_id: int):
    """取一轮出行记录的完整内容（含四段产出），供前端点开时恢复卡片。"""
    record = get_trip(trip_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"没有 id 为 {trip_id} 的出行记录")
    return record


@app.delete("/trip/{trip_id}")
async def trip_delete(trip_id: int):
    """删除一轮出行记录（它的用户输入和 AI 输出会被级联一起删掉）。"""
    deleted = delete_trip(trip_id)
    return {"deleted": deleted > 0}


# 模块三：智能客服（/customer/chat）
#
# 和另外两个模块最大的不同：它是一次性问答，不记会话、不带历史。
# 用户问一句、拿一个答案就走，所以请求里只有 query，没有 session_id。

class CustomerRequest(BaseModel):
    query: str


@app.get("/customer/ping")
async def customer_ping():
    """客服模块存活检测。"""
    return {"ok": True, "module": "智能客服"}


@app.post("/customer/chat")
async def customer_chat(req: CustomerRequest):
    """收一个问题，返回客服回答的 SSE 事件流。"""
    return StreamingResponse(
        customer_stream(req.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# 会话接口（两个模块共用）

@app.get("/sessions")
async def get_sessions():
    """列出所有会话，供前端侧边栏使用。"""
    return all_sessions()


@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: int):
    """取某个会话的全部历史消息，供前端点开旧会话时渲染。"""
    return session_messages(session_id)


@app.delete("/sessions/{session_id}")
async def delete_one_session(session_id: int):
    """删除一个会话（连同它的消息一起）。"""
    ok = remove_session(session_id)
    return {"deleted": ok}


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(app, host="127.0.0.1", port=8080)
