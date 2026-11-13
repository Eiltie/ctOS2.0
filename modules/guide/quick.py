"""旅游攻略｜只问天气的快捷回答

做什么：用户只问"杭州明天下雨吗"时，不用跑整张攻略图，直接查天气回一句。
被谁用：modules/guide/stream.py（攻略入口）、modules/trip/stream.py（路线入口临时借用）。
注意：不写库，写库由调用方决定（存成一号 CHAT 轮）。

为什么放在攻略模块：
  天气建议本来就是攻略的一部分（攻略第一段就是天气）。
  路线入口也用它，是因为"问天气"不该被逼着先报起点终点。
"""

from modules.guide.node import weather_node

FALLBACK = "这次没查到天气，换个城市名再试试。"


def answer_weather(query):
    """查一次天气，返回给用户看的文字；查不到返回兜底句。"""
    try:
        state = weather_node({
            "user_query": query,
            "history": [],
            "messages": [],
        })
        text = (state.get("weather") or "").strip()
    except Exception as e:
        print(f"[天气] 查询失败：{e}")
        return FALLBACK

    return text or FALLBACK
