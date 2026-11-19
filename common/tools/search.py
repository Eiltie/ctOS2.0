"""联网搜索：DeepSeek 官方的 Search 接口。

做什么：把一次搜索的结果（标题 + 摘要 + 来源）拼成一段给模型读的文字。
被谁用：modules/guide（搜景点）、modules/chat/roleplay/search.py（AI 帮我查）。
注意：和调模型用同一个 API Key，不需要另外注册。
"""

import os

import httpx
from langchain_core.tools import tool
from common.stats import tracked

# 只为了触发 .env 加载（common.llm 在 import 时会 load_dotenv 一次）。
# 本文件在请求时才读 DEEPSEEK_API_KEY，所以这里不是必须的，
# 但保留它可以让"只 import 这个文件"的场景也能拿到配置。
import common.llm  # noqa: F401

# 搜索：DeepSeek 官方的 Search 接口
DEEPSEEK_SEARCH_URL = "https://api.deepseek.com/v1/tools/search"

# 取几条结果。2 条足够模型判断了：
# 摘要本身信息密度高，3 条会把输入撑到 2700 token，反而拖慢下一次模型调用
SEARCH_RESULT_COUNT = 2

# 每条摘要最多带多少字。接口给的摘要有 600~800 字，
# 截到 300 字能保留门票、时间、路线这些关键信息，又不至于把上下文撑爆
SEARCH_SUMMARY_LIMIT = 300

# 相关度门槛。接口每条结果都带 rerank_score（0~3 分，官方说 1.5 以上算优质）。
# 实测：正常搜索在 2 分以上，搜错词时只有 0.2 分左右。
# 取 1.0 而不是 1.5：留点余量，避免个别边缘情况把有用结果也筛掉
SEARCH_MIN_SCORE = 1.0


@tracked("search")
@tool
def web_search(query: str) -> str:
    """联网搜索实时信息：景点攻略、门票价格、开放时间、评价、最新资讯等。

    Args:
        query: 搜索关键词，例如"杭州西湖 游玩攻略 门票"。
    """
    # httpx.post 里只有第一个参数（地址）是必须的，
    # headers 带上密钥，json 是请求体。
    # need_content 传 False：只要 summary 摘要，不要整页正文。
    try:
        response = httpx.post(
            DEEPSEEK_SEARCH_URL,
            timeout=30,
            headers={
                "Authorization": "Bearer " + (os.getenv("DEEPSEEK_API_KEY") or ""),
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "count": SEARCH_RESULT_COUNT,
                "need_content": False,
            },
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except Exception as e:
        return f"这次没搜到（{e}）。可以换个关键词再试一次；还是不行就按常识推荐，别反复重试。"

    if not results:
        return f"搜「{query}」没有任何结果。换个更具体的说法再试一次。"

    # 只留相关度够的结果。实测：正常搜索的分数在 2 分以上，
    # 而搜错词、乱码时返回的都是 0.2 分左右的无关页面。
    # 与其把无关内容硬塞给模型（它会当真），不如直说没搜到
    good_results = [r for r in results if (r.get("rerank_score") or 0) >= SEARCH_MIN_SCORE]
    if not good_results:
        return (f"搜「{query}」没有找到相关的结果。"
                f"换个更具体的说法再试一次；如果还是没有，就按常识推荐，别反复重试。")

    # 按分数从高到低排，好的排前面
    good_results.sort(key=lambda r: r.get("rerank_score") or 0, reverse=True)

    # 拼成文字给模型读：每条一行标题加摘要
    output_lines = []
    source_urls = []
    for item in good_results:
        title = item.get("title") or "（无标题）"
        summary = (item.get("summary") or item.get("snippet") or "").strip()
        summary = " ".join(summary.split())[:SEARCH_SUMMARY_LIMIT]
        output_lines.append(f"- {title}：{summary}")

        url = item.get("url") or ""
        if url:
            source_urls.append(url)

    # 来源统一放在最后一行，不占正文空间
    if source_urls:
        output_lines.append("来源：" + "　".join(source_urls))

    return "\n".join(output_lines)

