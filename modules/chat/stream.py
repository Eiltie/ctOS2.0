"""对话模块的对外出口，吐纯文本（不是 SSE）。

顺带处理生图：用户说「帮我画一只橘猫」时，先判断这句话是不是真的要画，
确认后跑一次生图，把图的 id 以 `[IMAGE:123]` 追加在文字流末尾。

用标记而不是结构化事件，是因为 /chat 返回的就是纯文本，加标记不用改接口格式，
前端渲染时识别一下就行。生成的图也登记进 message_images，
和用户上传的图走同一条 GET /chat/attachment/{id} 取，前端不用区分两种图。
"""

import re

from modules.chat.create_graph import create_graph
from modules.chat.image_intent import clean_image_reply, is_image_request
from modules.chat.sessions import text_of

# 对话图的对外出口：ctOS_chat_api 只 import 这里的 run_graph
graph = create_graph()

# 图片标记：前端据此把这一行换成一张图
IMAGE_MARK = "[IMAGE:{image_id}]"


async def run_graph(query, tenant_id=None, session_id=None):
    """按消息流式跑对话图，逐块产出文本，对外唯一入口。

    query：消息列表（history + 这一轮的用户消息），不是一条字符串。
      api/routes/chat.py 传进来的是 list，所以这里要取最后一条的正文。

    tenant_id / session_id：生图时要用。
      tenant_id 决定图存到哪个租户目录、登记在哪条记录上；
      session_id 用来把图挂到这一轮的消息上（前端回放历史时能显示）。

    生图失败不影响正常回复 —— 图没画出来，文字照常给。
    """
    # 这一轮用户说了什么：取最后一条消息的纯文字
    user_text = _last_user_text(query)

    # 先跑完正常对话，边跑边吐字
    collected = []
    async for chunk in graph.astream(
        {"messages": query},
        stream_mode="messages",
    ):
        msg, _meta = chunk
        if msg.content:
            collected.append(msg.content)
            yield msg.content

    # 对话跑完了。如果这句是在让 AI 画图，再补一张
    if not is_image_request(user_text):
        return

    reply_text = "".join(collected)
    image_id = _generate_and_register(
        query=user_text,
        tenant_id=tenant_id,
        session_id=session_id,
        history_reply=reply_text,
    )

    if image_id is None:
        return

    # 追加图片标记。前面如果模型自己写了假图片链接，这里已经清过了
    yield "\n\n" + IMAGE_MARK.format(image_id=image_id)


def _last_user_text(query) -> str:
    """从消息列表里取最后一条用户消息的纯文字。

    为什么单独写一个：
      query 可能是 list[BaseMessage]（正常调用），
      也可能是裸字符串（直接调 run_graph 的测试/调试场景）。
      text_of 对 list 返回空串，直接用会拿到 ''，
      导致判断永远不通过 —— 这个 bug 就是这么来的。
    """
    if isinstance(query, str):
        return query.strip()

    if isinstance(query, (list, tuple)):
        for message in reversed(query):
            # 只要最后一条 human 的
            if getattr(message, "type", "") != "human":
                continue
            return text_of(getattr(message, "content", "")).strip()

    return ""


def _generate_and_register(query, tenant_id, session_id, history_reply=""):
    """跑一次生图，把结果登记进 message_images，返回 image_id。

    生图本身是 tools/imagesproduct 的事，这里只负责：
    拼需求、调用、登记。任何一步失败都返回 None —— 生图是锦上添花，不能拖垮这轮对话。
    """
    if tenant_id is None:
        # 没有租户就没法归档，直接不画
        print("[生图] 缺少 tenant_id，跳过")
        return None

    # 用「用户这句话 + 模型刚才的回复」一起当生图需求：
    # 模型回复里往往补全了细节（「一只橘猫，坐在阳光下的窗台上」），
    # 单看用户那句话信息可能不够。
    need = clean_image_reply(history_reply)
    requirement = f"{query}\n\n{need}" if need else query

    try:
        from tools.imagesproduct import imageProduct

        saved = imageProduct(requirement, tenantId=tenant_id)
    except Exception as e:
        print(f"[生图] 生成失败（不影响这轮对话）：{e}")
        return None

    if not saved:
        return None

    rel_path, mime, byte_size = saved

    return _register_image(rel_path, tenant_id, session_id, mime, byte_size)


# 图片扩展名 → MIME。和 modules/chat/attachments.py 支持的一致
_EXT_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _register_image(rel_path, tenant_id, session_id, mime=None, byte_size=0):
    """把生成的图登记进 message_images，返回 image_id。

    mime / byte_size 由 imageProduct 给出（它是按文件真实内容判的），
    没给才按扩展名兜底。
    """
    try:
        from databases.modules.db_chat import add_message_image

        if not mime:
            ext = rel_path.rsplit(".", 1)[-1].lower()
            mime = _EXT_MIME.get(ext, "image/jpeg")

        return add_message_image(
            None,
            rel_path,
            mime,
            byte_size or 0,
            session_id=session_id,
            tenant_id=tenant_id,
        )
    except Exception as e:
        print(f"[生图] 登记图片失败：{e}")
        return None


def extract_image_ids(text: str) -> list[int]:
    """从一段文字里取出所有 [IMAGE:n] 标记的 id（测试和排查用）。"""
    return [int(m) for m in re.findall(r"\[IMAGE:(\d+)\]", text or "")]
