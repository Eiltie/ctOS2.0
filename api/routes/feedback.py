"""反馈路由：/feedback，用户提交评价和意见。

独立功能，和三个业务模块没有关系。
不需要了，删掉这个文件 + databases/modules/db_feedback.py + feedback_view.py 即可。
"""

import time

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from api.deps import tenant_of
from databases.modules.db_feedback import VALID_PAGES, VALID_RATINGS, add_feedback

router = APIRouter(tags=["反馈"])


class FeedbackRequest(BaseModel):
    content: str = ""
    contact: str = ""
    rating: str | None = None       # 很满意 / 满意 / 一般 / 不太满意
    page: str = ""                  # chat / trip / customer / login


# 简单的频率限制：同一个 IP 每分钟最多 3 条。
# 存在进程内存里，重启服务就清空 —— 够用了，不值得为此引入 Redis。
_feedback_hits: dict[str, list[float]] = {}
FEEDBACK_LIMIT_PER_MINUTE = 3


def _client_ip(request: Request) -> str:
    """取真实客户端 IP。

    线上走 Cloudflare，request.client.host 拿到的是 Cloudflare 的地址，
    真实 IP 在 CF-Connecting-IP 头里。
    """
    forwarded = request.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded
    return request.client.host if request.client else ""


@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    request: Request,
    authorization: str | None = Header(default=None),
):
    """提交反馈。不需要登录，未登录时 tenant_id 记为空。

    刻意不强制登录：万一登录态出问题，也不能让用户提不了反馈。
    """
    # 1. 频率限制
    ip = _client_ip(request)
    now = time.time()
    recent = [t for t in _feedback_hits.get(ip, []) if now - t < 60]
    if len(recent) >= FEEDBACK_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="提交太频繁了，请稍后再试")
    recent.append(now)
    _feedback_hits[ip] = recent

    # 2. 内容校验：评价和内容至少有一个
    content = (req.content or "").strip()[:500]
    contact = (req.contact or "").strip()[:100]
    rating = req.rating if req.rating in VALID_RATINGS else None
    page = req.page if req.page in VALID_PAGES else ""

    if not content and not rating:
        raise HTTPException(status_code=400, detail="请至少选择一个评价或填写反馈内容")

    # 3. 登录了就顺带记下是谁；拿不到也不影响提交
    tenant_id = None
    if authorization:
        try:
            tenant_id = tenant_of(authorization)
        except Exception:
            tenant_id = None

    # 4. 落库
    try:
        add_feedback(
            content=content,
            contact=contact,
            rating=rating,
            page=page,
            tenant_id=tenant_id,
            user_agent=request.headers.get("user-agent", ""),
        )
    except Exception as e:
        print(f"[反馈] 写入失败（不影响其他功能）：{e}")
        raise HTTPException(status_code=500, detail="提交失败，请稍后再试")

    return {"ok": True}
