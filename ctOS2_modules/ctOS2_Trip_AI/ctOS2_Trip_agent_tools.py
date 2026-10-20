import os
from datetime import datetime, timedelta, date
from pathlib import Path

import httpx
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")


#工具一：天气（Open-Meteo）

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#WMO 天气码 -> 中文
WMO_CODE = {
    0: "晴", 1: "基本晴朗", 2: "部分多云", 3: "阴", 45: "有雾", 48: "冻雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨", 56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "强阵雨", 85: "小阵雪", 86: "大阵雪",
    95: "雷阵雨", 96: "雷阵雨伴小冰雹", 99: "雷阵雨伴大冰雹",
}


@tool
def get_weather(city: str, days: int = 3, start_date: str = "") -> str:
    """查询指定城市某几天的天气。

    Args:
        city: 中文城市名，例如"杭州"、"北京"。要传城市名，不要传景点名。
        days: 查询天数，1 到 16 之间，默认 3。
        start_date: 起始日期，格式 YYYY-MM-DD。留空表示从今天开始。
    """
    days = max(1, min(int(days), 16))

    #候选名依次试：原名、"去掉市"、"加上市"（dict.fromkeys 去重又保序）
    name_candidates = dict.fromkeys([city, city.removesuffix("市"), city + "市"])

    #给了起始日期就查该日期起 N 天，否则查今天起 N 天
    date_params = {"forecast_days": days}
    if start_date:
        try:
            begin = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            return f"起始日期格式不对：「{start_date}」，应为 YYYY-MM-DD。"
        begin = max(begin, date.today())
        end = begin + timedelta(days=days - 1)
        limit = date.today() + timedelta(days=15)
        if end > limit:
            return (f"「{start_date}」起 {days} 天的天气超出预报范围。"
                    f"今天是 {date.today()}，最远只能查到 {limit}。")
        date_params = {"start_date": str(begin), "end_date": str(end)}

    try:
        geo = []
        for name in name_candidates:
            geo = httpx.get(GEOCODE_URL, timeout=15, params={
                "name": name, "count": 5, "language": "zh", "format": "json",
            }).json().get("results") or []
            if geo:
                break
        if not geo:
            return f"未找到城市「{city}」，请换一个城市名重试。"

        # 同名地点可能有好几个（浙江、四川都有"杭州"），取人口最多的那个
        geo.sort(key=lambda p: p.get("population") or 0, reverse=True)
        place = geo[0]

        # 匹配到山脉、湖泊这类非人口聚居地 -> 城市名写错了，把候选交回给 LLM 判断
        if not str(place.get("feature_code", "")).startswith("PPL"):
            options = "、".join(f"{p['name']}（{p.get('country') or '?'}）" for p in geo[:5])
            return f"没找到城市「{city}」，最接近的是：{options}。请确认为城市名后重试。"

        daily = httpx.get(FORECAST_URL, timeout=15, params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "timezone": place.get("timezone", "Asia/Shanghai"),
            **date_params,
        }).json().get("daily", {})
    except Exception as e:
        return f"查询天气失败（{e}），请稍后重试。"

    dates = daily.get("time", [])
    if not dates:
        return f"没有查到「{city}」的天气数据。"

    region = f"（{place['admin1']}）" if place.get("admin1") else ""
    lines = [f"{place.get('name', city)}{region}未来 {len(dates)} 天天气："]
    for i, day in enumerate(dates):
        code = daily["weather_code"][i]
        lines.append(
            f"{day}  {WMO_CODE.get(code, '未知')}  "
            f"{daily['temperature_2m_min'][i]} ~ {daily['temperature_2m_max'][i]} °C"
        )

    if all(p.get("population") is None for p in geo):
        lines.append(f"\n提示：以上结果匹配自「{place['name']}」，可能不是你要找的城市。")

    return "\n".join(lines)


#工具二：联网搜索（Tavily）

# max_results=3：够 LLM 判断了，多给反而灌水；include_answer=True 让 Tavily 先给一段结论。
_tavily = TavilySearch(max_results=3, include_answer=True, search_depth="basic")


@tool
def web_search(query: str) -> str:
    """联网搜索实时信息：景点攻略、门票价格、开放时间、评价、最新资讯等。

    Args:
        query: 搜索关键词，例如"杭州西湖 游玩攻略 门票"。
    """
    result = _tavily.invoke(query)
    #结论给 LLM 直接用，来源让它能核对细节
    answer = result.get("answer") or ""
    snippets = "\n".join(
        f"- {r.get('title', '')}：{(r.get('content') or '')[:200]}"
        for r in (result.get("results") or [])[:3]
    )
    return f"{answer}\n\n参考来源：\n{snippets}".strip()


#工具三：路线规划（高德地图 Web 服务）

AMAP_KEY = os.getenv("AMAP_KEY")

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"        # 地名 → 经纬度
AMAP_DIRECTION_URL = {                                              # 经纬度 → 路线
    "driving": "https://restapi.amap.com/v3/direction/driving",     # 驾车/打车
    "walking": "https://restapi.amap.com/v3/direction/walking",     # 步行
}


def _geocode(address: str, city: str) -> tuple[str, str]:
    """地名 → (经纬度, 匹配到的完整地址)。

    高德的路径规划接口只认经纬度、不认地名，所以查询前必须先转换一次。
    查不到就抛 ValueError，由调用方转成给人看的错误文本。
    单独抽成函数是因为一次 get_directions 要转两个地名（起点和终点）。
    """
    r = httpx.get(AMAP_GEOCODE_URL, timeout=15, params={
        "address": address, "city": city, "key": AMAP_KEY,
    }).json()
    geocodes = r.get("geocodes") or []
    if r.get("status") != "1" or not geocodes:
        #错误文本里直接写好"下一步怎么办"——LLM 读到就知道该换名字重试还是放弃
        raise ValueError(
            f"查询「{address}」没能拿到结果（{r.get('info') or '无匹配结果'}）。"
            f"请先换个更具体的名字重试一次；如果还是同样的错误，"
            f"说明地图服务暂时不可用，不要再试了，直接按常识估算并标注（估算）。"
        )
    g = geocodes[0]
    return g["location"], g.get("formatted_address", "")


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

    if mode not in AMAP_DIRECTION_URL:   #不支持的方式回退驾车，避免流程中断
        mode = "driving"

    try:
        #两个地名各自转成经纬度（路径规划接口只认经纬度）
        o, o_addr = _geocode(origin, city)
        d, d_addr = _geocode(destination, city)

        #查路线
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
    except ValueError as e:          # 地名查不到这类"能靠改名字解决"的错误，原样说清楚
        return str(e)
    except Exception as e:           # 网络、超时等意外，避免程序崩溃
        return (f"这个查询没成功（{e}）。可以换个名字再试一次；"
                f"再失败就按常识估算并标注（估算）。")

    distance_km = int(path["distance"]) / 1000
    minutes = int(path["duration"]) // 60
    label = "驾车/打车" if mode == "driving" else "步行"

    # 把"起点匹配 / 终点匹配"一起返回：路线 Agent 靠这两行判断高德有没有认错地方
    return (f"【路线】{origin} → {destination}（{label}）\n"
            f"起点匹配：{o_addr}\n"
            f"终点匹配：{d_addr}\n"
            f"距离：{distance_km:.1f} 公里\n"
            f"耗时：约 {minutes} 分钟")
