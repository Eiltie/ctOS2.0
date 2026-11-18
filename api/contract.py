"""接口契约：后端单方面声明的「前端能依赖什么」。

================================ 为什么要有这个 ================================
前后端靠字符串字段名耦合（m.content、ev.kind……），没有任何地方声明过。
后端改了字段名，前端要到运行时才崩；新增的 SSE 事件前端直接静默丢弃。
这里把约定写成数据，由 /contract 暴露，前端启动时校验。

怎么用：
  - 后端：新增/修改接口时**同步改这里**，改了这里才算改完
  - 前端：web/scripts/check-api-contract.mjs 和页面类型定义对着它写，CI 里会跑

注意：这个文件是**声明**，不是校验器。
  它不检查代码是否真的这么实现——那是测试的事。
  它的价值在于「有一个唯一的地方写明约定」，两边都对着它看。

================================ 关于这份文件的来历 ================================
仓库里的 api/contract.py 曾经缺失（本机磁盘上没有，只有容器镜像里有一份），
导致 GET /contract 一直 500。这里是按容器里实际运行的那份补回来的，
并补上了两处与真实代码对不上的地方（见下面标 [已修正] 的注释）。
============================================================================
"""

# 前端调用、后端提供的全部接口
# 字段名要和代码里的实际实现一致，改代码时必须同步改这里
API = {
    # ---------- 认证 ----------
    "POST /auth/trial": {
        "desc": "创建一个访客账号，页面首次打开时自动调",
        "response": ["token", "user", "is_trial"],
    },
    "POST /auth/login": {
        "desc": "登录",
        "request": ["email", "password"],
        "response": ["token", "user"],
    },
    "POST /auth/register": {
        "desc": "注册",
        "request": ["email", "password", "display_name"],
        "response": ["token", "user"],
    },
    "GET /auth/me": {
        "desc": "查当前登录用户",
        # [已修正] 原声明里有 is_trial，但 api/routes/auth.py 的 me() 只返回这三项。
        #         访客身份靠 user.email 的 @ctos-trial.local 后缀判断。
        "response": ["id", "email", "display_name"],
    },

    # ---------- 闲聊 ----------
    "POST /chat": {
        "desc": "闲聊 / 角色扮演，流式返回纯文本",
        "request": ["messages", "session_id", "role_id", "image_ids"],
        "response_headers": ["X-Session-Id"],
        "content_type": "text/plain",
    },

    # ---------- 会话 ----------
    "GET /sessions": {
        "desc": "会话列表",
        "response_item": ["id", "title", "created_at", "updated_at", "role_id"],
    },
    "GET /sessions/{id}/messages": {
        "desc": "某个会话的全部消息",
        "response_item": ["role", "content", "images"],
        # role 只能是这两个值
        "enums": {"role": ["user", "assistant"]},
        # images 是图片 id 的数组，取图走 GET /chat/attachment/{image_id}
        "notes": "images 里只有 id，像素内容要另取",
    },
    "DELETE /sessions/{id}": {
        "desc": "删会话",
        "response": ["deleted"],
    },
    "POST /sessions/delete-batch": {
        "desc": "批量删会话",
        "request": ["ids"],
        # deleted 是实际删掉的数量（别人的 / 已删除的不算）
        "response": ["deleted"],
    },

    # ---------- 图片附件 ----------
    "POST /chat/attachment": {
        "desc": "上传图片，返回 image_id",
        "request": ["file(multipart)"],
        "response": ["image_id", "mime", "bytes", "url"],
        # 上限：8 MiB，一次最多 3 张，支持 jpeg/png/gif/webp
    },
    "GET /chat/attachment/{image_id}": {
        "desc": "取图片（需要带 token）",
        "content_type": "image/*",
    },

    # ---------- 角色扮演 ----------
    "GET /roleplay/roles": {
        "desc": "角色列表（预设 + 我的）",
        "response": ["roles"],
        "response_item": ["id", "name", "group", "emoji", "tagline", "opening", "source"],
    },
    "GET /roleplay/roles/{role_id}": {
        "desc": "角色完整档案",
        "response": ["role"],
    },
    "POST /roleplay/roles": {
        "desc": "创建自定义角色",
        "request": [
            "name", "age", "gender", "personality", "deeds",
            "background", "extra", "emoji", "tagline", "speaking", "source",
        ],
        "response": ["role"],
    },
    "DELETE /roleplay/roles/{role_id}": {
        "desc": "删除自定义角色（连同它的聊天和记忆）",
    },
    "POST /roleplay/roles/search": {
        "desc": "AI 帮我查：联网搜资料生成角色草稿（不存库）",
        "request": ["query"],
        "response": ["role", "note"],
    },
    "POST /roleplay/start": {
        "desc": "开始角色聊天",
        "request": ["role_id"],
        "response": ["session_id", "opening", "memory", "role"],
    },
    "GET /roleplay/session/{session_id}": {
        "desc": "查某个会话是哪个角色",
        # [已修正] 原声明漏了 session_id；api/routes/roleplay.py 三个分支都返回它。
        #         role 为 null 表示这是普通闲聊，不是错误。
        "response": ["session_id", "role", "memory"],
    },
    "GET /roleplay/memory/{role_id}": {
        "desc": "查角色记忆",
        "response": ["role_id", "memory"],
    },
    "POST /roleplay/memory/clear": {
        "desc": "清空角色记忆",
        "request": ["role_id"],
    },

    # ---------- 智能出行 ----------
    "POST /trip/chat": {
        "desc": "智能出行唯一入口，SSE 事件流",
        "request": ["query", "history", "chat_id", "image_ids"],
        "content_type": "text/event-stream",
    },
    "POST /trip/route/choose": {
        "desc": "用户在候选方案里选了一条",
        "request": ["thread_id", "choice_id", "chat_id"],
        "content_type": "text/event-stream",
    },
    "POST /trip/route/place": {
        "desc": "用户从地点候选里挑了一个",
        "request": ["thread_id", "place"],
        "content_type": "text/event-stream",
    },
    "POST /guide/spots": {
        "desc": "攻略勾完景点，继续排行程",
        "request": ["thread_id", "removed", "added"],
        "content_type": "text/event-stream",
    },
    "GET /trip/list": {
        "desc": "出行记录列表",
        # [已修正] 原声明漏了 turn_count（db_trip.list_trips 有返回），
        #         前端要用它显示「几轮」。
        "response_item": [
            "id", "title", "created_at", "updated_at", "turn_count", "last_kind",
        ],
        "notes": "last_kind 只代表最后一轮，不代表整个会话",
    },
    "GET /trip/{trip_id}": {
        "desc": "出行记录详情",
        # [已修正] 原声明写的是 {"record": ...}，但 db_trip.get_trip 直接返回
        #         会话本身的字段，外面没有 record 包一层。
        "response": ["id", "title", "created_at", "updated_at", "turns"],
    },
    "DELETE /trip/{trip_id}": {
        "desc": "删一条出行记录",
        "response": ["deleted"],
    },
    "POST /trip/delete-batch": {
        "desc": "批量删出行记录",
        "request": ["ids"],
        "response": ["deleted"],
    },

    # ---------- 客服 ----------
    "POST /customer/chat": {
        "desc": "智能客服，SSE 事件流",
        "request": ["query", "history"],
        "content_type": "text/event-stream",
    },

    # ---------- 其他 ----------
    "GET /notice": {
        "desc": "更新公告",
        "response": ["notice"],
    },
    "POST /feedback": {
        "desc": "提交反馈",
        # 可选的 page / rating / content / contact
        "request": ["page", "rating", "content"],
        "response": ["ok"],
    },
    "POST /presence/ping": {
        "desc": "在线心跳",
        "response": ["ok", "updated"],
    },
    "GET /presence/online": {
        "desc": "在线人数",
        "response": ["online", "window_minutes"],
    },
    "GET /health": {
        "desc": "存活检查",
        "response": ["ok", "database", "user"],
    },
}

# SSE 事件类型。
# 前端没处理到的 kind 会被静默忽略——这里列全，前端对不上的要报警告。
SSE_KINDS = {
    # 通用
    "SAY": "一句进度说明（纯文本气泡）",
    "START": "开始，带 mode 表示走哪个能力",
    "STEP": "进度条上点亮某一步",
    "TOKEN": "逐字输出，带 key 表示这段属于哪一部分",
    "DONE": "某一段写完，带 key 和完整 text",
    "CHAT": "一整段对话式回复，带 chat_id",
    "SAVED": "这一轮已存库，带 chat_id",
    "ERROR": "出错，带 message",

    # 生图（出行侧主动提议之后画出来的图）
    "IMAGE": "AI 生成了一张图，带 image_id（取图走 GET /chat/attachment/{id}）",

    # 需要用户操作的暂停
    "ASK": "让用户从路线候选里选一条",
    "ASK_PLACE": "地点有歧义，让用户选一个",
    "ASK_SPOTS": "攻略的景点清单，让用户勾选",
}

# 出行里，TOKEN/DONE/STEP 的 key 有哪些。
# 来自 modules/trip/route/stream.py 的 ROUTE_STEP_TEXT、
#      modules/trip/guide/stream.py 的 GUIDE_SECTION_KEYS / GUIDE_STEP_TEXT。
SECTION_KEYS = {
    # 路线：确认需求 → 查方案 → 整理推荐 → 出发提醒
    "ROUTE": ["route_need", "route_compare", "route_decision", "route_tips"],
    # 攻略：天气 → 景点 → 行程 → 游玩建议
    "TRAVEL": ["weather", "spots", "itinerary", "advice"],
}

# 每一轮的类型（trip_sessions.turn_kind）
TURN_KINDS = {
    "CHAT": "直接回答",
    "ROUTE": "调了路线子图",
    "TRAVEL": "调了攻略子图",
}

# 反馈里允许的值（databases/modules/db_feedback.py 的 VALID_*）
FEEDBACK_RATINGS = ["很满意", "满意", "一般", "不太满意"]
FEEDBACK_PAGES = ["chat", "trip", "customer", "login", ""]

# /chat 返回的图片里，images 数组中每一项的字段
# （目前前端只用到 id）
IMAGE_FIELDS = ["id", "rel_path", "mime", "byte_size"]

# 契约版本：字段或事件有任何变化就改这个日期。
# 前端 check-api-contract 会打印出来，方便确认两边对着的是同一版。
CONTRACT_VERSION = "2026-11-18"


def contract():
    """给 /contract 接口用：整份契约。"""
    return {
        "version": CONTRACT_VERSION,
        "api": API,
        "sse_kinds": SSE_KINDS,
        "section_keys": SECTION_KEYS,
        "turn_kinds": TURN_KINDS,
        "feedback_ratings": FEEDBACK_RATINGS,
        "feedback_pages": FEEDBACK_PAGES,
        "image_fields": IMAGE_FIELDS,
    }


if __name__ == "__main__":
    # 单独跑这个文件 = 打印当前契约，方便人工核对
    import json

    print(json.dumps(contract(), ensure_ascii=False, indent=2))
