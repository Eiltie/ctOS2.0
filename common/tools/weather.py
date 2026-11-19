"""天气：Open-Meteo，不需要 Key。

做什么：城市名换经纬度，再查未来几天的天气，拼成一段给模型读的文字。
被谁用：路线决策（出发当天）、旅游攻略（整趟行程）、出行记录的天气快捷回答。
注意：失败返回「给模型看的提示文字」，不抛异常，免得打断整条流程。
"""

from datetime import date, datetime, timedelta

import httpx
from langchain_core.tools import tool
from common.stats import tracked

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
@tracked("weather")
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

