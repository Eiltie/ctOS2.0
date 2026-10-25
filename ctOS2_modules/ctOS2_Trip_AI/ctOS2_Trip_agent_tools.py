import os
from datetime import datetime, timedelta, date
from pathlib import Path

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")

# 出行图的三个工具：天气（Open-Meteo）、搜索（Tavily）、路线（高德）

# 天气：地名接口和预报接口
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# 预报分档：按「整趟行程最远的那天距今天几天」判断属哪一档
#   3 天内   准确，直接给结论
#   7 天内   可参考，提醒临近再确认
#   10 天内  仅供参考，照常给数据但强调准确性有限
#   超过 10  不查，直接说明原因
ACCURATE_WITHIN_DAYS = 3
REFERENCE_WITHIN_DAYS = 7
ALERT_WITHIN_DAYS = 10

# 天气码 -> 中文。只保留会出现的常用码，不认识的显示「未知天气」
WEATHER_CODE_NAMES = {
    0: "晴", 1: "基本晴朗", 2: "多云", 3: "阴",
    45: "有雾", 48: "冻雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "强阵雨", 85: "小阵雪", 86: "大阵雪",
    95: "雷阵雨", 96: "雷阵雨伴冰雹", 99: "雷阵雨伴大冰雹",
}


# 这个 @tool 是让 AI 能调这个函数用的，它自己不收参数，
# AI 是看下面函数的参数名和说明来决定怎么传的
@tool
def get_weather(city: str, days: int = 3, start_date: str = "") -> str:
    """查询指定城市某几天的天气。

    Args:
        city: 中文城市名，例如"杭州"、"北京"。要传城市名，不要传景点名。
        days: 查询天数，1 到 10 之间，默认 3。
        start_date: 起始日期，格式 YYYY-MM-DD。留空表示从今天开始。
    """
    days = max(1, min(int(days), ALERT_WITHIN_DAYS))

    # 先把日期确定下来。出发日默认今天，用户说了就按他说的，
    # 但说成过去的日期没意义，还是从今天算
    today = date.today()
    first_day = today
    if start_date:
        try:
            first_day = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            return f"起始日期格式不对：「{start_date}」，应为 YYYY-MM-DD。"
    first_day = max(first_day, today)

    # 玩 3 天就是出发日往后数 3 天，所以最后一天要减 1
    last_day = first_day + timedelta(days=days - 1)

    # 档位按最远的那天算。不然会出现前两天准、最后一天不准的情况，
    # 用户会以为整趟都准
    days_ahead = (last_day - today).days

    # 太远的天气查不了，与其给个不准的不如直接说清楚，
    # 这里连请求都不发，省得白跑一趟
    if days_ahead > ALERT_WITHIN_DAYS:
        last_queryable_day = today + timedelta(days=ALERT_WITHIN_DAYS)
        return (f"「{start_date or today}」起 {days} 天的天气超出预报范围。"
                f"今天是 {today}，最远只能查到 {last_queryable_day}。")

    # 天气接口只认经纬度，所以得先拿城市名换一次坐标。
    # httpx.get 里只有第一个参数（地址）是必须的，params 和 timeout 都能不写，
    # 这里加 timeout 是怕网络卡住一直等。".json()" 是把返回的文字转成字典。
    # 取 "results" 这个名字是地名接口自己定的，写成别的就啥也拿不到
    try:
        city_matches = httpx.get(GEOCODE_URL, timeout=15, params={
            "name": city, "count": 5, "language": "zh", "format": "json",
        }).json().get("results") or []
    except Exception as e:
        return f"查询天气失败（{e}），请稍后重试。"

    if not city_matches:
        return f"未找到城市「{city}」，请换一个城市名重试。"

    # 一个城市名可能对上好几个地方，国内的杭州、杭州湾边上的村、
    # 国外也叫这名的镇都有可能。这里挑人口最多的，一般就是大家说的那个城市
    city_info = max(city_matches, key=lambda candidate: candidate.get("population") or 0)

    # 拿天气数据。经纬度这两个是必须给的，剩下几个不写也行
    try:
        forecast = httpx.get(FORECAST_URL, timeout=15, params={
            "latitude": city_info["latitude"],
            "longitude": city_info["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": city_info.get("timezone", "Asia/Shanghai"),
            "start_date": str(first_day),
            "end_date": str(last_day),
        }).json().get("daily") or {}
    except Exception as e:
        return f"查询天气失败（{e}），请稍后重试。"

    forecast_dates = forecast.get("time") or []
    if not forecast_dates:
        return f"没有查到「{city}」的天气数据。"

    # 城市名优先用接口给的正式名字，后面带上省份
    city_name = city_info.get("name", city)
    region = f"（{city_info['admin1']}）" if city_info.get("admin1") else ""
    title = f"{city_name}{region}未来 {len(forecast_dates)} 天天气"

    # 三档给的数据一样，区别只在开头和结尾的提醒
    if days_ahead <= ACCURATE_WITHIN_DAYS:
        output_lines = [f"{title}："]
    elif days_ahead <= REFERENCE_WITHIN_DAYS:
        output_lines = [f"{title}（预报较远，建议临近出行前再看一次）："]
    else:
        output_lines = [f"{title}（预报日期较远，准确性有限，仅供参考）："]

    for i, day in enumerate(forecast_dates):
        output_lines.append(
            f"{day}  {WEATHER_CODE_NAMES.get(forecast['weather_code'][i], '未知天气')}  "
            f"{forecast['temperature_2m_min'][i]} ~ {forecast['temperature_2m_max'][i]} °C"
        )

    # 最远那一档额外加结尾提醒，避免用户把远期数据当准确预报
    if days_ahead > REFERENCE_WITHIN_DAYS:
        # 只有一天时就不用写成「X 至 X」
        span = (f"{first_day}" if first_day == last_day
                else f"{first_day} 至 {last_day}")
        output_lines.append("")
        output_lines.append(f"提醒：以上是 {span} 的远期预报，"
                            "实际天气可能变化较大，请以出发前一两天的最新预报为准。")

    return "\n".join(output_lines)



# 这些参数都有默认值，不是非写不可。搜 3 条够模型判断了，多给它也看不过来
_tavily = TavilySearch(max_results=3, include_answer=True, search_depth="basic")


@tool
def web_search(query: str) -> str:
    """联网搜索实时信息：景点攻略、门票价格、开放时间、评价、最新资讯等。

    Args:
        query: 搜索关键词，例如"杭州西湖 游玩攻略 门票"。
    """
    # 返回的是字典，"answer" 是一段现成的结论，"results" 是原文列表
    result = _tavily.invoke(query)
    answer = result.get("answer") or ""
    snippets = "\n".join(
        f"- {r.get('title', '')}：{(r.get('content') or '')[:200]}"
        for r in (result.get("results") or [])[:3]
    )
    return f"{answer}\n\n参考来源：\n{snippets}".strip()


AMAP_KEY = os.getenv("AMAP_KEY")

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"

# 经纬度 -> 路线，键就是工具的 mode 参数取值
AMAP_DIRECTION_URL = {
    "driving": "https://restapi.amap.com/v3/direction/driving",
    "walking": "https://restapi.amap.com/v3/direction/walking",
}


def _geocode(address: str, city: str) -> tuple[str, str]:
    """地名转经纬度，返回（经纬度, 完整地址）；查不到抛 ValueError。"""
    # 高德的路径规划只认经纬度，所以得先转一次。
    # 这三个参数（address、city、key）都得给，少一个就查不了
    r = httpx.get(AMAP_GEOCODE_URL, timeout=15, params={
        "address": address, "city": city, "key": AMAP_KEY,
    }).json()
    geocodes = r.get("geocodes") or []
    if r.get("status") != "1" or not geocodes:
        raise ValueError(
            f"查询「{address}」没能拿到结果（{r.get('info') or '无匹配结果'}）。"
            f"请先换个更具体的名字重试一次；如果还是同样的错误，"
            f"说明地图服务暂时不可用，不要再试了，直接按常识估算并标注（估算）。"
        )
    g = geocodes[0]
    return g["location"], g.get("formatted_address", "")


# @tool 同上。mode 默认开车，不传就是驾车
@tool
def get_directions(origin: str, destination: str, city: str, mode: str = "driving") -> str:
    """查询两个地点之间的路线、距离和耗时。

    Args:
        origin: 起点地名，尽量具体，例如"西湖断桥"、"灵隐寺"。
        destination: 终点地名，例如"河坊街"。
        city: 所在城市，例如"杭州"。用来限定同名地点。
        mode: 出行方式，driving 表示驾车/打车（默认），walking 表示步行。
    """
    if not AMAP_KEY:
        return "没有配置 AMAP_KEY，请检查项目根目录的 config/.env 文件。"

    if mode not in AMAP_DIRECTION_URL:
        # 不支持的方式回退驾车，别让流程中断
        mode = "driving"

    try:
        o, o_addr = _geocode(origin, city)
        d, d_addr = _geocode(destination, city)

        # 起终点这里要传经纬度，不能传地名。三个参数都得给
        r = httpx.get(AMAP_DIRECTION_URL[mode], timeout=15, params={
            "origin": o, "destination": d, "key": AMAP_KEY,
        }).json()
        if r.get("status") != "1":
            return (f"这一段路线没算出来（{r.get('info')}）。"
                    f"别重试了，按常识估算这一段并标注（估算）。")

        paths = (r.get("route") or {}).get("paths") or []
        if not paths:
            return (f"没有查到「{origin}」到「{destination}」的路线，"
                    f"请按常识估算这一段并标注（估算）。")

        path = paths[0]
    except ValueError as e:
        return str(e)
    except Exception as e:
        return (f"这个查询没成功（{e}）。可以换个名字再试一次；"
                f"再失败就按常识估算并标注（估算）。")

    distance_km = int(path["distance"]) / 1000
    minutes = int(path["duration"]) // 60
    label = "驾车/打车" if mode == "driving" else "步行"

    # 带上起终点匹配到的真实地址，路线 Agent 靠它判断高德有没有认错地方
    return (f"【路线】{origin} → {destination}（{label}）\n"
            f"起点匹配：{o_addr}\n"
            f"终点匹配：{d_addr}\n"
            f"距离：{distance_km:.1f} 公里\n"
            f"耗时：约 {minutes} 分钟")
