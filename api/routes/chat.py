"""闲聊路由：/chat（含角色扮演）和 /chat/attachment（图片附件）。

/chat 是闲聊和角色扮演的唯一入口：
  传了 role_id 就是角色扮演，没传就是普通闲聊，两条路共用会话和消息表。
"""

import asyncio
import re

from fastapi import APIRouter, File, Header, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import resolve_images, tenant_of
from databases.modules.db_chat import add_message_image, claim_image, get_image
from databases.modules.db_roleplay import add_one_round, get_memory, get_role_id, is_my_session, link_role_session
from modules.chat.attachments import (
    MAX_IMAGES_PER_MESSAGE,
    BadImage,
    read_image,
    save_image,
)
from modules.chat.roleplay.memory import refresh_memory
from modules.chat.roleplay.roles import get_role
from modules.chat.roleplay.stream import role_play_stream
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

# 生图标记：[IMAGE:123]。modules/chat/stream.py 在流末尾追加。
_IMAGE_MARK_RE = re.compile(r"\s*\[IMAGE:(\d+)\]\s*")


def split_image_marks(text: str) -> tuple[str, list[int]]:
    """把回复里的 [IMAGE:id] 标记拆出来。

    返回（干净的文字, 图片 id 列表）。

    为什么要拆：
      标记是给前端看的，不能存进数据库正文——否则回放历史时
      用户会看到一行 [IMAGE:42] 这种怪东西。
      图本身靠 message_images 关联到消息上，回放时自然能显示。
    """
    ids = [int(m) for m in _IMAGE_MARK_RE.findall(text or "")]
    cleaned = _IMAGE_MARK_RE.sub("\n", text or "").strip()
    # 连续空行收成一个
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, ids


def attach_generated_images(message_id, image_ids, session_id=None, tenant_id=None):
    """把生成的图认领到 AI 回复这条消息上。

    这些图是 stream.py 先插的空记录（message_id 为空），
    这里 UPDATE 认领，和用户上传图的处理方式一致。
    失败只打印 —— 图挂不上不该让整轮对话失败。
    """
    if not message_id or not image_ids:
        return

    for image_id in image_ids:
        try:
            claim_image(image_id, message_id, session_id=session_id, tenant_id=tenant_id)
        except Exception as e:
            print(f"[生图] 认领图片失败（不影响本轮回复）：{e}")


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

        # 传 tenant_id / session_id：这句是在让 AI 画图时，run_graph 会生图
        # 并在流末尾追加 [IMAGE:id] 标记
        async for chunks in run_graph(query, tenant_id=tenant_id, session_id=session_id):
            collection.append(chunks)
            yield chunks

        raw_reply = "".join(collection)

        # 存库前把图片标记拆出来：
        #   · 标记是给前端的，不该进正文（历史回放会显示成一行怪东西）
        #   · 图本身走 message_images，挂到这条 AI 回复上，回放时能正常显示
        reply_text, image_ids = split_image_marks(raw_reply)

        # 正文只存纯文字（图在 message_images 里），历史回放才不会被块数组弄崩
        message_id = save_user_message(session_id, req.messages, tenant_id=tenant_id)
        attach_images(message_id, image_records, session_id=session_id, tenant_id=tenant_id)

        reply_id = save_ai_reply(session_id, reply_text, tenant_id=tenant_id)

        # 把生成的图挂到 AI 回复上（和用户上传的图走同一套关联）
        if image_ids and reply_id:
            attach_generated_images(reply_id, image_ids, session_id=session_id, tenant_id=tenant_id)

    headers = {"X-Session-Id": str(session_id)} if session_id else {}

    return StreamingResponse(gen(), media_type="text/plain", headers=headers)
