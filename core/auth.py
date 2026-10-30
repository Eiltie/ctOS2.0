"""认证相关的底层工具：密码哈希、JWT 签发与校验。

三个核心概念：
  密码哈希  用户密码绝不存明文，只存 bcrypt 哈希（不可逆）
  JWT       登录成功后发一个签名 token，之后每个请求带上它
  tenant_id 从 token 里解出来的租户 id，所有数据查询靠它隔离
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from jose import JWTError, jwt

# 项目根：本文件在 core/ 下，往上两级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(_PROJECT_ROOT / "config" / ".env")

# JWT 签名算法
ALGORITHM = "HS256"

# token 有效期：7 天。最小可用阶段先设长一点，省得天天重新登录。
# 正式上线前应该改成短 token + refresh token。
TOKEN_EXPIRE_DAYS = 7

# bcrypt 的代价因子。12 是当前推荐值，越大越慢越安全。
# 每加 1 计算时间翻倍，12 大约 200 毫秒，对登录体验影响很小。
BCRYPT_ROUNDS = 12


def _secret_key() -> str:
    """取 JWT 签名密钥。

    这个值泄漏 = 任何人能伪造任意用户的登录，所以缺失时直接报错，
    绝不会退回一个默认值。
    """
    key = os.getenv("JWT_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "config/.env 里没有 JWT_SECRET_KEY。\n"
            "生成一个：python -c \"import secrets; print(secrets.token_urlsafe(48))\"\n"
            "然后加到 config/.env：JWT_SECRET_KEY=<那个值>"
        )
    return key


# ---------------------------------------------------------------- 密码

def hash_password(password: str) -> str:
    """把明文密码变成哈希，存进数据库的就是这个。"""
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码，不对返回 False（不抛异常）。"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # 哈希格式不对（比如库里存的是空串），当作校验失败
        return False


# ---------------------------------------------------------------- JWT

def create_token(user_id: int, tenant_id: int, email: str) -> str:
    """签发登录 token。里面只放身份标识，不放密码等敏感信息。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),        # 用户 id（JWT 规范要求 sub 是字符串）
        "tenant_id": tenant_id,     # 关键：所有数据查询都用它隔离
        "email": email,
        "iat": now,                 # 签发时间
        "exp": now + timedelta(days=TOKEN_EXPIRE_DAYS),   # 过期时间
    }
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """校验并解析 token；过期、签名不对、格式错都返回 None。"""
    try:
        return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
    except JWTError:
        return None


def new_secret_key() -> str:
    """生成一个新的随机密钥，写配置时用。"""
    return secrets.token_urlsafe(48)
