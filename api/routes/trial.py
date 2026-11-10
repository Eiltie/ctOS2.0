"""访客账号：免注册进入，自动创建一个临时账号并直接登录。

================================ 关于这个文件 ================================
它是**独立的一块功能**，和主流程解耦。现在的用法是：
  - 打开页面时前端发现没有 token，自动 POST /auth/trial，直接进主界面
  - 登录弹层里的「不登录，直接以访客身份使用」也走这里
访客拿到的是独立租户，聊天记录、出行记录都和真实账号一样隔离，互不可见。

以后不想要了，删掉这个文件，再把下面几处引用一起删掉即可：
  1. api/main.py                 import 那一行 + include_router 那一行
  2. static/js/common/auth.js    guestLogin() / ensureSession() 里的访客分支
  3. static/index.html           「不登录，直接以访客身份使用」按钮
删完之后项目行为和加这个文件之前完全一样，不留任何残渣。

不做的事（刻意简化）：
  - 不做限流：现在注册接口本来也没有，不算新增风险
  - 不做定期清理：访客账号会慢慢堆积，以后真有量了再加一个清理脚本
  - 不改任何现有接口：鉴权、租户隔离全部走原来的逻辑
============================================================================
"""

import secrets

from fastapi import APIRouter

from core.auth import create_token, hash_password
from core.db import DEFAULT_TENANT_ID
from databases.db_auth import create_user, touch_last_login

router = APIRouter(prefix="/auth", tags=["访客账号"])

# 统一邮箱格式：<前缀>_<随机串>@<固定域名>
#
# 为什么要统一：
#   - 一眼能认出哪些是访客账号，以后清理用 LIKE '%@ctos-trial.local' 一句就够
#   - .local 是保留域名，永远不会和真实注册的邮箱撞上
#   - 以后想做统计/管理界面，直接按这个后缀筛
TRIAL_EMAIL_PREFIX = "trial_"
TRIAL_EMAIL_DOMAIN = "@ctos-trial.local"

# 随机串长度（16 位十六进制 = 64 bit），足够避免撞车
TRIAL_ID_LEN = 16

# 显示名：侧栏会显示它，让使用者知道这是个临时访客空间
TRIAL_DISPLAY_NAME = "访客"

# 邮箱撞车时最多重试几次（理论上几乎不会发生，但不能不处理）
MAX_RETRY = 5


def make_trial_email() -> str:
    """生成一个统一格式的测试邮箱，例如 trial_9f3a1c2b7e4d5064@ctos-trial.local"""
    return TRIAL_EMAIL_PREFIX + secrets.token_hex(TRIAL_ID_LEN // 2) + TRIAL_EMAIL_DOMAIN


def create_trial_account() -> dict:
    """创建一个访客账号，返回用户信息。

    复用现有的 create_user()：它会在一个事务里同时建租户和用户，
    所以访客账号和正常注册账号在数据库里长得一模一样，
    后续所有接口（租户隔离、会话读写、出行记录）都不需要特殊处理。
    """
    last_error = None

    for _ in range(MAX_RETRY):
        email = make_trial_email()
        # 密码随机生成、不回传、不记日志 —— 用户靠 token 用，永远用不到密码。
        # 这样即使别人知道这个测试邮箱，也登不进去。
        password_hash = hash_password(secrets.token_urlsafe(24))
        try:
            return create_user(email=email, password_hash=password_hash,
                               display_name=TRIAL_DISPLAY_NAME)
        except Exception as e:
            # 最常见的是邮箱 UNIQUE 冲突，换一个再试
            last_error = e

    raise RuntimeError(f"创建访客账号失败（试了 {MAX_RETRY} 次）：{last_error}")


@router.post("/trial")
def trial_login():
    """获取一个访客账号并登录。

    前端首次打开页面时自动调用；拿到 token 后和正常登录一样使用。
    """
    user = create_trial_account()
    token = create_token(user["id"], user["tenant_id"], user["email"])
    touch_last_login(user["id"])

    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "is_trial": True,
        },
        "is_trial": True,
    }


def count_trial_accounts() -> int:
    """访客账号有多少个。以后要清理时用得上，也可以在运维时查一下。"""
    from core.db import query_one

    row = query_one(
        "SELECT COUNT(*) AS n FROM users WHERE email LIKE %s",
        (f"%{TRIAL_EMAIL_DOMAIN}",),
    )
    return row["n"] if row else 0


if __name__ == "__main__":
    # 单独跑这个文件 = 建一个访客账号看看长什么样
    info = create_trial_account()
    print(f"已创建：{info['email']}（租户 {info['tenant_id']}）")
    print(f"当前访客账号总数：{count_trial_accounts()}")
