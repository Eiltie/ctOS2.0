"""闲聊｜生图意图判断

做什么：判断用户这句话是不是「让我画一张图」，是的话就去生图。
被谁用：modules/chat/stream.py 的 run_graph。

为什么不做成图里的一个节点：
  生图是一个外部调用（十几秒、要花钱），塞进 LangGraph 的状态流转里
  会和流式输出纠缠不清。判断 + 调用放在这一层更直白。

触发条件（两个都要满足，避免误触）：
  1. 文字里出现了画图的词（画、生成图、图片、插图……）
  2. 模型确认这确实是「要一张图」，而不是在讨论「画画」这件事

为什么不只看关键词：
  「我很喜欢画画」不该触发生图，
  「帮我画一只橘猫」才该。所以关键词先筛一次，模型再判一次，
  两层都过才花钱调生图接口。
"""

import re

from langchain_core.messages import HumanMessage

from common.llm import get_llm
from modules.chat.sessions import text_of

# 第一层：关键词。粗略筛一下，避免每句话都去问模型
#
# 为什么用正则而不是一串固定短语：
#   一开始写的是"画一""画个""生成一张"这种固定搭配，
#   结果用户说"生成一只柴犬"—— 量词是"只"，不是"张"，直接漏了。
#   中文里「画/生成/做/来/给我」后面能接的量词太多了
#   （一张、一只、一个、一幅、一份、一条……），
#   逐个列举永远列不全。所以改成「动词 + 任意量词 + 任意内容」。
#
# 每个模式都要求「动作词 + 量词/内容」，避免"我看了图片"这种误触。

# 画图动作：画/绘制/生成/做/来/给我 + 可选量词
_IMAGE_PATTERNS = (
    # 画一张 / 画一只 / 画个 / 画只 / 帮我画 …
    r"(画|绘制|绘制一)\s*(一|个|张|只|幅|份|条|副)?",
    # 生成一张 / 生成一只 / 生成个 / 生成图 …
    r"生成\s*(一|个|张|只|幅|份|条|副)?",
    # 做一张图 / 做个图 / 做一只 …
    r"做\s*(一|个|张|只|幅|份)?\s*[图只张个幅]",
    # 来一张 / 来一只 / 给我来一张
    r"来\s*(一|个|张|只|幅)",
    # 给我一只 / 给我一张 —— 后面必须跟量词，
    # 否则"给我讲讲杭州"这种也会被误判
    r"给我\s*(一|个|张|只|幅)\s*",
    # 明确要图片本身：生成图 / 输出一张图片 / 要一张图 / 画插画 …
    # 量词和名词之间可能还有字（"输出一张有趣的图片"），所以用 .{0,4} 放开
    r"(生成|做|画|输出|出|要|整|来)\s*.{0,3}?(图|图片|插画|海报|头像)",
    # “XX的图” / “XX的照片” —— 很少见但确实是要图
    r".的(图|图片|插画|海报|头像|画)",
)

# 明显不是生图的说法：先挡掉，省一次模型调用
NOT_IMAGE_HINTS = (
    "画画", "画风", "画家", "画画的人", "画作", "油画", "国画", "壁画",
    "图片是什么", "这张图", "这个图什么", "图片里", "图解",
    "生成代码", "生成函数", "生成数据",
)

# 判断用的提示词：只问一个问题，输出一个字
DECIDE_PROMPT = """用户在聊天里说了一句话。判断他是不是在**要求你画一张图**（生成图片）。

要求你画图：
- 「帮我画一只橘猫」「生成一张日落的图」「做个头像」「配一张插画」

不是：
- 在讨论绘画、画风、画家
- 在问图片里有什么内容
- 只是顺口提到「图」这个字

用户这句话：
{query}

只输出 YES 或 NO，不要别的。"""


def looks_like_image_request(text: str) -> bool:
    """第一层：关键词粗筛。通过返回 True。

    只做「值得再问一次模型」的初筛，宁可我多一点、错杀让第二层判断。
    """
    content = (text or "").strip()
    if not content:
        return False

    # 先看是不是明显不是生图的说法
    if any(hint in content for hint in NOT_IMAGE_HINTS):
        return False

    return any(re.search(pattern, content) for pattern in _IMAGE_PATTERNS)


def is_image_request(text: str) -> bool:
    """两层判断：关键词过了之后，再让模型确认一次。

    模型调用失败时返回 False —— 宁可不画，也别乱花钱。
    """
    if not looks_like_image_request(text):
        return False

    try:
        raw = get_llm(temperature=0).invoke(
            [HumanMessage(content=DECIDE_PROMPT.replace("{query}", text))]
        ).content
    except Exception as e:
        print(f"[生图] 判断失败，按不画处理：{e}")
        return False

    answer = str(raw or "").strip().upper()
    # 模型可能回答 "YES。" 或 "YES, ..."，取开头两个字判断
    return answer.startswith("YES")


def clean_image_reply(reply: str) -> str:
    """把回复里的 markdown 图片语法去掉。

    为什么要清：
      模型有时会自作主张输出 `![猫](image.jpg)` 这种假链接，
      而真正的图我们会用 [IMAGE:id] 标记追加在后面。
      留着假链接，用户会看到一张加载失败的破图。

    只清 markdown 图片语法，普通文字不动。
    """
    if not reply:
        return ""
    return re.sub(r"!\[[^\]]*\]\([^)]*\)", "", reply).strip()


def text_of_message(message) -> str:
    """从消息里取纯文字（带图时 content 是块数组）。"""
    return text_of(message)
