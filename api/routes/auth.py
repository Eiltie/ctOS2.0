"""认证路由：注册、登录、查当前用户。

三个接口：
  POST /auth/register   注册（自动创建租户）
  POST /auth/login      登录，返回 token
  GET  /auth/me         查当前登录用户（前端刷新时用它验证 token 还有效）

关于 token 怎么传：
  放在请求头 Authorization: Bearer <token>
  不用 cookie，这样前后端分离部署时不用处理跨域 cookie 问题。
"""

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common.auth import create_token, decode_token, hash_password, verify_password
from databases.modules.db_auth import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    touch_last_login,
)

router = APIRouter(prefix="/auth", tags=["认证"])

# 邮箱简单校验：够用就好，不做 RFC 5322 那种复杂正则
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 密码长度限制
MIN_PASSWORD_LEN = 6
MAX_PASSWORD_LEN = 72       # bcrypt 只看前 72 字节，超了会静默截断


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


def _validate_password(password: str) -> str | None:
    """检查密码规则，不合格返回错误文案，合格返回 None。"""
    if len(password) < MIN_PASSWORD_LEN:
        return f"密码至少要 {MIN_PASSWORD_LEN} 位"
    if len(password) > MAX_PASSWORD_LEN:
        return f"密码不能超过 {MAX_PASSWORD_LEN} 位"
    return None


def current_user(authorization: str | None) -> dict:
    """从 Authorization 头解析出当前用户，解析失败抛 401。

    这是个普通函数不是依赖注入，因为业务路由有的是 SSE 流式响应，
    用 Depends 也行，但显式调用更好读。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")

    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="登录信息无效")

    user = get_user_by_id(user_id)
    if not user:
        # token 有效但用户被删了
        raise HTTPException(status_code=401, detail="账号不存在")

    return user


def current_tenant(authorization: str | None) -> int:
    """取当前租户 id：所有数据查询都用它隔离。

    这是整个多租户的核心：以前这个值是常量 1，
    现在从登录态里取，每个用户看到的是自己的数据。
    """
    return current_user(authorization)["tenant_id"]


@router.post("/register")
def register(req: RegisterRequest):
    """注册新用户：建账号 + 建专属租户，返回 token 直接登录。"""
    email = req.email.strip().lower()

    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不对")

    problem = _validate_password(req.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if get_user_by_email(email):
        raise HTTPException(status_code=400, detail="这个邮箱已经注册过了")

    user = create_user(
        email=email,
        password_hash=hash_password(req.password),
        display_name=req.display_name.strip(),
    )

    token = create_token(user["id"], user["tenant_id"], user["email"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
        },
    }


@router.post("/login")
def login(req: LoginRequest):
    """登录：校验密码，返回 token。"""
    email = req.email.strip().lower()
    user = get_user_by_email(email)

    # 故意不区分「邮箱不存在」和「密码错误」：
    # 区分开的话，攻击者能靠报错文案枚举出哪些邮箱注册过
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码不对")

    touch_last_login(user["id"])
    token = create_token(user["id"], user["tenant_id"], user["email"])

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
        },
    }


@router.get("/me")
def me(authorization: str | None = Header(default=None)):
    """查当前登录用户。前端刷新页面时用它判断 token 还有没有效。

    响应头 X-Token-Refresh 里可能带一个新的 token。
    为什么要这个：
      老版本给访客签的 token 只有 7 天。如果什么都不做，那些人在第 8 天回来时
      token 已经失效，前端会给他们建新账号，旧记录就找不回来了。
      这里在每次校验时检查剩余有效期，快到期就顺手换个新的（滑动续期），
      老用户不用做任何事就能继续用原来的账号。
    """
    user = current_user(authorization)

    refreshed = _maybe_refresh_token(authorization)

    headers = {}
    if refreshed:
        headers["X-Token-Refresh"] = refreshed

    return JSONResponse(
        content={
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
        },
        headers=headers,
    )


# 剩余有效期少于这个天数就续期。
# 选 7 天是因为正式账号本来就只有 7 天有效期，访客要长得多；
# 对访客来说「剩不到 7 天」基本意味着这个人用了一阵子，该换新的了。
REFRESH_THRESHOLD_DAYS = 7


def _maybe_refresh_token(authorization: str | None) -> str | None:
    """token 剩余有效期不多了就签发一个新的；不需要续期返回 None。

    失败一律返回 None —— 续期是锦上添花，不能因为它让 /auth/me 报错。
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.removeprefix("Bearer ").strip()

    try:
        # 这里要看 exp，所以不能用 current_user 的解码（它只返回用户）。
        payload = decode_token(token)
        if not payload:
            return None

        exp = payload.get("exp")
        if not exp:
            return None

        remaining = datetime.fromtimestamp(float(exp), tz=timezone.utc) - datetime.now(timezone.utc)
        if remaining > timedelta(days=REFRESH_THRESHOLD_DAYS):
            return None

        user = get_user_by_id(int(payload["sub"]))
        if not user:
            return None

        return create_token(user["id"], user["tenant_id"], user["email"])
    except Exception as e:
        print(f"[续期] 跳过（不影响本次请求）：{e}")
        return None
