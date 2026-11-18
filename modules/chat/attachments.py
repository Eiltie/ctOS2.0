"""附件（图片）：存盘、记账、转成模型能吃的块数组。

为什么要单独一个文件：
  「图片怎么存」和「图片怎么给模型」是两件事。
  存盘要按租户隔离、要防路径穿越；给模型要拼成 base64 块。
  闲聊和出行都要用同一套，所以放这里，两边都 import 它。

为什么图片不放进 static/：
  static/ 是公开挂载的，任何人猜到路径就能看别人的图。
  所以图片存在 databases/images/ 下，只通过带鉴权的接口对外。

存哪、怎么记账：
  文件    databases/images/{tenant_id}/{会话或随机}/{随机}.{ext}
  数据库  message_images 表，一行一张图，关联到 messages
  消息正文仍然只存纯文字——这样历史回放不用改，老数据不受影响
"""

import base64
import secrets
from pathlib import Path

from core.db import DEFAULT_TENANT_ID

# 图片存放的根目录：core/ 的上一级是项目根，再进 databases/images
IMAGES_ROOT = Path(__file__).resolve().parent.parent.parent / "databases" / "images"

# 单张上限：DeepSeek 允许 32 MiB，但我们自己收图控制在 8 MiB
# （base64 之后体积涨三分之一，留足余量）
MAX_IMAGE_BYTES = 8 * 1024 * 1024

# 一次最多带几张。DeepSeek 允许 600 张，但界面上一张张看有意义的上限是 3 张
MAX_IMAGES_PER_MESSAGE = 3

# 支持的格式：和 DeepSeek 识图支持的一致
SUPPORTED_MIMES = ("image/jpeg", "image/png", "image/gif", "image/webp")


class BadImage(Exception):
    """图片不合格（格式不对、太大）。调用方把它转成 400。"""


def sniff_mime(data: bytes) -> str | None:
    """按文件真实内容判断格式，返回 MIME；不认识返回 None。

    为什么不信扩展名和 Content-Type：
      DeepSeek 按真实内容判断格式。用户把 PNG 改名成 .jpg 再传，
      按扩展名写 MIME 会和服务端的判断对不上，直接 400。
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def ext_of(mime: str) -> str:
    """MIME 换成文件扩展名。"""
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
    }[mime]


def tenant_dir(tenant_id: int) -> Path:
    """某个租户的图片目录。不存在就建。"""
    directory = IMAGES_ROOT / str(int(tenant_id))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_image(data: bytes, tenant_id: int = DEFAULT_TENANT_ID) -> tuple[str, str, int]:
    """校验并保存一张图，返回（相对路径, MIME, 字节数）。

    相对路径形如 "1/ab12cd34ef.png"，不含根目录，存进数据库。
    这样换机器、换挂载点都不用改数据库。
    """
    if not data:
        raise BadImage("图片是空的")

    if len(data) > MAX_IMAGE_BYTES:
        limit_mb = MAX_IMAGE_BYTES / 1024 / 1024
        raise BadImage(f"图片太大了（上限 {limit_mb:.0f} MiB）")

    mime = sniff_mime(data)
    if mime is None:
        raise BadImage("只支持 JPEG / PNG / GIF / WebP 格式的图片")

    # 随机文件名：不用原始文件名，避免中文、空格、路径穿越（../../）
    filename = f"{secrets.token_hex(12)}.{ext_of(mime)}"
    path = tenant_dir(tenant_id) / filename

    with open(path, "wb") as f:
        f.write(data)

    return f"{int(tenant_id)}/{filename}", mime, len(data)


def resolve_path(rel_path: str) -> Path | None:
    """相对路径换成绝对路径；越出图片根目录的返回 None。

    为什么要检查：rel_path 来自数据库，但万一是脏数据（比如被人塞了 "../.."），
    resolve 之后如果跑到 IMAGES_ROOT 外面，就是目录穿越，必须拦。
    """
    root = IMAGES_ROOT.resolve()
    target = (IMAGES_ROOT / rel_path).resolve()

    # target 必须在 root 里面（不能是 root 本身）
    if root not in target.parents:
        return None
    return target


def read_image(rel_path: str) -> tuple[bytes, str] | None:
    """读一张图，返回（字节, MIME）；读不到返回 None。"""
    path = resolve_path(rel_path)
    if path is None or not path.exists():
        return None

    data = path.read_bytes()
    mime = sniff_mime(data) or "application/octet-stream"
    return data, mime


def to_block(rel_path: str) -> dict | None:
    """把一张图变成模型认的 image_url 块；读不到返回 None。

    这个块就是 HumanMessage.content 列表里的一项，
    也是「让模型识图」的全部形式。
    """
    got = read_image(rel_path)
    if got is None:
        return None

    data, mime = got
    b64 = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def blocks_of(rel_paths: list[str]) -> list[dict]:
    """一批图换成一批块，读不到的跳过（不因为一张坏图整条消息失败）。"""
    blocks = []
    for rel_path in rel_paths or []:
        block = to_block(rel_path)
        if block:
            blocks.append(block)
    return blocks


def delete_image(rel_path: str) -> bool:
    """删一张图，成功返回 True。清理用。"""
    path = resolve_path(rel_path)
    if path is None or not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError as e:
        print(f"[附件] 删除失败 {rel_path}：{e}")
        return False
