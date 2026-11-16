"""判断一句话更像"查路线"还是"做攻略"。

做什么：只在"流程跑不下去"的时候用一下，决定要不要给用户一个转场按钮。
被谁用：modules/trip/capabilities/route/stream.py（走错门去攻略）、
        modules/guide/stream.py（走错门去路线）。

为什么不用模型：
  这个判断错了代价很小（用户不点那个按钮就行），
  而每次多调一次模型是实打实的首字延迟。关键词够用。

两边用同一个规则：只有在"对方信号更强"时才建议转场，
两边都像（比如"去杭州玩3天，从东站到西湖怎么走"）就不转，按当前模式继续问。
"""

# 想玩几天的说法
GUIDE_HINTS = (
    "玩", "旅游", "旅行", "攻略", "行程", "景点", "度假", "逛",
    "吃什么", "住哪", "几天", "好玩", "推荐",
)

# 想知道怎么走的说法
ROUTE_HINTS = (
    "怎么走", "怎么去", "怎么到", "坐什么", "哪条路", "路线",
    "多远", "多久", "堵不堵", "堵吗", "开车", "打车", "地铁", "公交", "步行", "骑车",
)


def looks_like_guide(text):
    """这句更像"想去玩几天"。"""
    text = text or ""
    return any(word in text for word in GUIDE_HINTS)


def looks_like_route(text):
    """这句更像"想知道怎么走"。"""
    text = text or ""
    return any(word in text for word in ROUTE_HINTS)


def suggest_guide(text):
    """在路线模式下，这句该不该建议转去攻略。"""
    return looks_like_guide(text) and not looks_like_route(text)


def suggest_route(text):
    """在攻略模式下，这句该不该建议转去路线。"""
    return looks_like_route(text) and not looks_like_guide(text)
