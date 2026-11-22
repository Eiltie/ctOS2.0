"""系统路由：更新公告、健康检查、首页入口页。

这些接口和任何业务模块都无关，属于"服务本身"的东西。
不需要登录，给前端读公告、给监控看健康状态、给浏览器进首页。
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.contract import contract

router = APIRouter(tags=["系统"])

# 项目根：本文件在 api/routes/ 下，往上三级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

STATIC_DIR = _PROJECT_ROOT / "static"

# 公告内容放在 config/notice.json，改完保存、刷新页面就生效，不用改前端代码
NOTICE_FILE = _PROJECT_ROOT / "config" / "notice.json"


def read_notice():
    """读公告文件；文件不存在或格式不对就返回 None。"""
    try:
        with open(NOTICE_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"[公告] 读取失败：{e}")
        return None

    if not isinstance(data, dict):
        return None

    notice_id = str(data.get("id") or "").strip()
    if not notice_id:
        return None

    items = data.get("items")
    if not isinstance(items, list):
        items = []

    return {
        "id": notice_id,
        "title": str(data.get("title") or "更新公告"),
        "date": str(data.get("date") or ""),
        "version": str(data.get("version") or ""),
        "intro": str(data.get("intro") or ""),
        "items": [str(item) for item in items if str(item).strip()],
    }


@router.get("/notice")
def get_notice():
    """给前端读更新公告；没有公告就返回 null。"""
    return {"notice": read_notice()}


@router.get("/contract")
def get_contract():
    """接口契约：前端启动时拉一次，用来校验字段和事件类型。

    为什么要有这个：
      前后端靠字符串字段名耦合，后端改名字前端要到运行时才崩。
      这里把约定暴露成数据，前端对不上就报警告。

    见 api/contract.py 的说明——它是声明，不是自动校验器。
    """
    return contract()


@router.get("/health")
async def health():
    """健康检查：不需要登录，给部署平台和监控用。"""
    from databases.conn import check_connection

    try:
        info = check_connection()
        return {
            "ok": True,
            "database": info.get("db"),
            "user": info.get("usr"),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"数据库连接失败：{e}")


@router.get("/", include_in_schema=False)
async def index():
    """返回前端入口页。

    前端源码在 web/，构建产物在 static/dist/（npm run build 生成）。
    这里直接返回产物里的 index.html。

    加 no-cache：HTML 一旦被 CDN 缓存，改版后用户看到的还是旧页面，
    引用的还是旧的那批带哈希的脚本。「no-cache」不是不缓存，
    而是用之前必须问一次源站，没变就回 304，几乎不耗流量。

    产物不存在时给一句明确的提示，而不是抛 500 ——
    第一次跑项目时最容易忘记的就是「先构建」这一步。
    """
    return _index_response()


# 前端自己管理的页面路径。
#
# 为什么要这个列表：
#   前端用 history 路由，用户刷新 /chat 时浏览器是真的去请求 /chat 这个地址，
#   而服务器上并没有这个文件。这些路径要交回 index.html，由前端路由接管。
#
# 为什么不干脆写一个「所有未匹配路径都返回 index.html」的兜底：
#   那样任何写错的接口地址都会返回 200 + 一堆 HTML，
#   调用方看到的是「JSON 解析失败」而不是「404 没这个接口」，反而更难查。
#   所以这里只列出前端真实存在的页面，多一个也不加。
SPA_ROUTES = ("chat", "chat/roles", "trip", "customer")


def _index_response():
    """读产物里的 index.html；还没构建时给出明确提示。"""
    dist_index = STATIC_DIR / "dist" / "index.html"

    if not dist_index.is_file():
        raise HTTPException(
            status_code=503,
            detail="前端还没构建。在 web/ 目录下执行：npm install && npm run build",
        )

    return FileResponse(
        dist_index,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@router.get("/{spa_path:path}", include_in_schema=False)
async def spa_page(spa_path: str):
    """前端页面的直接访问 / 刷新。

    只认 SPA_ROUTES 里列出的路径，其余一律 404 ——
    这样接口地址写错时仍然是 404，不会莫名其妙返回一个 HTML 页面。
    """
    if spa_path.rstrip("/") not in SPA_ROUTES:
        raise HTTPException(status_code=404, detail="Not Found")

    return _index_response()
