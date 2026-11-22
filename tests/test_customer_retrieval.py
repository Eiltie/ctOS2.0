"""客服模块的纯逻辑测试：切块、改写解析、检索打分、拒答分派。

这几块是这次改造的核心，也是最容易被后来的改动悄悄弄坏的地方：
  - 切块：代码块里的 `#` 会被当成标题，整本手册的标题路径会全变
  - 改写解析：模型多吐一个字、包一层代码块，得能兜住
  - 混合打分：「查不到」必须能真的返回空列表，不能永远返回 4 条
  - 拒答分派：模型误判库外时，不能让检索到的内容被白扔

不连库、不联网、不调模型，全部用假对象。
"""

import pytest

from modules.customer import node as customer_node
from modules.customer.rag_ingest import split_markdown_detailed
from modules.customer.rag_search import Hit


# ---------------------------------------------------------------- 切块

def _titles(text, source="doc.md"):
    return [b["title"] for b in split_markdown_detailed(text, source=source)]


def test_code_fence_hashes_are_not_headings():
    """代码块里的 `# 注释` 不能被当成标题。

    改版前整本手册 63 块里有一半的标题路径是「› source venv/bin/activate」，
    起因就是 bash 片段里的注释行。
    """
    text = (
        "# 真标题\n\n"
        "## 第一节\n\n"
        "正文一，先凑够字数再进代码块，不然这段会被当成碎片丢掉。\n\n"
        "```bash\n"
        "# 这是注释，不是标题\n"
        "source venv/bin/activate\n"
        "```\n\n"
        "## 第二节\n\n"
        "正文二，同样要凑够四十个字以上，保证这一节能单独成块，不会被当成碎片丢掉。\n"
    )
    titles = _titles(text)

    for title in titles:
        assert "这是注释" not in title
        assert "source venv" not in title

    assert any("真标题" in t and "第一节" in t for t in titles)
    assert any("第二节" in t for t in titles)


def test_code_fence_stays_in_one_chunk():
    """超长小节再切时，不能在代码块中间下刀。"""
    body = "\n".join(f"- 列表项 {i}，这里放一些字凑长度凑长度" for i in range(10))
    text = (
        "# 标题\n\n## 长节\n\n"
        + body
        + "\n\n```bash\n"
        + "\n".join(f'echo "命令 {i}"  # 说明说明说明说明' for i in range(30))
        + "\n```\n"
    )

    for chunk in split_markdown_detailed(text, source="doc.md"):
        body_text = chunk["text"]
        # 每个块里的 ``` 必须成对：要么没有代码块，要么完整闭合
        assert body_text.count("```") % 2 == 0, f"代码块被切断：{chunk['title']}"


def test_title_path_contains_source_and_headings():
    """标题路径要能看出「哪份文档的哪一章哪一节」。"""
    text = (
        "# 手册\n\n"
        "## 三、使用手册\n\n"
        "这一章的开头段落，先凑够字数让它不被当成碎片丢掉，后面再开小节。\n\n"
        "## 3.2 客服\n\n"
        "正文内容放在这里，同样要超过四十个字，保证这一节能单独成块。\n"
    )
    titles = _titles(text, source="manual.md")
    assert any("manual.md" in t and "三、使用手册" in t for t in titles)
    assert any("3.2 客服" in t for t in titles)


def test_tiny_fragments_are_dropped():
    """只剩一个标题的碎片不进库。"""
    text = "# 标题\n\n## 空节\n\n## 有内容的节\n\n" + "这里是正文。" * 10
    for chunk in split_markdown_detailed(text, source="doc.md"):
        assert len(chunk["text"].strip()) >= 40


# ---------------------------------------------------------------- 改写解析

@pytest.mark.parametrize("raw", [
    '{"query": "密钥怎么配置", "in_scope": true}',
    '```json\n{"query": "密钥怎么配置", "in_scope": true}\n```',
    '好的，结果如下：{"query": "密钥怎么配置", "in_scope": true}',
])
def test_parse_rewrite_tolerates_model_noise(raw):
    """模型偶尔包代码块或多说一句，都要能解析出来。"""
    query, in_scope = customer_node._parse_rewrite(raw)
    assert query == "密钥怎么配置"
    assert in_scope is True


def test_parse_rewrite_marks_out_of_scope():
    query, in_scope = customer_node._parse_rewrite('{"query": "讲个笑话", "in_scope": false}')
    assert query == "讲个笑话"
    assert in_scope is False


@pytest.mark.parametrize("raw", ["", "我改不了", "{坏的 json"])
def test_parse_rewrite_falls_back_to_empty(raw):
    """解析不出来时返回空查询，调用方据此退回原问题（不能直接判库外）。"""
    query, in_scope = customer_node._parse_rewrite(raw)
    assert query == ""
    assert in_scope is False


# ---------------------------------------------------------------- 意图补全

@pytest.mark.parametrize("query", [
    "这东西能帮我干什么",
    "它能做什么",
    "这个项目有什么功能",
])
def test_intent_hint_for_vague_questions(query):
    """空泛问句要补检索意图，否则检索会撞到最近的一节就停手。"""
    assert customer_node._intent_hint(query)


@pytest.mark.parametrize("query", [
    "端口怎么改",
    "ZHIPU_API_KEY 是什么",
    "embedding-3 是多少维",
])
def test_no_intent_hint_for_specific_questions(query):
    """带具体名词的问句不补，补了反而稀释相关性。"""
    assert customer_node._intent_hint(query) == ""


# ---------------------------------------------------------------- 拒答分派

def _state(hits, in_scope=True, query="随便问问", not_found=False):
    return {
        "user_query": query,
        "in_scope": in_scope,
        "not_found": not_found,
        "hits": [{"text": t, "title": "", "score": s} for t, s in hits],
    }


def test_route_refuses_when_nothing_found():
    assert customer_node.route_after_retrieve(_state([], not_found=True)) == "refuse"


def test_route_generates_when_in_scope():
    assert customer_node.route_after_retrieve(_state([("x", 0.4)])) == "generate"


def test_route_generates_when_hits_are_strong_even_if_model_said_out_of_scope():
    """模型误判库外时，检索到强结果仍然要作答。

    「怎么部署上线」实测被模型判成 in_scope=false，但文档里有整章部署，
    得分 0.780。这类误拒比答得浅更难受。
    """
    state = _state([("部署上线流程", 0.78)], in_scope=False, query="怎么部署")
    assert customer_node.route_after_retrieve(state) == "generate"


def test_route_refuses_when_model_says_out_of_scope_and_hits_are_weak():
    state = _state([("无关内容", 0.50)], in_scope=False, query="今天天气怎么样")
    assert customer_node.route_after_retrieve(state) == "refuse"


@pytest.mark.parametrize("query", [
    "为什么回答老是说找不到资料",
    "知识库怎么更新",
    "客服模块支持追问吗",
])
def test_route_never_refuses_knowledge_questions(query):
    """问知识库自己的问题，模型说库外也不能拒答。"""
    state = _state([("片段", 0.40)], in_scope=False, query=query)
    assert customer_node.route_after_retrieve(state) == "generate"


# ---------------------------------------------------------------- 引用格式

def test_hit_context_carries_title():
    """给模型的段落要带上标题路径，模型才知道这段话从哪来。"""
    hit = Hit(text="正文内容", title="手册.md › 三、使用手册 › 3.2 客服", score=0.8)
    context = hit.as_context()
    assert "手册.md" in context
    assert "3.2 客服" in context
    assert "正文内容" in context


def test_hit_without_title_still_works():
    """老库里没有 title 字段，退化成纯正文，不能崩。"""
    assert Hit(text="正文", title="", score=0.5).as_context() == "正文"


# ---------------------------------------------------------------- 寒暄

@pytest.mark.parametrize("query", [
    "你好", "您好！", "hi", "Hello", "在吗", "谢谢", "好的", "嗯嗯", "谢谢。",
])
def test_greeting_detected(query):
    """纯寒暄要被识别出来，回引导语而不是「没找到」。"""
    assert customer_node._is_greeting(query) is True


@pytest.mark.parametrize("query", [
    "你好，端口怎么改",        # 带着真实问题，不能当寒暄
    "谢谢，那部署呢",
    "你好我是新手",
    "你能做什么",
    "今天天气怎么样",
    "",
    "   ",
])
def test_not_greeting_when_question_attached(query):
    """带问题的句子、空串都不是寒暄，必须走正常检索。"""
    assert customer_node._is_greeting(query) is False


def test_greeting_goes_straight_to_greet():
    """寒暄在入口就分走，不经过改写节点（省一次模型调用）。"""
    state = {"user_query": "你好"}
    assert customer_node.route_start(state) == "greet"
    assert customer_node.route_start({"user_query": "端口怎么改"}) == "rewrite"


def test_greet_node_returns_guide_without_hits():
    """寒暄节点给引导语，不返回检索结果。"""
    out = customer_node.greet_node({"user_query": "你好"})
    assert out["answer"] == customer_node.GREETING_ANSWER
    assert out["hits"] == []
    assert out["not_found"] is False


# ---------------------------------------------------------------- 拒答话术

def test_not_found_answer_offers_guidance():
    """拒答不能只回一句「没找到」——那是个死胡同。

    现在必须同时说清三件事：承认没找到、说明能答什么范围、给出一条下一步。
    """
    from modules.customer.prompts import NOT_FOUND_ANSWER

    assert "没有找到" in NOT_FOUND_ANSWER      # 承认没找到
    assert "ctOS" in NOT_FOUND_ANSWER           # 说清范围
    assert "你能做什么" in NOT_FOUND_ANSWER     # 给出下一步


def test_split_for_typing_covers_whole_text():
    """补发给前端的 TOKEN 要拼回原文，一个字都不能少或多。"""
    from modules.customer.stream import _split_for_typing

    text = "你好，我是 ctOS 的智能客服。\n\n第二段内容。"
    pieces = _split_for_typing(text)
    assert "".join(pieces) == text
    assert all(1 <= len(p) <= 2 for p in pieces)
