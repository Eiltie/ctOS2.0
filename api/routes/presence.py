"""在线人数路由：前端「系统负载」里的「在线用户」。

只新增，不改动任何现有接口；数据库侧只是给 users 补一个 last_seen_at 字段。
"""

import time as _time

from fastapi import APIRouter, Header

from api.deps import tenant_of
from databases.modules.db_auth import count_online, touch_last_seen

router = APIRouter(prefix="/presence", tags=["在线人数"])

# 同一个用户 30 秒内只写一次库，避免频繁 ping 把数据库打满
_presence_last: dict[int, float] = {}
PRESENCE_WRITE_INTERVAL = 30.0


@router.post("/ping")
async def presence_ping(authorization: str | None = Header(default=None)):
    """心跳：告诉后端「我还在」。

    前端每 60 秒调一次。同一个用户 30 秒内的重复心跳直接返回，不写库。
    """
    try:
        tenant_id = tenant_of(authorization)
    except Exception:
        # 没登录 / token 失效：不算在线，但也不报错，免得前端一直重试
        return {"ok": False}

    now = _time.time()
    last = _presence_last.get(tenant_id, 0)
    updated = False
    if now - last >= PRESENCE_WRITE_INTERVAL:
        touch_last_seen(tenant_id)
        _presence_last[tenant_id] = now
        updated = True

    return {"ok": True, "updated": updated}


@router.get("/online")
async def presence_online(minutes: int = 10):
    """最近 N 分钟内有活跃的用户数。不需要登录：只返回一个数字。"""
    minutes = max(1, min(int(minutes or 10), 1440))
    return {"online": count_online(minutes), "window_minutes": minutes}
