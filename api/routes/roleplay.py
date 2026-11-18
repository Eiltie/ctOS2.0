"""角色扮演路由：角色列表 / 新建 / 搜索 / 开始 / 记忆。

角色扮演挂在闲聊下面（插件），会话和消息复用闲聊的表。
这里只负责 HTTP 层：取租户、校验参数、调用模块函数。
"""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.deps import clean_text, tenant_of
from databases.modules.db_roleplay import (
    clear_memory,
    create_custom_role,
    delete_custom_role,
    get_memory,
    get_role_id,
    is_my_session,
    link_role_session,
)
from modules.chat.sessions import resolve_session, save_ai_reply
from modules.chat.roleplay.openings import make_opening, split_opening
from modules.chat.roleplay.presets import public_role
from modules.chat.roleplay.roles import (
    DEFAULT_ROLE_BOUNDARIES,
    all_roles,
    get_role,
    public_profile,
)
from modules.chat.roleplay.search import search_role

router = APIRouter(prefix="/roleplay", tags=["角色扮演"])


class RoleStartRequest(BaseModel):
    role_id: str


class RoleCreateRequest(BaseModel):
    name: str = ""
    age: str = ""
    gender: str = ""
    personality: str = ""
    deeds: str = ""
    background: str = ""
    extra: str = ""
    # 下面三个表单里不显示，AI 生成的草稿会带上
    emoji: str = "🎭"
    tagline: str = ""
    speaking: str = ""
    # custom = 用户自己写的；ai_search = AI 搜资料生成的
    source: str = "custom"


class RoleSearchRequest(BaseModel):
    query: str


class RoleMemoryClearRequest(BaseModel):
    role_id: str


@router.get("/roles")
def roleplay_roles(authorization: str | None = Header(default=None)):
    """列出所有角色：预设 + 用户自己写的。"""
    tenant_id = tenant_of(authorization)
    return {"roles": all_roles(tenant_id)}


@router.get("/roles/{role_id}")
def roleplay_role_detail(role_id: str, authorization: str | None = Header(default=None)):
    """查看一个角色的完整档案，角色聊天里的「查看档案」用。"""
    tenant_id = tenant_of(authorization)
    role = get_role(role_id, tenant_id)
    if role is None:
        raise HTTPException(status_code=404, detail="没有这个角色")

    return {"role": public_profile(role)}


@router.delete("/roles/{role_id}")
def roleplay_delete_role(role_id: str, authorization: str | None = Header(default=None)):
    """删除自己创建的角色；预设角色不能删。"""
    tenant_id = tenant_of(authorization)

    if not role_id.startswith("custom_"):
        raise HTTPException(status_code=400, detail="预设角色不能删除")

    if not delete_custom_role(tenant_id, role_id):
        raise HTTPException(status_code=404, detail="没有这个角色")

    return {"ok": True}


@router.post("/roles/search")
def roleplay_search_role(req: RoleSearchRequest,
                         authorization: str | None = Header(default=None)):
    """AI 帮我查：联网搜资料，生成一份角色草稿（先不存库）。"""
    tenant_of(authorization)

    query = clean_text(req.query, 60)
    if not query:
        raise HTTPException(status_code=400, detail="先说一个角色名或描述")

    try:
        role, note = search_role(query)
    except Exception as e:
        print(f"[角色搜索] 生成失败：{e}")
        raise HTTPException(status_code=500, detail="没能生成角色，换个说法再试")

    return {"role": role, "note": note}


@router.post("/roles")
def roleplay_create_role(req: RoleCreateRequest,
                         authorization: str | None = Header(default=None)):
    """用户自己写一个角色，或者保存 AI 查出来的角色。"""
    tenant_id = tenant_of(authorization)

    name = clean_text(req.name, 20) or "未命名角色"
    age = clean_text(req.age, 20)
    gender = clean_text(req.gender, 10)
    personality = clean_text(req.personality, 200)
    deeds = clean_text(req.deeds, 300)
    background = clean_text(req.background, 300)
    extra = clean_text(req.extra, 300)

    emoji = clean_text(req.emoji, 4) or "🎭"
    tagline = clean_text(req.tagline, 30) or "自己写的角色"
    speaking = clean_text(req.speaking, 200) or "用符合角色身份和性格的方式说话。"
    boundaries = DEFAULT_ROLE_BOUNDARIES
    source = "ai_search" if req.source == "ai_search" else "custom"

    # 用户可以在补充说明里写"开场白：xxx"；没写就让模型说一句
    opening, extra = split_opening(extra)
    if not opening:
        opening = make_opening({
            "name": name,
            "age": age,
            "gender": gender,
            "personality": personality,
            "deeds": deeds,
            "background": background,
            "extra": extra,
        })

    role_number = create_custom_role(
        tenant_id=tenant_id,
        name=name,
        emoji=emoji,
        tagline=tagline,
        age=age,
        gender=gender,
        personality=personality,
        deeds=deeds,
        background=background,
        extra=extra,
        speaking=speaking,
        boundaries=boundaries,
        opening=opening,
        source=source,
    )

    role = get_role(f"custom_{role_number}", tenant_id)
    if role is None:
        raise HTTPException(status_code=500, detail="角色保存失败")

    return {"role": public_role(role)}


@router.post("/start")
def roleplay_start(req: RoleStartRequest, authorization: str | None = Header(default=None)):
    """选一个角色开始：建一个聊天会话，把角色和会话绑起来，存下开场白。"""
    tenant_id = tenant_of(authorization)
    role = get_role(req.role_id, tenant_id)
    if role is None:
        raise HTTPException(status_code=404, detail="没有这个角色")

    session_id = resolve_session(None, role["name"], tenant_id=tenant_id)
    if session_id is None:
        raise HTTPException(status_code=500, detail="创建角色会话失败")

    link_role_session(session_id, tenant_id, role["id"])
    save_ai_reply(session_id, role["opening"], tenant_id=tenant_id)

    return {
        "session_id": session_id,
        "role": public_role(role),
        "opening": role["opening"],
        "memory": get_memory(tenant_id, role["id"]),
    }


@router.get("/session/{session_id}")
def roleplay_session(session_id: int, authorization: str | None = Header(default=None)):
    """查一个会话是哪个角色，刷新页面后前端用它恢复角色。

    普通闲聊不是错误，返回 role: None，前端照常当普通聊天打开。
    """
    tenant_id = tenant_of(authorization)
    role_id = get_role_id(session_id, tenant_id)

    if role_id is None:
        if not is_my_session(session_id, tenant_id):
            raise HTTPException(status_code=404, detail="没有这个会话")
        return {"session_id": session_id, "role": None, "memory": ""}

    role = get_role(role_id, tenant_id)
    if role is None:
        raise HTTPException(status_code=404, detail="这个角色已经不存在了")

    return {
        "session_id": session_id,
        "role": public_role(role),
        "memory": get_memory(tenant_id, role_id),
    }


@router.get("/memory/{role_id}")
def roleplay_memory(role_id: str, authorization: str | None = Header(default=None)):
    """查这个角色记住了什么，前端可以显示"它还记着……"。"""
    tenant_id = tenant_of(authorization)
    if get_role(role_id, tenant_id) is None:
        raise HTTPException(status_code=404, detail="没有这个角色")

    return {"role_id": role_id, "memory": get_memory(tenant_id, role_id)}


@router.post("/memory/clear")
def roleplay_memory_clear(req: RoleMemoryClearRequest,
                          authorization: str | None = Header(default=None)):
    """把这个角色的记忆全部清掉。"""
    tenant_id = tenant_of(authorization)
    if get_role(req.role_id, tenant_id) is None:
        raise HTTPException(status_code=404, detail="没有这个角色")

    clear_memory(tenant_id, req.role_id)
    return {"ok": True}
