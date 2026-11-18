"""生图｜两个工具

工具一 build_prompt(spec)：把结构化规格拼成提示词，并卡死在接口限制内。
工具二 call_seedream(prompt, size)：调火山方舟 Seedream，把图下载到本地。

为什么工具里不做限额：
  限额是"谁能画几张"的业务规则，属于 API 层。
  图只负责"把一张画出来"，不该管钱。

失败不抛异常：
  返回 (None, 原因)，由节点决定怎么告诉用户。
  抛异常会打断整张图，用户只会看到一个 500。
"""

import json
import os
import secrets
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

# 复用项目里已经加载过的 .env（common.llm 加载过一次，这里再调一次没有副作用）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / "config" / ".env")

# ---- 火山方舟配置 ----
ARK_BASE_URL = os.getenv("ARK_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3"

# 模型名必须带日期后缀，这是火山方舟的约定。
# 不带后缀会报 InvalidEndpointOrModel.NotFound，排查起来很费时间。
# 用 4.0：这个模型有新用户免费额度，开发阶段不花钱。
ARK_IMAGE_MODEL = os.getenv("ARK_IMAGE_MODEL") or "doubao-seedream-4-0-20260415"

# 生图接口的提示词硬上限（官方文档：最大输入 1000 字符）
MAX_PROMPT_CHARS = 1000

# 我们自己留的余量：写到 600 字以内，超了按优先级砍
SOFT_PROMPT_CHARS = 600

# 生图较慢（实测 10~20 秒），超时给足
GENERATE_TIMEOUT = 180

# 图片存哪：和用户上传的分开放
GENERATED_ROOT = _PROJECT_ROOT / "databases" / "images" / "generated"

# 允许的尺寸，防止上游拒绝（Seedream 4.0：边长 512~2048，宽高须为 64 的倍数）
ALLOWED_SIZES = {
    "1024x1024", "1280x960", "960x1280",
    "1280x720", "720x1280", "1280x864", "864x1280",
}


def _api_key():
    return os.getenv("SEEDREAM_API_KEY") or os.getenv("ARK_API_KEY") or ""


# ============================================================
# 工具一：规格 -> 提示词
# ============================================================

def build_prompt(spec: dict) -> str:
    """把结构化规格拼成一段提示词，保证不超过接口限制。

    拼的顺序：主体 → 动作 → 场景 → 风格 → 光线 → 图内文字 → 不要出现。
    超长时按这个顺序从**后面**砍：负向词最先砍，主体永远保留。

    去重：拆规格时模型常把「坐在窗台上」和「窗台」都填上，
    直接拼会得到「坐在窗台上，窗台」这种冗余。
    规则：后面一段如果已经被前面某段包含，就跳过。
    """
    if not isinstance(spec, dict):
        return ""

    def field(key):
        return (spec.get(key) or "").strip()

    # 按优先级排好序；主体在最前，砍的时候从尾部砍
    ordered = [
        field("subject"),
        field("action"),
        field("scene"),
        field("style"),
        field("lighting"),
    ]

    parts = []
    for value in ordered:
        if not value:
            continue
        # 已经说过这个意思了（被前面某段包含，或者包含前面某段），跳过
        if any(value in done or done in value for done in parts):
            continue
        parts.append(value)

    text_in_image = field("text_in_image")
    if text_in_image:
        parts.append(f"画面中写着「{text_in_image}」")

    negative = field("negative")
    if negative:
        parts.append(f"不要出现{negative}")

    prompt = "，".join(parts)

    # 超长就从尾部一段段砍（负向词 → 图内文字 → 光线 → 风格）
    while len(prompt) > SOFT_PROMPT_CHARS and len(parts) > 1:
        parts.pop()
        prompt = "，".join(parts)

    # 极端情况：主体本身就超长，硬截断到硬上限
    return prompt[:MAX_PROMPT_CHARS]


def normalize_size(aspect: str) -> str:
    """比例换成尺寸；不认识就返回默认的方图。"""
    from modules.imagegen.state import ASPECT_SIZES, DEFAULT_SIZE

    size = ASPECT_SIZES.get((aspect or "").strip(), DEFAULT_SIZE)
    return size if size in ALLOWED_SIZES else DEFAULT_SIZE


# ============================================================
# 工具二：调 Seedream 生图
# ============================================================

def call_seedream(prompt: str, size: str = "1536x1536") -> tuple[bytes | None, str]:
    """调火山方舟 Seedream 生成一张图，返回（图片字节, 失败原因）。

    成功时第二项是空字符串；失败时第一项是 None，第二项是给人看的原因。

    为什么拿到 URL 要立刻下载：
      接口返回的是 TOS 上的临时链接，有有效期。
      存 URL 不下载，过一会儿就 404 了。
    """
    api_key = _api_key()
    if not api_key:
        return None, "没配置生图 Key（SEEDREAM_API_KEY）"

    prompt = (prompt or "").strip()
    if not prompt:
        return None, "提示词是空的"

    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS]

    if size not in ALLOWED_SIZES:
        size = "1536x1536"

    body = {
        "model": ARK_IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "watermark": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=GENERATE_TIMEOUT) as client:
            response = client.post(
                f"{ARK_BASE_URL}/images/generations",
                headers=headers,
                json=body,
            )

            if response.status_code != 200:
                return None, _explain_error(response)

            data = response.json()
            items = data.get("data") or []
            if not items:
                return None, "接口没返回图片"

            item = items[0]

            # 优先 URL，其次 base64
            if item.get("url"):
                image = client.get(item["url"], follow_redirects=True, timeout=120)
                if image.status_code != 200:
                    return None, f"下载图片失败（HTTP {image.status_code}）"
                content = image.content
            elif item.get("b64_json"):
                import base64
                content = base64.b64decode(item["b64_json"])
            else:
                return None, "接口返回里既没有 url 也没有 b64_json"

            if len(content) < 1024:
                return None, "图片内容太小，可能没生成成功"

            return content, ""

    except httpx.TimeoutException:
        return None, "生图超时了（超过 3 分钟）"
    except Exception as e:
        return None, f"生图出错：{type(e).__name__}: {e}"


def _explain_error(response) -> str:
    """把接口错误翻译成一句人能看懂的话。"""
    text = response.text or ""

    try:
        payload = json.loads(text)
        code = (payload.get("error") or {}).get("code") or ""
    except Exception:
        code = ""

    if "InvalidEndpointOrModel" in code or "does not exist" in text:
        return f"模型名不对或没开通：{ARK_IMAGE_MODEL}"
    if "AuthenticationError" in code or response.status_code == 401:
        return "生图 Key 无效或已过期"
    if "QuotaExceeded" in code or response.status_code == 429:
        return "生图额度用完了或请求太频繁"
    if "Sensitive" in code or "content" in text.lower():
        return "提示词触发了内容审核，换个说法试试"

    return f"生图接口报错（HTTP {response.status_code}）：{text[:120]}"


def save_generated(content: bytes) -> tuple[str, str]:
    """把生成好的图片存到磁盘，返回（绝对路径, 相对路径）。

    文件名随机，不用提示词——提示词里有中文和特殊字符，不适合做文件名。
    """
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)

    ext = "jpg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        ext = "webp"

    name = f"{secrets.token_hex(10)}.{ext}"
    path = GENERATED_ROOT / name

    with open(path, "wb") as f:
        f.write(content)

    rel = f"generated/{name}"
    return str(path), rel


if __name__ == "__main__":
    # 单独跑本文件 = 手工验一次两个工具
    demo_spec = {
        "subject": "一只橘猫",
        "action": "坐在窗台上",
        "scene": "室内",
        "style": "水彩",
        "lighting": "清晨柔光",
        "aspect": "1:1",
        "text_in_image": "",
        "negative": "模糊, 低质量",
    }

    text = build_prompt(demo_spec)
    print(f"提示词（{len(text)} 字）：{text}")
    print(f"尺寸：{normalize_size(demo_spec['aspect'])}")

    print("\n开始生图…")
    start = time.time()
    content, problem = call_seedream(text, normalize_size(demo_spec["aspect"]))
    print(f"耗时 {time.time()-start:.1f}s")

    if content:
        path, rel = save_generated(content)
        print(f"成功：{path}（{len(content)/1024:.1f} KB）")
    else:
        print(f"失败：{problem}")
