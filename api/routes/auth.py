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

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.auth import create_token, decode_token, hash_password, verify_password
from databases.db_auth import (
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
    """查当前登录用户。前端刷新页面时用它判断 token 还有没有效。"""
    user = current_user(authorization)
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
    }
