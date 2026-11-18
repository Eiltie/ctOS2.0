"""智能出行｜生图能力（补充能力，不是主流程）

做什么：路线或攻略跑完后，主动问用户要不要生成一张图；
        用户说要，就把这一轮的内容画成一张图。
被谁用：modules/trip/agent.py（在 route/guide 完成后调用）。

================================ 为什么是「主动问」而不是「用户说才画」 ================================
出行这个模块是**专做出行**的，用户来这里是为了查路线、排行程，不是来画图的。
所以生图不能喧宾夺主：
  · 不在提示词里教 Agent「可以画图」，否则用户随口一句「好看」都可能触发生图
  · 只在**路线或攻略刚做完**这个时机提议 —— 这时候用户手里有完整行程，
    画一张图是真的有用（路线图、行程卡），不是硬塞功能

================================ 图的内容怎么定 ================================
不把整段路线文字丢给生图模型（太长、也画不出来），而是：
  路线 → 一张「路线示意/打卡卡」：起点终点、交通方式、关键地标
  攻略 → 一张「行程海报」：目的地、几天、每天的关键景点

生图模型擅长画氛围和排版，不擅长画精确的路线拓扑。
所以提示词里明确要求「示意」「卡片风」，不要求它画得准 —— 画不准的东西不如不画。
==========================================================================
"""

import re

from common.sse import sse

# 提议图的两种场景
KIND_ROUTE = "route"
KIND_GUIDE = "guide"

# 从路线/攻略的产出里挑出能用来画图的要点，最多取这么多条
MAX_POINTS = 5

# 提议语。短、明确、好拒绝 —— 用户不想要就说「不用」，不该反复问
PROPOSE_TEXT = {
    KIND_ROUTE: "路线安排好了。要不要我生成一张路线示意图，方便你截图带走？",
    KIND_GUIDE: "行程排好了。要不要我生成一张行程海报，方便你发朋友圈或者给同行的人看？",
}


def _clean(text: str, limit: int) -> str:
    """压掉多余空白，截断。"""
    value = re.sub(r"\s+", " ", text or "").strip()
    return value[:limit]


def _lines_of(text: str, limit: int = MAX_POINTS) -> list[str]:
    """从一段产出里取出前几行有内容的，用来当画图的素材。"""
    points = []
    for line in (text or "").splitlines():
        item = _clean(line, 60)
        # 跳过空行、分隔线、纯符号这些
        if not item or len(item) < 4:
            continue
        if set(item) <= set("-—=·•| "):
            continue
        points.append(item)
        if len(points) >= limit:
            break
    return points


def build_route_image_prompt(need_text: str, decision: str, tips: str) -> str:
    """路线场景：把需求 + 推荐 + 提醒拼成一段生图需求。

    为什么要求「示意图/卡片」：
      生图模型画不出真实道路网络，硬要求它画准只会得到一张似是而非的图。
      画成「信息卡」——起点终点、交通方式、关键提示排成一张海报——反而有用。
    """
    need = _clean(need_text, 120)
    points = _lines_of(decision, 3) + _lines_of(tips, 2)
    detail = "；".join(points) if points else ""

    prompt = (
        "一张简洁的出行路线信息卡，扁平插画风格，浅色背景，排版干净。"
        f"主题是：{need}。"
    )
    if detail:
        prompt += f"卡片上体现这些信息：{detail}。"
    prompt += (
        "不要画真实地图，不要出现经纬度和杂乱文字；"
        "用简单的线条、图标和色块表达路线方向和交通方式。"
    )
    return prompt


def build_guide_image_prompt(need_text: str, itinerary: str, spots: str) -> str:
    """攻略场景：把目的地 + 天数 + 每日关键景点拼成生图需求。"""
    need = _clean(need_text, 100)
    days = _lines_of(itinerary, 4)
    spot_names = _lines_of(spots, 3)

    prompt = (
        "一张旅行行程海报，清新明亮的插画风格，适合拍照发朋友圈。"
        f"主题是：{need}。"
    )
    if days:
        prompt += f"画面分区体现这几天的安排：{'；'.join(days)}。"
    elif spot_names:
        prompt += f"画面体现这些景点：{'；'.join(spot_names)}。"
    prompt += (
        "不要写大段文字，不要出现真实人名；"
        "用标志性景物、建筑剪影和天气元素表现每一个目的地。"
    )
    return prompt


def propose(kind: str) -> str:
    """打包「要不要生成一张图」的提议事件。

    复用 CHAT 事件：它就是「Agent 说了一句话」，
    前端不需要为生图提议加新的处理逻辑。
    """
    return sse({
        "kind": "CHAT",
        "message": PROPOSE_TEXT.get(kind, PROPOSE_TEXT[KIND_GUIDE]),
        "chat_id": None,
    })


# 用户表示想要一张图的说法（宽松匹配：短句里出现这些词就是要）
_YES_WORDS = ("要", "好", "可以", "行", "谢谢", "画吧", "来一张", "生成", "做个", "做一张")

# 明显拒绝的说法
_NO_WORDS = ("不用", "不要", "不需要", "算了", "不必", "别画")


def wants_image(text: str) -> bool:
    """判断用户是不是在说「要这张图」。

    只在**刚刚提议过**的时候调用（agent.py 里控制时机），
    所以这里可以宽松一点：短句里出现肯定词就算要。

    为什么不用模型判断：
      这是个二选一的短句判断，关键词够了。
      为它多调一次模型，既慢又花钱。
    """
    content = _clean(text, 40)
    if not content:
        return False

    if any(word in content for word in _NO_WORDS):
        return False

    return any(word in content for word in _YES_WORDS)


def wants_image_now(text: str) -> bool:
    """判断用户是不是**自己开口就要图**（不依赖有没有提议过）。

    比 wants_image 严格：
      「要图片」「画张路线图」「生成一张图」算，
      「好的」「要」这种纯应答不算 —— 那得配合上一轮的提议才算数。

    为什么要区分：
      「好的」单独出现时语义太弱，不该触发生图；
      但用户明确说「要图片」，那就是真的要。
    """
    content = _clean(text, 60)
    if not content:
        return False

    if any(word in content for word in _NO_WORDS):
        return False

    # 必须出现「图」相关的名词，才算是要图
    if not any(word in content for word in ("图", "画", "海报", "插画", "头像")):
        return False

    # 出现画图动作词
    return any(word in content for word in ("要", "画", "生成", "做", "来", "给", "整"))


def build_free_image_prompt(query: str) -> str:
    """用户自己开口要图、但之前没有跑过路线/攻略：按他这句话画。

    这种情况下没有行程素材，只能照原话画。
    在提示词里补一句"出行主题"，让它画出来的东西靠得住。
    """
    content = _clean(query, 200)
    return (
        "一张和出行相关的插画或信息卡，画风干净明亮。"
        f"用户的要求是：{content}。"
        "如果提到具体的地点、路线或行程，用图标和色块表达；"
        "不要画真实地图，不要出现大段文字。"
    )
