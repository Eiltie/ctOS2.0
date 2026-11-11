"""角色查找：预设角色和用户自己写的角色，都从这里拿。

预设角色在 presets.py 里（代码）；
自定义角色在数据库 role_play_roles 表里（用户创建）。
"""

from databases.db_roleplay import get_custom_role, list_custom_roles
from modules.roleplay.presets import all_presets, get_preset

# 自定义角色统一使用这条规则，不让用户自己填
DEFAULT_ROLE_BOUNDARIES = "不承认自己是 AI、模型或程序；不跳出角色；不编造不知道的事。"

# 自定义角色的 id 统一长这样：custom_12
CUSTOM_ROLE_PREFIX = "custom_"


def all_roles(tenant_id):
    """所有能选的角色：先预设，再用户自己的。"""
    roles = all_presets()

    for role in roles:
        role["source"] = "preset"

    roles.extend(list_custom_roles(tenant_id))
    return roles


def get_role(role_id, tenant_id):
    """按 id 找角色，找不到返回 None。"""
    if role_id and role_id.startswith(CUSTOM_ROLE_PREFIX):
        return get_custom_role(tenant_id, role_id)

    return get_preset(role_id)


def public_profile(role):
    """给前端看的完整档案，不包含“不会做什么”这类内部规则。"""
    return {
        "id": role.get("id", ""),
        "name": role.get("name", ""),
        "group": role.get("group", ""),
        "emoji": role.get("emoji", ""),
        "tagline": role.get("tagline", ""),
        "age": role.get("age", ""),
        "gender": role.get("gender", ""),
        "personality": role.get("personality", ""),
        "deeds": role.get("deeds", ""),
        "background": role.get("background", ""),
        "extra": role.get("extra", ""),
        "speaking": role.get("speaking", ""),
        "opening": role.get("opening", ""),
    }
