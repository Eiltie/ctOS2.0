"""测试的公共准备。

core/auth.py 一 import 就会 load_dotenv 读 config/.env，
而 _secret_key() 在没有 JWT_SECRET_KEY 时会直接 raise。
所以这里在测试进程启动前兜一个假密钥：
  - 保证本地和 CI 都能跑，不依赖 config/.env 存在
  - 不覆盖已有值（本地已配好就沿用，不干扰）
"""

import os

import pytest

# 必须是 32 字节以上，HS256 才不会报警
_TEST_SECRET = "test-only-secret-key-do-not-use-in-production-0123456789"


@pytest.fixture(scope="session", autouse=True)
def _ensure_jwt_secret():
    """没有密钥时补一个只给测试用的。"""
    os.environ.setdefault("JWT_SECRET_KEY", _TEST_SECRET)
    # 有的环境里 setdefault 前 .env 已被读过且留了空值，这里兜一下空串
    if not os.environ.get("JWT_SECRET_KEY"):
        os.environ["JWT_SECRET_KEY"] = _TEST_SECRET
    yield
