"""系统路由：更新公告、健康检查、首页入口页。

这些接口和任何业务模块都无关，属于"服务本身"的东西。
不需要登录，给前端读公告、给监控看健康状态、给浏览器进首页。
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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


@router.get("/health")
async def health():
    """健康检查：不需要登录，给部署平台和监控用。"""
    from core.db import check_connection

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
    """返回前端入口页 index.html。

    入口页只做一件事：读「当前主题」的偏好，然后跳到 /static/themeA/ 或 /static/themeB/。
    真正的页面在那两个目录里，所以这里改它不会影响任何主题的渲染。
    手机端（宽度 < 900px）一律跳 themeA，见 shared/js/common/prefs.js。

    同样加 no-cache：HTML 一旦被 CDN 缓存，改版后用户看到的还是旧页面，
    /static 下面的新脚本也就用不上。
    """
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )
