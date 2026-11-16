"""高德地图：地名查坐标、四种方式的路线、给模型用的单段路线工具。

做什么：只负责"查数据"，把高德的返回整理成统一的字典或文字。
        哪条更值得推荐、给用户看什么结论，是业务层的事
        （modules/trip/capabilities/route/tools.py）。
被谁用：路线决策（地点、候选路线）、攻略拆分前的真实路线查询。
注意：这里不调模型；查不到返回空列表或 None，不抛异常。

两套接口并存，别混用：
  - v5（本文件主体）：一次请求就能同时拿到距离、耗时、费用、路况，
    返回结构化的候选字典，给"多方案对比"用
  - v3（文件末尾的 get_directions）：单段路线的文字版本，包成 @tool 给模型调
"""

import os

import httpx
from langchain_core.tools import tool

# 只为了触发 .env 加载（core.llm 在 import 时会读一次配置）。
# 下面 AMAP_KEY 在模块顶层读取，必须保证在这之前 .env 已经加载好。
import core.llm  # noqa: F401

# 高德地图的 Key 和接口地址
AMAP_KEY = os.getenv("AMAP_KEY")

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"

AMAP_DRIVE_URL = "https://restapi.amap.com/v5/direction/driving"
AMAP_BUS_URL = "https://restapi.amap.com/v5/direction/transit/integrated"
AMAP_WALK_URL = "https://restapi.amap.com/v5/direction/walking"
AMAP_BIKE_URL = "https://restapi.amap.com/v5/direction/bicycling"

# v3 的路线接口（只给 get_directions 用）
AMAP_DIRECTION_URL = {
    "driving": "https://restapi.amap.com/v3/direction/driving",
    "walking": "https://restapi.amap.com/v3/direction/walking",
}

# 每种方式最多留几条候选，太多用户选不过来
MAX_DRIVE_CHOICES = 2
MAX_BUS_CHOICES = 1

# 驾车备选如果比最快那条远太多/慢太多，就不值得摆出来
DRIVE_ALTERNATIVE_MAX_RATIO = 1.5

# 这些级别太笼统，拿来做路线起点/终点很容易算错，交给用户再说具体一点。
# "道路"不算：苏堤、中山路这类路名本身就可以当终点。
VAGUE_LEVELS = {"村庄", "城市", "省份", "国家", "市", "省", "未知"}


# ===== 基础：一条候选的字段和几个单位换算 =====

def _empty_choice(mode, mode_name):
    """建一个空的候选路线，避免每个查询函数都手写一遍全部字段。"""
    return {
        "mode": mode,                  # drive / bus / walk / bike
        "mode_name": mode_name,        # 显示用的中文名
        "distance_km": 0.0,            # 总距离
        "minutes": 0,                  # 预计用时
        "cost_yuan": 0.0,              # 预计费用
        "walk_km": 0.0,                # 需要步行的距离
        "transfer_count": 0,           # 换乘次数
        "traffic_text": "",            # 当前路况
        "detail": "",                  # 一句话补充
        "lines": [],                   # 公交/地铁线路名
        "tolls_yuan": 0.0,             # 过路费
        "traffic_lights": 0,           # 红绿灯个数
    }


def _text(value):
    """高德有的字段会返回空列表，统一转成字符串，后面拼字符串才不会出错。"""
    if isinstance(value, str):
        return value
    return ""


def _meters_to_km(meters):
    """米换成公里，保留一位小数。"""
    return round(int(meters or 0) / 1000, 1)


def _seconds_to_minutes(seconds):
    """秒换成分钟，至少算 1 分钟。"""
    seconds = int(seconds or 0)
    if seconds <= 0:
        return 0
    return max(1, round(seconds / 60))


def _money(value):
    """金额统一保留一位小数。"""
    return round(float(value or 0), 1)


def _get_json(url, params):
    """请求高德接口，失败时打印原因并返回空字典。"""
    try:
        response = httpx.get(url, params=params, timeout=20)
        return response.json()
    except Exception as e:
        print(f"[路线] 请求高德失败：{e}")
        return {}


# ===== 地名 -> 坐标 =====

def _city_matches(result_city, wanted_city):
    """判断高德返回的城市是不是用户说的那个城市。"""
    if not wanted_city:
        return True

    result_name = result_city.replace("市", "")
    wanted_name = wanted_city.replace("市", "")
    if not result_name:
        return True

    return wanted_name in result_name or result_name in wanted_name


def drop_city_prefix(place_name, city):
    """去掉地名前面的城市，例如「北京故宫」→「故宫」。"""
    if not place_name:
        return ""

    city_name = (city or "").replace("市", "").strip()
    if not city_name:
        return ""

    for prefix in (city_name + "市", city_name):
        if place_name.startswith(prefix) and len(place_name) > len(prefix):
            return place_name[len(prefix):].strip()

    return ""


def _to_place(name, place, wanted_city):
    """把高德返回的一条结果整理成地点字典。"""
    location = _text(place.get("location"))
    level = _text(place.get("level"))
    result_city = _text(place.get("city"))

    return {
        "name": name,
        "address": _text(place.get("formatted_address")) or _text(place.get("district")),
        "location": location,
        "city": result_city,
        "province": _text(place.get("province")),
        "adcode": _text(place.get("adcode")),
        "level": level,
        "too_vague": (not level) or (level in VAGUE_LEVELS),
        "different_city": bool(wanted_city and not _city_matches(result_city, wanted_city)),
    }


def find_place_candidates(place_name, city="", limit=3):
    """列出几个可能的地点，给用户挑。

    高德认不出或只认出城市时，与其反复追问，不如把候选摆出来。
    """
    if not place_name or not AMAP_KEY:
        return []

    response = _get_json(AMAP_GEOCODE_URL, {
        "address": place_name,
        "city": city or "",
        "key": AMAP_KEY,
    })

    if response.get("status") != "1":
        return []

    found = []
    for place in response.get("geocodes") or []:
        location = _text(place.get("location"))
        if not location:
            continue

        item = _to_place(place_name, place, city)
        if item["different_city"]:
            continue

        found.append(item)
        if len(found) >= limit:
            break

    return found


def find_place(place_name, city="", allow_nationwide=False):
    """把地名换成经纬度和地址；查不到返回 None。

    参数说明：
        city             用户说的城市，用来防止同名地点跑到别的城市
        allow_nationwide 查不到时要不要全国范围再找一次。
                         起点可以打开（可能从外地过来），终点不要打开，
                         否则"平湖秋月"这种名字会被匹配到外省。
    """
    if not place_name:
        return None

    if not AMAP_KEY:
        print("[路线] 没有配置 AMAP_KEY，查不了地点")
        return None

    city_list = [city] if city else [""]
    if city and allow_nationwide:
        city_list.append("")

    for try_city in city_list:
        response = _get_json(AMAP_GEOCODE_URL, {
            "address": place_name,
            "city": try_city,
            "key": AMAP_KEY,
        })

        if response.get("status") != "1":
            continue

        places = response.get("geocodes") or []

        for place in places:
            location = _text(place.get("location"))
            if not location:
                continue

            result = _to_place(place_name, place, city)

            # 带城市查的那一轮，城市对不上就跳过；
            # 全国兜底那一轮（try_city 为空）才允许跨城
            if city and try_city and result["different_city"]:
                continue

            # 「北京故宫」高德会解析成整个北京市，太笼统。
            # 去掉城市前缀再查一次，拿更具体的地点。
            if result["too_vague"]:
                shorter = drop_city_prefix(place_name, city)
                if shorter and shorter != place_name:
                    better = find_place(shorter, city, allow_nationwide=False)
                    if better is not None and not better["too_vague"]:
                        better["asked_name"] = place_name
                        return better

            return result

    return None


# ===== 四种方式的候选路线（v5） =====

def _traffic_text(steps):
    """把一段段路况按距离汇总成一句话，例如"畅通 70%，拥堵 17%"。"""
    total = 0
    parts = {}

    for step in steps:
        for traffic_item in step.get("tmcs") or []:
            distance = int(traffic_item.get("tmc_distance") or 0)
            status = _text(traffic_item.get("tmc_status")) or "未知"
            total += distance
            parts[status] = parts.get(status, 0) + distance

    if not total:
        return "暂无路况"

    pieces = []
    for status, distance in sorted(parts.items(), key=lambda item: -item[1]):
        if status == "未知":
            continue
        percent = round(distance * 100 / total)
        if percent >= 5:
            pieces.append(f"{status} {percent}%")

    return "，".join(pieces) if pieces else "暂无路况"


def _path_minutes(path):
    """从一条路径里取用时。不同接口把用时放在不同位置，这里统一取。"""
    cost = path.get("cost") or {}
    seconds = cost.get("duration") or path.get("duration") or 0
    return _seconds_to_minutes(seconds)


def get_drive_choices(start_point, end_point):
    """查驾车/打车的候选路线，最多留两条。"""
    if not AMAP_KEY:
        return []

    response = _get_json(AMAP_DRIVE_URL, {
        "origin": start_point,
        "destination": end_point,
        "key": AMAP_KEY,
        "show_fields": "cost,tmcs",
        "alternative_route": 2,
    })

    if response.get("status") != "1":
        print(f"[路线] 驾车查询失败：{response.get('info')}")
        return []

    route = response.get("route") or {}
    paths = route.get("paths") or []
    taxi_cost = _money(route.get("taxi_cost"))

    choices = []
    seen = set()
    first_minutes = None
    first_distance = None

    for path in paths:
        distance_km = _meters_to_km(path.get("distance"))
        minutes = _path_minutes(path)
        if minutes <= 0:
            continue

        # 第一条是主方案，后面的备选如果远太多或慢太多就不摆出来了
        if first_minutes is None:
            first_minutes = minutes
            first_distance = distance_km
        elif (minutes > first_minutes * DRIVE_ALTERNATIVE_MAX_RATIO
              or distance_km > first_distance * DRIVE_ALTERNATIVE_MAX_RATIO):
            continue

        # 两条备选的距离和用时都一样时，只留一条
        mark = (distance_km, minutes)
        if mark in seen:
            continue
        seen.add(mark)

        cost = path.get("cost") or {}
        tolls = _money(cost.get("tolls"))
        traffic_lights = int(cost.get("traffic_lights") or 0)
        traffic_text = _traffic_text(path.get("steps") or [])

        choice = _empty_choice("drive", "打车/驾车")
        choice["distance_km"] = distance_km
        choice["minutes"] = minutes
        choice["cost_yuan"] = round(taxi_cost + tolls, 1)
        choice["tolls_yuan"] = tolls
        choice["traffic_lights"] = traffic_lights
        choice["traffic_text"] = traffic_text
        choice["detail"] = f"红绿灯 {traffic_lights} 个；{traffic_text}"
        if tolls > 0:
            choice["detail"] += f"；过路费约 {tolls:.1f} 元"

        choices.append(choice)
        if len(choices) >= MAX_DRIVE_CHOICES:
            break

    return choices


def get_bus_choices(start_point, end_point, start_city_code, end_city_code):
    """查公交/地铁的候选路线，最多留两条。"""
    if not AMAP_KEY:
        return []

    if not start_city_code or not end_city_code:
        return []

    response = _get_json(AMAP_BUS_URL, {
        "origin": start_point,
        "destination": end_point,
        "key": AMAP_KEY,
        "city1": start_city_code,
        "city2": end_city_code,
        "show_fields": "cost",
    })

    if response.get("status") != "1":
        print(f"[路线] 公交查询失败：{response.get('info')}")
        return []

    route = response.get("route") or {}
    transits = route.get("transits") or []

    choices = []
    seen = set()

    for transit in transits:
        cost = transit.get("cost") or {}
        minutes = _seconds_to_minutes(cost.get("duration"))
        if minutes <= 0:
            continue

        distance_km = _meters_to_km(transit.get("distance"))
        walk_km = _meters_to_km(transit.get("walking_distance"))
        fee = _money(cost.get("transit_fee"))

        # 一段公交算一次乘车，换乘次数 = 乘车段数减一
        bus_count = 0
        lines = []
        for segment in transit.get("segments") or []:
            bus = segment.get("bus") or {}
            buslines = bus.get("buslines") or []
            if not buslines:
                continue

            bus_count += 1
            line_name = _text(buslines[0].get("name")).split("(")[0]
            if line_name and line_name not in lines:
                lines.append(line_name)

        transfer_count = max(0, bus_count - 1)

        mark = (minutes, fee, walk_km)
        if mark in seen:
            continue
        seen.add(mark)

        detail = " → ".join(lines) if lines else "公交/地铁"
        detail += f"；步行 {walk_km:.1f} 公里；换乘 {transfer_count} 次"
        if _text(transit.get("nightflag")) == "1":
            detail += "；夜班车"

        choice = _empty_choice("bus", "公交/地铁")
        choice["distance_km"] = distance_km
        choice["minutes"] = minutes
        choice["cost_yuan"] = fee
        choice["walk_km"] = walk_km
        choice["transfer_count"] = transfer_count
        choice["lines"] = lines
        choice["detail"] = detail

        choices.append(choice)
        if len(choices) >= MAX_BUS_CHOICES:
            break

    return choices


def get_walk_choice(start_point, end_point):
    """查步行路线，只返回一条。"""
    if not AMAP_KEY:
        return None

    response = _get_json(AMAP_WALK_URL, {
        "origin": start_point,
        "destination": end_point,
        "key": AMAP_KEY,
        "show_fields": "cost",
    })

    if response.get("status") != "1":
        print(f"[路线] 步行查询失败：{response.get('info')}")
        return None

    paths = ((response.get("route") or {}).get("paths") or [])
    if not paths:
        return None

    path = paths[0]
    distance_km = _meters_to_km(path.get("distance"))
    minutes = _path_minutes(path)
    if minutes <= 0:
        return None

    choice = _empty_choice("walk", "步行")
    choice["distance_km"] = distance_km
    choice["minutes"] = minutes
    choice["walk_km"] = distance_km
    choice["detail"] = "全程步行"
    return choice


def get_bike_choice(start_point, end_point):
    """查骑行路线，只返回一条。"""
    if not AMAP_KEY:
        return None

    response = _get_json(AMAP_BIKE_URL, {
        "origin": start_point,
        "destination": end_point,
        "key": AMAP_KEY,
        "show_fields": "cost",
    })

    if response.get("status") != "1":
        print(f"[路线] 骑行查询失败：{response.get('info')}")
        return None

    paths = ((response.get("route") or {}).get("paths") or [])
    if not paths:
        return None

    path = paths[0]
    distance_km = _meters_to_km(path.get("distance"))
    minutes = _path_minutes(path)
    if minutes <= 0:
        return None

    choice = _empty_choice("bike", "骑行")
    choice["distance_km"] = distance_km
    choice["minutes"] = minutes
    choice["detail"] = "全程骑行"
    return choice


# ===== 给模型用的单段路线工具（v3，返回文字） =====

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
