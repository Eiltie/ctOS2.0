"""智能出行｜记住「刚提议过生图」

做什么：记录「这个会话刚刚提议过画图，还没等到用户回答」。
被谁用：modules/trip/agent.py。

为什么需要状态：
  提议是上一轮发的（「要不要生成一张路线图？」），
  用户的回答是下一轮（「要」）。第二轮里头已经看不到第一轮的提议了，
  得有个地方记住「我刚才问过、问的是哪种图、素材是什么」。

为什么放进程内存而不是数据库：
  这是个「上一句问、下一句答」的短暂状态，生命周期只有一轮对话。
  为它加一张表、一个字段，代价远大于收益：
    · 服务重启丢掉，最多是用户那句「要」被当成普通闲聊，没有副作用
    · 跨进程不共享 —— 现在是单进程部署，不是问题
  真要做多实例了，再换成表也不难（接口已经收在这里）。

过期：超过 MAX_AGE_SECONDS 没等到回答就作废，
      免得用户隔了半天说一句「要好」，突然冒出一张图。
"""

import time

# 提议之后多久内回答还算数
MAX_AGE_SECONDS = 10 * 60

# 内存里存：{ (tenant_id, chat_id): PendingOffer }
# 用租户 + 会话两个键，避免不同用户互相串
_pending: dict[tuple[int, int | None], dict] = {}


def remember(tenant_id, chat_id, kind, prompt, title=""):
    """记下「刚提议过」。

    kind    route / guide
    prompt  如果用户说要，直接拿这个去生图
    title   给用户看的提示（比如「杭州三天行程图」）
    """
    _pending[(int(tenant_id), chat_id)] = {
        "kind": kind,
        "prompt": prompt,
        "title": title,
        "at": time.time(),
    }


def take(tenant_id, chat_id):
    """取出并清掉这条提议；没有或已过期返回 None。

    「取出就清掉」是刻意的：
      一次提议只能被回答一次。用户说了「要」之后，
      下一句再说「要」不该又画一张。
    """
    key = (int(tenant_id), chat_id)
    item = _pending.pop(key, None)

    if not item:
        return None

    if time.time() - item["at"] > MAX_AGE_SECONDS:
        return None

    return item


def peek(tenant_id, chat_id):
    """只看不清（判断该不该画时用，真要画了再 take）。"""
    key = (int(tenant_id), chat_id)
    item = _pending.get(key)

    if not item:
        return None
    if time.time() - item["at"] > MAX_AGE_SECONDS:
        _pending.pop(key, None)
        return None

    return item


def clear(tenant_id, chat_id):
    """主动清掉（比如用户直接换了个话题，或者明确拒绝）。"""
    _pending.pop((int(tenant_id), chat_id), None)
