"""后端唯一入口：建 app、挂静态文件、把所有路由装进来。

原来的 main.py 有 976 行，什么都在里面：路由、请求模型、业务判断、后台线程。
现在按"每个模块一个文件"拆到 api/routes/ 下面，这里只剩装配工作。

职责划分：
    api/deps.py         租户解析、图片校验、SSE 响应头（路由们共用）
    api/routes/*.py     各模块的对外接口
    api/main.py         建 app + 挂静态 + include_router（本文件）

认证说明：
  除了 /auth/* 和静态资源，所有接口都需要登录。
  登录状态通过请求头 Authorization: Bearer <token> 判断。
  每个请求解析出 tenant_id，传给下层做数据隔离。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
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

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


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


# ============================================================================
# 运行统计
# ============================================================================
# 每个请求结束往 logs/stats.jsonl 追加一行，用 scripts/stats_watch.py 看。
# 统计逻辑全在 common/stats.py，这里只负责「什么时候开始、什么时候结束」。
#
# 为什么用中间件而不是在每个路由里加：
#   11 个流式接口 + 十几个普通接口，逐个加重复且容易漏。
#   中间件是唯一入口，加一次全覆盖。
#
# 为什么只统计业务接口：
#   静态文件、健康检查每秒都在跑，混进来会把数据冲淡。
#   所以只记有意义的路径，其余直接放行。
#
# 流式接口的特殊处理：
#   StreamingResponse 在中间件看来「一返回就结束」，
#   实际上数据还在后面慢慢吐。所以流式的结算推迟到生成器真正跑完时。
#   这里把返回的 response.body_iterator 换成一个带 finally 的包装。

import common.stats as stats  # noqa: E402

# 需要统计的路径前缀 → 模块名。
# 顺序有讲究：更具体的放前面（/chat/attachment 要先于 /chat 判断）。
_STATS_PATHS = (
    ("/trip/", "trip"),
    ("/guide/", "trip"),
    ("/customer/", "customer"),
    ("/chat/attachment", "image"),
    ("/chat", "chat"),
    ("/roleplay/", "chat-role"),
    ("/sessions", "chat"),
    ("/feedback", "other"),
    ("/auth/", "auth"),
)

# 这些后缀不算一次业务请求（静态资源、健康检查、契约查询）
_SKIP_SUFFIXES = ("/contract", "/health", "/notice")


def _module_of(path: str) -> str | None:
    """这条路要不要统计；要的话返回模块名。"""
    if any(path.endswith(s) for s in _SKIP_SUFFIXES):
        return None
    if path.startswith("/static"):
        return None

    for prefix, name in _STATS_PATHS:
        if path.startswith(prefix):
            return name
    return None


@app.middleware("http")
async def stats_middleware(request, call_next):
    module = _module_of(request.url.path)

    # 不统计的路径：直接放行，一点开销都不加
    if module is None:
        return await call_next(request)

    record = stats.begin(request.url.path, module)

    try:
        response = await call_next(request)
    except Exception as e:
        # 路由里抛了未捕获的异常（理论上不该有，业务都自己兜了）
        record.mark_error(f"{type(e).__name__}: {e}")
        stats.finish(record)
        raise

    # 流式响应：结算推迟到生成器结束
    #
    # 判断用 duck typing 而不是 isinstance：
    #   中间件里拿到的 response 可能已经被 Starlette 包过一层
    #   （BaseHTTPMiddleware 会给它加一些属性），
    #   isinstance 有时不成立。有 body_iterator 就按流式处理。
    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is not None and hasattr(body_iterator, "__aiter__"):
        original = body_iterator

        async def tracked_body():
            # 关键：在生成器自己的上下文里重新绑定记录。
            #
            # 为什么必须做：
            #   body_iterator 是在 StreamingResponse 里被单独 await 的，
            #   它跑在一个新的任务里，中间件设置好的 contextvars 传不进来。
            #   不重新绑的话，生成器里调模型时 stats.current() 是 None，
            #   token 和工具就全记不上（踩过：接口里 token 一直是 0）。
            token = stats._current.set(record)
            try:
                async for chunk in original:
                    record.touch()
                    yield chunk
            except Exception as e:
                record.mark_error(f"{type(e).__name__}: {e}")
                raise
            finally:
                stats.finish(record)
                # 复原，避免影响后续复用的上下文
                stats._current.reset(token)

        response.body_iterator = tracked_body()
        return response

    # 普通响应：直接结算。
    # 业务错误（4xx/5xx）也算 error —— 那是我们返回的失败结果。
    if response.status_code >= 500:
        record.mark_error(f"HTTP {response.status_code}")
    elif response.status_code >= 400:
        record.mark_error(f"HTTP {response.status_code}")

    stats.finish(record)
    return response


if __name__ == "__main__":
    import os
    import uvicorn

    # 监听地址：
    #   本机开发用 127.0.0.1（只有自己能访问，安全）
    #   容器里必须用 0.0.0.0（否则 Docker 的端口映射转发不进来）
    # 用环境变量 HOST 控制，Dockerfile 里设为 0.0.0.0
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8080"))

    uvicorn.run(app, host=host, port=port)
