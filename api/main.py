"""接口层的装配文件：建 app、挂静态文件、把所有路由装进来。

职责划分：
    api/main.py         建 app + 挂静态 + include_router（本文件）
    api/deps.py         租户解析、图片校验、SSE 响应头（路由们共用）
    api/security.py     密码哈希 + JWT（只有接口层用）
    api/routes/*.py     各模块的对外接口

启动方式：
    python -X utf8 -m common.main     ← 项目总入口
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes import (
    auth,
    chat,
    customer,
    feedback,
    guide,
    presence,
    roleplay,
    sessions,
    system,
    trial,
    trip,
)

app = FastAPI(title="ctOS 2.0")

STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"


class NoCacheStaticFiles(StaticFiles):
    """静态文件：每次都让浏览器/CDN 回源确认有没有更新。

    为什么要覆写：
      默认的 StaticFiles 只发 ETag 和 Last-Modified。Cloudflare 会把
      /static/*.css 这类文件缓存 4 小时（max-age=14400），
      结果就是「代码改了、源站是新的，但用户看到的还是旧样式」——
      改完前端上线，界面上却是白底黑字的默认按钮。

    这里显式发 Cache-Control: no-cache：
      - no-cache 不是「不缓存」，而是「用之前必须先问源站」
      - 配合 ETag，没变化时源站回 304，几乎不耗流量，速度不受影响
      - 一旦文件变了，立刻拿到新版本

    代价：每次请求多一次 304 往返。这个项目是给人演示用的，
    新鲜度比这点开销重要得多。
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")

# ---------- 认证 ----------
# /auth/register、/auth/login、/auth/me
app.include_router(auth.router)

# 访客账号：POST /auth/trial（页面首次打开时自动创建并登录，免注册）
# 不需要了就删掉这两行 + api/routes/trial.py，其余代码不受影响
app.include_router(trial.router)

# ---------- 业务模块 ----------
app.include_router(chat.router)        # /chat、/chat/attachment
app.include_router(trip.router)        # /trip/*（路线和攻略的启动都走这里）
app.include_router(guide.router)       # /guide/spots（勾完景点继续）
app.include_router(roleplay.router)    # /roleplay/*
app.include_router(customer.router)    # /customer/*
app.include_router(sessions.router)    # /sessions

# ---------- 辅助功能 ----------
app.include_router(presence.router)    # /presence/ping、/presence/online
app.include_router(feedback.router)    # /feedback
app.include_router(system.router)      # /notice、/health、/（首页）


if __name__ == "__main__":
    # 启动入口统一在 common/main.py，这里直接转过去，
    # 免得两份启动代码各改各的。
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from common.main import main

    main()
