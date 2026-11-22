"""客服｜图节点

做什么：
  rewrite  把追问补成自包含的检索句，并判断问题在不在知识范围
  retrieve 跑混合检索，拿到带标题路径的片段
  generate 用检索结果 + 历史写答案
  refuse   不在范围内 / 检索不到时直接给拒答话术，不调模型
被谁用：modules/customer/graph.py 注册为节点。

关于历史的两个用法：
  1. 改写：把「那它怎么配」补成「DeepSeek 密钥怎么配」。
     以前是「上一轮问题 + 当前问题」用空格拼起来，噪声大，
     同义改写那类题命中@1 只有 40%，现在是让模型真正改写。
  2. 生成：把历史给模型，让它理解「它」指什么。
"""

import json
import re

from modules.customer.state import AgentState
from common.llm import get_llm
from modules.customer.prompts import (
    ANSWER_PROMPT,
    NOT_FOUND_ANSWER,
    REWRITE_PROMPT,
)
from modules.customer.rag_search import hybrid_search

# 带进提示词的历史轮数（一问一答算一轮）
HISTORY_TURNS = 3


def _format_history(history: list[dict]) -> str:
    """把历史格式化成提示词里的一段文字，只取最近几轮。"""
    if not history:
        return "（这是第一句，没有历史）"

    # 只取最近 HISTORY_TURNS 轮（一问一答），太长的历史会挤占上下文
    recent = history[-HISTORY_TURNS * 2:]

    lines = []
    for item in recent:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if not content:
            continue
        speaker = "用户" if role == "user" else "客服"
        lines.append(f"{speaker}：{content}")

    return "\n".join(lines) if lines else "（这是第一句，没有历史）"


def _parse_rewrite(raw: str) -> tuple[str, bool]:
    """从模型的输出里取出改写后的查询和范围判断。

    模型偶尔会加代码块或者多说一句，所以先抠出 JSON 再解析；
    实在解析不出来就当成「改写失败、在范围内」，用原问题去检索，
    宁可多查一次，也不要因为一次格式抖动把用户挡在拒答分支上。

    返回 (query, in_scope)；query 为空表示改写失败。
    """
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return "", False

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return "", False

    query = str(data.get("query") or "").strip()
    in_scope = data.get("in_scope", True)
    if not isinstance(in_scope, bool):
        in_scope = str(in_scope).strip().lower() not in ("false", "0", "no")
    return query, in_scope


# ---------------------------------------------------------------- 改写

def rewrite_node(state: AgentState) -> dict:
    """把当前问题改写成一句能独立检索的话，并判断在不在知识范围。

    有一个坑要防：探针发现「这东西能帮我干什么」这种本来就完整的问句，
    模型会原样返回。原样返回时，检索层只能靠「智能」「帮我」这种泛词去撞，
    结果撞到哪一节纯看运气（实测撞进了「智能出行」那一节）。

    所以只要改写出来跟原问题一模一样（或者几乎一样），就说明这次改写没起作用，
    补一条「列出 ctOS 的所有功能」这样的意图提示再搜一次。
    改写只用来找资料，用户的答案仍然由 generate 按原问题写。
    """
    query = state["user_query"]
    history = state.get("history") or []

    prompt = (REWRITE_PROMPT
              .replace("{history}", _format_history(history))
              .replace("{user_query}", query))

    in_scope = True
    search_query = ""

    try:
        raw = get_llm(temperature=0).invoke(prompt).content
        search_query, in_scope = _parse_rewrite(raw)
    except Exception:
        # 改写挂了不能拖垮整条链路：退回原问题，别把用户挡在拒答分支外
        search_query, in_scope = query, True

    if not search_query:
        search_query = query

    if in_scope and search_query.strip() == query.strip():
        # 改写没起作用：补意图提示。只有「这是什么」类的问法才补，
        # 已经带具体名词的问题（端口怎么改）补了反而稀释相关性。
        hint = _intent_hint(query)
        if hint:
            search_query = f"{query} {hint}"

    return {"search_query": search_query, "in_scope": in_scope}


# 「这东西能帮我干什么」这类问法没有任何具体名词，
# 单靠原句检索会撞到最近的一节就停手。
#
# 注意别把「是什么」也放进来：那是**具体提问**的固定句式，
# 「什么是 MAX_HITS」「ZHIPU_API_KEY 是什么」都靠它，
# 补一句「ctOS 的全部功能模块介绍」会把相关性冲淡。
_OVERVIEW_WORDS = ("干什么", "做什么", "有什么功能", "能做什么", "有什么用", "有哪些")


def _intent_hint(query: str) -> str:
    """给空泛问句补一个检索意图，具体问句返回空串。"""
    if not any(word in query for word in _OVERVIEW_WORDS):
        return ""
    return "ctOS 的全部功能模块介绍"


def route_start(state: AgentState) -> str:
    """图入口分一次：寒暄不进改写节点，省掉一次模型调用。

    「你好」这种在入口就能判定，没必要为了它去调一次改写模型。
    实测走改写的寒暄要 2.7 秒，走这里只要几十毫秒。
    """
    if _is_greeting(state.get("user_query", "")):
        return "greet"
    return "rewrite"


# ---------------------------------------------------------------- 寒暄

# 单独一句「你好」「谢谢」这种，不该回「抱歉，我在知识库里没有找到相关答案」。
# 用户第一句话就问「你好」是很自然的，原样拒答显得生硬，也看不出这个客服该问什么。
#
# 判法：整句只由问候/客套的词构成（去掉标点后），才算寒暄。
# 「你好，端口怎么改」这种不算——它带着真实问题，要走正常检索。
_GREETING_WORDS = (
    "你好", "您好", "哈喽", "哈啰", "嗨", "hi", "hello", "hey",
    "在吗", "在不在", "有人吗",
    "早上好", "早安", "下午好", "晚上好", "晚安",
    "谢谢", "谢谢你", "多谢", "感谢", "thanks", "thank you",
    "再见", "拜拜", "bye",
    "嗯", "好的", "好", "ok", "收到", "明白了", "懂了",
)

# 去掉标点、空格、全角符号后再比
_GREETING_STRIP = " \t\r\n，。！？、；：,.!?;:~～…\"'“”‘’（）()[]【】"

GREETING_ANSWER = (
    "你好，我是 ctOS 的智能客服。我只负责回答关于这个项目本身的问题，"
    "比如有哪些模块、端口怎么改、数据库有几张表、报错怎么处理。"
    "你把想问的说出来就行，不方便打字的话也可以先问一句「你能做什么」。"
)


def _is_greeting(query: str) -> bool:
    """整句只是寒暄客套，返回 True。

    只看去掉标点后剩下的内容：如果它整个就是一个问候词，才算寒暄。
    这样「你好，端口怎么改」不会被误判（里面有「端口怎么改」）。
    """
    text = (query or "").strip().lower()
    for ch in _GREETING_STRIP:
        text = text.replace(ch, "")
    if not text:
        return False

    if text in _GREETING_WORDS:
        return True

    # 叠词也算：「嗯嗯」「好的好的」
    for word in _GREETING_WORDS:
        if len(word) >= 1 and text == word * (len(text) // len(word)) \
                and len(text) % len(word) == 0:
            return True
    return False


def route_after_retrieve(state: AgentState) -> str:
    """检索之后去哪：三件事同时成立才拒答。

    1. 模型判断不在知识范围（rewrite 节点的 in_scope）
    2. 检索层也没找到像样的资料
    3. 不是「知识库自己有问题」的那种问法

    为什么不让 rewrite 直接拒答：
      探针实测「怎么部署上线」被模型判成 in_scope=false 直接拒答了，
      但文档里明明有一整章部署与运维，检索分数 0.780，是本批最高之一。
      模型对「像不像在问项目」和「知识库里有没有」这两件事分不太清。
      反过来，拿检索分数单独当判据也不行：库外题的最高分 0.780
      和可答题的最高分 0.832 完全交叠（见 rag_eval 扫过的数据）。

      所以改成两边都不同意才拒答，误拒率优先——客服最难受的不是「答得浅」，
      是明明能答却说没找到。
    """
    if state.get("not_found"):
        return "refuse"

    if state.get("in_scope", True):
        return "generate"

    # 模型说不在范围，但检索到了东西：再确认一下是不是在问知识库本身
    if _asks_about_knowledge(state.get("user_query", "")):
        return "generate"

    return "generate" if _strong_hits(state) else "refuse"


# 问「为什么找不到答案」「知识库怎么更新」这类，本质上是在问知识库自己，
# 再怎么说也属于范围内，不能拒答。
_KNOWLEDGE_WORDS = (
    "知识库", "找不到", "没找到", "检索", "向量库", "入库", "资料",
    "文档", "为什么答", "回答不", "客服",
)


def _asks_about_knowledge(query: str) -> bool:
    """问的是知识库/客服自己，必然算范围内。"""
    return any(word in query for word in _KNOWLEDGE_WORDS)


# 检索结果够不够强：最高分明显高过泛词撞车的水位。
# 0.55 是校准过的：可答题最低 0.500（那条被 intent hint 救回来了），
# 库外题大量落在 0.62~0.78，所以这里只用来挡「模型说不在范围」的那一类。
STRONG_HIT_SCORE = 0.68


def _strong_hits(state: AgentState) -> bool:
    """有没有一条够强的检索结果。"""
    return any(
        h.get("score", 0) >= STRONG_HIT_SCORE
        for h in (state.get("hits") or [])
    )


# ---------------------------------------------------------------- 检索

def retrieve_node(state: AgentState) -> dict:
    """混合检索：拿回带标题路径和分数的片段，一块都没有就标记 not_found。"""
    hits = hybrid_search(state["search_query"])

    return {
        "hits": [
            {"text": h.text, "title": h.title, "score": h.score}
            for h in hits
        ],
        "not_found": not hits,
    }


# ---------------------------------------------------------------- 生成

def generate_node(state: AgentState) -> dict:
    """用检索到的片段让模型写回答；一块都没检索到就不调模型。"""
    hits = state.get("hits") or []
    if not hits:
        return {"answer": NOT_FOUND_ANSWER}

    history = state.get("history") or []

    # 每段前面带上「文件 › 一级标题 › 二级标题」，模型知道这段话从哪来
    context = "\n\n---\n\n".join(
        f"【{h['title']}】\n{h['text']}" if h.get("title") else h["text"]
        for h in hits
    )

    prompt = (ANSWER_PROMPT
              .replace("{history}", _format_history(history))
              .replace("{context}", context)
              .replace("{user_query}", state["user_query"]))

    answer = get_llm().invoke(prompt).content.strip()

    return {"answer": answer}


# ---------------------------------------------------------------- 拒答

def refuse_node(state: AgentState) -> dict:
    """不在知识范围：直接给固定话术，不调模型、不检索。"""
    return {"answer": NOT_FOUND_ANSWER, "hits": [], "not_found": True}


# ---------------------------------------------------------------- 寒暄

def greet_node(state: AgentState) -> dict:
    """寒暄客套：回一句引导语，不检索、不调模型。"""
    return {"answer": GREETING_ANSWER, "hits": [], "not_found": False}
