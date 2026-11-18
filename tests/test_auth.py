"""认证的确定性逻辑测试。

为什么测这些：
  tenant_id 错了 = 用户 A 看到用户 B 的数据。
  这种事故服务不报错、日志干净，只能靠测试提前拦住。

跑法：
  .\\venv\\Scripts\\python.exe -m pytest tests\\test_auth.py -v
"""

from common.auth import (
    TOKEN_EXPIRE_DAYS,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


# ---------------------------------------------------------------- token

def test_签发的token能解出同一个人和同一个租户():
    token = create_token(user_id=7, tenant_id=42, email="a@b.com")
    payload = decode_token(token)

    assert payload is not None
    # sub 按 JWT 规范存成字符串，用之前要转 int
    assert int(payload["sub"]) == 7
    # 这一条是多租户的命门：错了就是串号
    assert payload["tenant_id"] == 42
    assert payload["email"] == "a@b.com"


def test_不同用户不会互相解出对方的租户():
    token_a = create_token(user_id=1, tenant_id=100, email="a@b.com")
    token_b = create_token(user_id=2, tenant_id=200, email="c@d.com")

    assert decode_token(token_a)["tenant_id"] == 100
    assert decode_token(token_b)["tenant_id"] == 200


def test_token里带过期时间且约等于7天后():
    token = create_token(1, 1, "a@b.com")
    payload = decode_token(token)

    assert payload["exp"] - payload["iat"] == TOKEN_EXPIRE_DAYS * 24 * 3600


def test_被篡改的token必须解析失败():
    token = create_token(7, 42, "a@b.com")
    # 改掉签名最后几个字符，模拟有人想伪造
    assert decode_token(token[:-3] + "xxx") is None


def test_乱码token返回None而不是抛异常():
    """decode_token 的约定：任何坏输入都返回 None，调用方靠它判空。"""
    assert decode_token("") is None
    assert decode_token("not-a-jwt") is None
    assert decode_token("a.b.c") is None


# ---------------------------------------------------------------- 密码

def test_密码不会以明文形式存储():
    h = hash_password("secret123")

    assert h != "secret123"
    assert "secret123" not in h
    # bcrypt 的固定前缀，换算法时这里会先炸
    assert h.startswith("$2b$")


def test_正确密码校验通过错误密码不通过():
    h = hash_password("secret123")

    assert verify_password("secret123", h) is True
    assert verify_password("secret124", h) is False
    assert verify_password("", h) is False


def test_同一个密码两次哈希结果不同():
    """bcrypt 自带随机盐，不然两个同密码用户能互相看出密码一样。"""
    assert hash_password("secret123") != hash_password("secret123")


def test_库里存了空串或坏值时校验返回False不崩溃():
    """
    历史数据里 password_hash 可能是空串或不是 bcrypt 格式。
    这种行必须当作"校验失败"，不能把登录接口打成 500。
    """
    assert verify_password("secret123", "") is False
    assert verify_password("secret123", "plain-text-not-a-hash") is False
