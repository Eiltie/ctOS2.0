"""生图｜图的状态

做什么：声明生图图里流转的字段。
被谁用：modules/imagegen/graph.py、node.py、stream.py。

设计要点：
  - spec 是「结构化规格」，不是一段提示词。
    用户能看、能改；迭代时只改字段，不用重写整段话。
  - asked_once 必须存在：需求不足时停下来问一次，
    问过还不足就直接按随机主题画，否则会反复追问卡死。
  - status 决定调用方怎么处理结果，不要靠猜字段有没有值。
"""

from typing import NotRequired, TypedDict


class ImageSpec(TypedDict, total=False):
    """一张图要画什么。字段都可空，空着由模型补或走默认。"""

    subject: str        # 主体：一只橘猫
    action: str         # 动作：坐在窗台上
    scene: str          # 场景：室内 / 雨夜街头
    style: str          # 风格：水彩 / 赛博朋克 / 写实
    lighting: str       # 光线：清晨柔光
    aspect: str         # 比例：1:1 / 16:9 / 9:16 / 4:3 / 3:4
    text_in_image: str  # 图里要写的字（空 = 不写字）
    negative: str       # 不想要的东西


class ImageState(TypedDict):
    # ---- 进来就有的 ----
    user_query: str
    history: NotRequired[list]     # 用户之前说过的话，纯文字
    tenant_id: NotRequired[int]

    # ---- plan 填的 ----
    spec: NotRequired[ImageSpec]
    final_prompt: NotRequired[str]  # 压到接口限制内的最终提示词
    size: NotRequired[str]          # 1536x1536 这类尺寸
    missing: NotRequired[list]      # 还差哪些信息；空 = 够了

    # ---- ask 用的 ----
    asked_once: NotRequired[bool]
    answer: NotRequired[str]        # 用户对提问的回答

    # ---- generate 填的 ----
    image_path: NotRequired[str]    # 存到磁盘后的绝对路径
    image_url: NotRequired[str]     # 给前端看的相对地址
    status: NotRequired[str]        # ok / need_more / api_failed / prompt_failed
    problem: NotRequired[str]       # 失败原因，给人看的

    node_path: NotRequired[list]


# status 的取值，调用方按这个分支
STATUS_OK = "ok"
STATUS_NEED_MORE = "need_more"       # 停下来问用户了（图会中断）
STATUS_PROMPT_FAILED = "prompt_failed"
STATUS_API_FAILED = "api_failed"

# 比例 -> 尺寸。
# 用 Seedream 4.0：常用档位是 1024 这一档，宽高都要是 64 的倍数，
# 边长范围 512~2048。这里的尺寸都在这个范围内。
ASPECT_SIZES = {
    "1:1": "1024x1024",
    "4:3": "1280x960",
    "3:4": "960x1280",
    "16:9": "1280x720",
    "9:16": "720x1280",
    "3:2": "1280x864",
    "2:3": "864x1280",
}

DEFAULT_ASPECT = "1:1"
DEFAULT_SIZE = ASPECT_SIZES[DEFAULT_ASPECT]
