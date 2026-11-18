"""闲聊路由：/chat（含角色扮演）和 /chat/attachment（图片附件）。

/chat 是闲聊和角色扮演的唯一入口：
  传了 role_id 就是角色扮演，没传就是普通闲聊，两条路共用会话和消息表。
"""

import asyncio

from fastapi import APIRouter, File, Header, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import resolve_images, tenant_of
from databases.db_chat import add_message_image, get_image
from databases.db_roleplay import add_one_round, get_memory, get_role_id, is_my_session, link_role_session
from modules.chat.attachments import (
    MAX_IMAGES_PER_MESSAGE,
    BadImage,
    read_image,
    save_image,
)
from modules.roleplay.memory import refresh_memory
from modules.roleplay.roles import get_role
from modules.roleplay.stream import role_play_stream
from modules.chat.sessions import (
    attach_images,
    build_user_message,
    load_history,
    resolve_session,
    save_ai_reply,
    save_user_message,
)
from modules.chat.stream import run_graph

router = APIRouter(tags=["闲聊"])


class ChatRequest(BaseModel):
    messages: str
    session_id: int | None = None
    # 传了就是角色扮演，不传就是普通闲聊
    role_id: str | None = None
    # 本轮的图片：先调 POST /chat/attachment 上传，拿到 id 再带进来
    image_ids: list[int] = []


@router.post("/chat/attachment")
async def upload_attachment(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
):
    """上传一张图片，返回它的 id。之后发消息时把 id 放进 image_ids。

    和 /chat 拆成两步，是为了让「传图」和「发消息」各自独立：
    用户可以传三张删两张、可以传完再改文字，最后只发一次带 image_ids 的请求。
    """
    tenant_id = tenant_of(authorization)

    data = await file.read()

    try:
        rel_path, mime, byte_size = save_image(data, tenant_id=tenant_id)
    except BadImage as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 先占一条记录，message_id 为空；等真发出消息时再挂上去
    image_id = add_message_image(
        None, rel_path, mime, byte_size, session_id=None, tenant_id=tenant_id,
    )

    return {
        "image_id": image_id,
        "mime": mime,
        "bytes": byte_size,
        "url": f"/chat/attachment/{image_id}",
    }


@router.get("/chat/attachment/{image_id}")
def get_attachment(image_id: int, authorization: str | None = Header(default=None)):
    """取一张图。只给图片所属的租户看，别人拿到 id 也取不到。"""
    tenant_id = tenant_of(authorization)

    row = get_image(image_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="没有这张图")

    got = read_image(row["rel_path"])
    if got is None:
        raise HTTPException(status_code=404, detail="图片文件找不到了")

    data, mime = got
    return Response(content=data, media_type=mime,
                    headers={"Cache-Control": "private, max-age=3600"})


@router.post("/chat")
async def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    """闲聊：流式返回纯文本，会话 id 放在响应头 X-Session-Id。

    传了 role_id 就是角色扮演，没传就是普通闲聊，两条路共用会话和消息表。
    传了 image_ids 就是带图提问：图片会拼进这一轮的用户消息。
    """
    tenant_id = tenant_of(authorization)

    # 先把图片换成真实路径（会校验归属），后面两条路都要用
    image_records, image_paths = resolve_images(req.image_ids, tenant_id)

    # ---------- 角色扮演 ----------
    if req.role_id:
        role = get_role(req.role_id, tenant_id)
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

        # 有图时 content 是块数组，没有图时就是纯文字——build_user_message 内部分两路
        user_message = build_user_message(req.messages, image_paths, tenant_id=tenant_id)
        query = history + [user_message]

        collection = []

        async for chunks in run_graph(query):
            collection.append(chunks)
            yield chunks

        # 正文只存纯文字（图在 message_images 里），历史回放才不会被块数组弄崩
        message_id = save_user_message(session_id, req.messages, tenant_id=tenant_id)
        attach_images(message_id, image_records, session_id=session_id, tenant_id=tenant_id)
        save_ai_reply(session_id, "".join(collection), tenant_id=tenant_id)

    headers = {"X-Session-Id": str(session_id)} if session_id else {}

    return StreamingResponse(gen(), media_type="text/plain", headers=headers)
