"""生图工具：需求 → 提示词 agent → 生图 API → 存盘。

对外只有一个函数 imageProduct()，它是生图的唯一出口。
失败不抛异常，打印原因后返回 None。
"""

import httpx

from common.llm import get_vlm
from modules.chat.attachments import save_image
from modules.generatePrompts.createGraph import create

MODEL = "doubao-seedream-4-0-20260415"


def imageProduct(query: str, image: list = None, tenantId: int = None):
    """一句话需求画一张图，返回（相对路径, MIME, 字节数）；失败返回 None。

    query    画什么
    image    图片块列表（可选，让提示词 agent 看图）
    tenantId 存到哪个租户目录
    """
    image = image or []

    # 1) 提示词 agent
    app = create()

    try:
        result = app.invoke({"requirement": query, "images": image})
    except Exception as e:
        print(f"[生图] 提示词生成失败：{e}")
        return None

    prompt = (result.get("prompt") or "").strip()

    if not prompt:
        print(f"[生图] 提示词生成失败：{result.get('problem') or '没有写出提示词'}")
        return None

    # 2) 生图 API
    try:
        imageRes = get_vlm().images.generate(
            model=MODEL,
            prompt=prompt,
            size="1K",
            response_format="url",
            extra_body={"watermark": False},
        )
    except Exception as e:
        print(f"[生图] 调用失败：{e}")
        return None

    url = imageRes.data[0].url

    # 3) 下载
    try:
        content = httpx.get(url, follow_redirects=True, timeout=120).content
    except Exception as e:
        print(f"[生图] 下载失败：{e}")
        return None

    if len(content) < 1024:
        print("[生图] 图片太小，可能没生成成功")
        return None

    # 4) 存盘
    try:
        from databases.conn import DEFAULT_TENANT_ID

        return save_image(content, tenant_id=tenantId or DEFAULT_TENANT_ID)
    except Exception as e:
        print(f"[生图] 保存失败：{e}")
        return None


if __name__ == "__main__":
    print(imageProduct("画一只橘猫坐在窗台上"))
