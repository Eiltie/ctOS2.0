"""接口层的共用工具：租户解析、图片校验、SSE 响应头。

为什么单独一个文件：
  这些函数原来长在 api/main.py 里，被几乎所有路由共用。
  路由拆到 api/routes/* 之后，谁都要 import 它们，
  如果还留在 main.py，routes 就得反向 import main ——循环依赖。

  所以独立成 deps.py：main.py 和所有 routes 都只依赖它，它不依赖任何路由。

和 api/routes/auth.py 的分工：
  routes/auth.py 的 current_tenant() 是"认证"本身（解 token、查用户）。
  这里的 tenant_of() 只是给业务路由用的薄壳，语义更直白："我要当前租户"。
"""

from fastapi import HTTPException

from api.routes.auth import current_tenant
from databases.db_chat import get_image
from modules.chat.attachments import MAX_IMAGES_PER_MESSAGE


def tenant_of(authorization: str | None) -> int:
    """从请求头取当前租户；没登录抛 401。

    每个业务接口都调它，这就是多租户隔离的入口。
    """
    return current_tenant(authorization)


def clean_text(value, limit):
    """去掉首尾空格，并限制长度。"""
    return (value or "").strip()[:limit]


def resolve_images(image_ids, tenant_id, session_id=None):
    """把前端传来的图片 id 换成真实的记录。

    只认属于当前租户的图：拿别人的 id 会被过滤掉，不会越权读图。
    返回两项：
        records —— [(image_id, rel_path, mime, size)]，用来认领到消息上
        paths   —— [rel_path]，用来拼成给模型的图片块
    """
    records = []
    seen = set()

    for image_id in (image_ids or [])[:MAX_IMAGES_PER_MESSAGE]:
        try:
            row = get_image(image_id, tenant_id=tenant_id)
        except Exception as e:
            print(f"[附件] 查图片失败 id={image_id}：{e}")
            continue

        # 查不到说明不存在，或者不属于这个租户——两种情况都当没给
        if not row or row["id"] in seen:
            continue

        # 已经被别的消息认领过的图不再重复用，避免一张图挂到多条消息上
        if row.get("message_id") is not None:
            continue

        seen.add(row["id"])
        records.append((row["id"], row["rel_path"], row["mime"], row["byte_size"] or 0))

    return records, [item[1] for item in records]


def sse_headers():
    """SSE 统一响应头。"""
    return {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }


def require_tenant(authorization: str | None) -> int:
    """要求登录但不用返回值的路由用这个。

    客服、角色搜索这类"只要求登录、不落库"的接口调用它，
    免得写 `tenant_of(authorization)` 然后丢掉返回值被 linter 报。
    """
    return tenant_of(authorization)
