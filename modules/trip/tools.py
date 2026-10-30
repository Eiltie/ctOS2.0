"""出行｜三个外部工具

做什么：天气(Open-Meteo)、联网搜索(DeepSeek)、路线(高德)，都包成 @tool 给模型调。
被谁用：modules/trip/node.py 的 bind_tools 和直接 invoke。
注意：工具失败返回「给模型看的提示文字」，不抛异常，免得打断整条流程。
"""

import os
from datetime import datetime, timedelta, date
from pathlib import Path

import httpx
from langchain_core.tools import tool

# 只为了触发 .env 加载（core.llm 在 import 时会 load_dotenv 一次）。
# 本文件下面有一行在模块顶层读 AMAP_KEY，必须保证在这之前 .env 已经加载好。
import core.llm  # noqa: F401

# 出行图的三个工具：天气（Open-Meteo）、搜索（DeepSeek）、路线（高德）

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


def _city_name_variants(city: str) -> list:
    """按顺序给出要尝试的城市名写法。

    为什么要试这么多：天气数据源的地名库来自 GeoNames，
    大城市存简称（"杭州"），中小城市存全称（"贺州市"），
    还有的只存"平遥县"这种。实测 100 个城市里，
    不加"市"会有 22% 查不到，包括厦门、敦煌这种热门地方。
    """
    variants = [city]                      # 原名放最前，多数情况第一次就命中

    # 去掉结尾的行政区后缀（用户可能输入"贺州市"）
    core_name = city
    for suffix in ("市", "县", "区", "盟", "自治州", "地区"):
        if core_name.endswith(suffix):
            core_name = core_name.removesuffix(suffix)
            break
    variants.append(core_name)

    # 再补上「加后缀」的写法：平遥要写"平遥县"、贺州要写"贺州市"才查得到。
    # 用去掉后缀的核心名来加，避免出现"贺州市市"这种
    variants.append(core_name + "市")
    variants.append(core_name + "县")

    # 去重并去掉空字符串，保持上面的顺序
    seen = []
    for name in variants:
        if name and name not in seen:
            seen.append(name)
    return seen


def _lookup_city(city: str) -> dict | None:
    """把城市名换成地点信息（含经纬度）。所有写法都查不到时返回 None。

    查到多个同名地点时取人口最多的那个——
    比如搜"杭州"会同时返回浙江的杭州和四川某个同名小镇。
    """
    tried_names = _city_name_variants(city)

    for name in tried_names:
        # httpx.get 里只有第一个参数（地址）是必须的，
        # params 和 timeout 都能不写。".json()" 把返回的文字转成字典
        resp = httpx.get(GEOCODE_URL, timeout=15, params={
            "name": name, "count": 5, "language": "zh", "format": "json",
        })

        # "results" 是地名接口自己定的字段名，写成别的就取不到
        matches = resp.json().get("results") or []

        if not matches:
            continue

        # 人口为 None 的按 0 处理，避免比较时出错
        return max(matches, key=lambda item: item.get("population") or 0)

    return None


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

    # 天气接口只认经纬度，所以得先拿城市名换一次坐标
    try:
        city_info = _lookup_city(city)
    except Exception as e:
        return f"查询天气失败（{e}），请稍后重试。"

    if not city_info:
        return (f"没找到「{city}」的天气数据。"
                f"可以换个写法试试，比如「{city}市」或「{city}县」；"
                f"如果还查不到，说明天气数据源没收录这个地方，"
                f"建议出发前用手机天气 App 再确认一次。")

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


# 搜索：DeepSeek 官方的 Search 接口，和调模型用同一个 API Key，不需要另外注册
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
