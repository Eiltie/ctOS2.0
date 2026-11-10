"""出行需求解析：判断用户这句话是「路线」「攻略」还是「闲聊」。

这是出行流程的第一步，Web 服务和终端调试都会用到，
所以单独成文件——它属于业务逻辑，不是调试代码。

输入：对话历史 + 用户最新一句
输出：(kind, content)
    kind = "ROUTE"   content = 合并后的完整路线需求
    kind = "TRAVEL"  content = 合并后的完整攻略需求
    kind = "CHAT"    content = 直接回给用户的话
"""

from core.llm import get_llm
from modules.trip.prompts import UNDERSTAND_QUERY_PROMPT


def understand_query(history: list[str], query: str) -> tuple[str, str]:
    """判定这句话是路线需求、攻略需求，还是闲聊。

    为什么要合并历史：
      用户可能说「换成 5 天」「改成 8 点出发」，
      这些片段单独看没有完整信息，必须拼上历史才能拿去查路线、排行程。
    """
    # 约定：模型回复第一行只写 ROUTE / TRAVEL / CHAT，第二行起是正文
    prompt = (UNDERSTAND_QUERY_PROMPT
              .replace("{history}", "\n".join(history) or "（还没聊过）")
              .replace("{query}", query))
    raw_reply = get_llm().invoke(prompt).content.strip()

    lines = raw_reply.split("\n", 1)
    kind = lines[0].strip().upper()
    body = lines[1].strip() if len(lines) > 1 else ""

    if kind.startswith("ROUTE"):
        return "ROUTE", body or raw_reply
    if kind.startswith("CHAT"):
        return "CHAT", body

    # 解析失败或模型写成 GUIDE，都按攻略处理：
    # 大不了多跑一次规划，也比把需求当闲聊吞掉好
    return "TRAVEL", body or raw_reply
