"""出行｜路线决策的数据工具

做什么：用高德查同城 A 到 B 的候选路线（驾车、公交地铁、步行、骑行），
        再把它们整理成统一的字典，交给后面的对比和推荐。
被谁用：modules/trip/route_decision_stream.py 和 route_decision_graph.py。
注意：这里只负责“查数据”，不调模型，也不生成给用户看的结论。
"""

import os

import httpx

# 只为了触发 .env 加载（core.llm 在 import 时会读一次配置）
import core.llm  # noqa: F401

# 高德地图的 Key 和四个接口地址
AMAP_KEY = os.getenv("AMAP_KEY")

AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AMAP_DRIVE_URL = "https://restapi.amap.com/v5/direction/driving"
AMAP_BUS_URL = "https://restapi.amap.com/v5/direction/transit/integrated"
AMAP_WALK_URL = "https://restapi.amap.com/v5/direction/walking"
AMAP_BIKE_URL = "https://restapi.amap.com/v5/direction/bicycling"

# 每种方式最多留几条候选，太多用户选不过来
MAX_DRIVE_CHOICES = 2
MAX_BUS_CHOICES = 1

# 驾车备选如果比最快那条远太多/慢太多，就不值得摆出来
DRIVE_ALTERNATIVE_MAX_RATIO = 1.5

# 步行和骑行的距离上限。超过以后就算查得到，也不适合放进候选
WALK_MAX_KM = 6
WALK_MAX_MINUTES = 90
BIKE_MAX_KM = 15
BIKE_MAX_MINUTES = 60

# 用户偏好。模型解析出来的值必须落在这几个里面，不然按“综合”算
PREFERENCE_FASTEST = "最快"
PREFERENCE_CHEAPEST = "最省钱"
PREFERENCE_LESS_WALK = "少走路"
PREFERENCE_LESS_TRANSFER = "少换乘"
PREFERENCE_BALANCED = "综合"

# 这些级别太笼统，拿来做路线起点/终点很容易算错，交给用户再说具体一点。
# “道路”不算：苏堤、中山路这类路名本身就可以当终点。
VAGUE_LEVELS = {"村庄", "城市", "省份", "国家", "市", "省", "未知"}

# 带老人/小孩时，走路超过这个距离就不放进候选了
ELDER_WALK_MAX_KM = 2
CHILD_WALK_MAX_KM = 3

# 候选的固定叫法，对比和按钮都用这一套
CHOICE_NAMES = ("方案一", "方案二", "方案三", "方案四", "方案五", "方案六")

# 一条候选路线里有哪些字段，先在这里写清楚，后面的函数照着填
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


def get_choice_name(index):
    """把候选位置换成“方案一”这种叫法。"""
    if 0 <= index < len(CHOICE_NAMES):
        return CHOICE_NAMES[index]
    return f"方案{index + 1}"


def normalize_preference(preference):
    """把模型可能写歪的偏好，归到固定的五个值里。"""
    if "最快" in preference or "赶时间" in preference:
        return PREFERENCE_FASTEST
    if "省钱" in preference or "便宜" in preference or "费用" in preference:
        return PREFERENCE_CHEAPEST
    if "走路" in preference or "步行" in preference or "不想走" in preference:
        return PREFERENCE_LESS_WALK
    if "换乘" in preference:
        return PREFERENCE_LESS_TRANSFER
    return PREFERENCE_BALANCED


def normalize_want_mode(want_mode):
    """把“地铁”“坐公交”这类说法，归到候选里的方式名。"""
    if not want_mode:
        return ""
    if "公交" in want_mode or "地铁" in want_mode:
        return "公交/地铁"
    if "打车" in want_mode or "开车" in want_mode or "驾车" in want_mode:
        return "打车/驾车"
    if "走路" in want_mode or "步行" in want_mode:
        return "步行"
    if "骑车" in want_mode or "骑行" in want_mode:
        return "骑行"
    return ""


def _city_matches(result_city, wanted_city):
    """判断高德返回的城市是不是用户说的那个城市。"""
    if not wanted_city:
        return True

    result_name = result_city.replace("市", "")
    wanted_name = wanted_city.replace("市", "")
    if not result_name:
        return True

    return wanted_name in result_name or result_name in wanted_name


def _get_json(url, params):
    """请求高德接口，失败时打印原因并返回空字典。"""
    try:
        response = httpx.get(url, params=params, timeout=20)
        return response.json()
    except Exception as e:
        print(f"[路线] 请求高德失败：{e}")
        return {}


def find_place(place_name, city="", allow_nationwide=False):
    """把地名换成经纬度和地址；查不到返回 None。

    参数说明：
        city             用户说的城市，用来防止同名地点跑到别的城市
        allow_nationwide 查不到时要不要全国范围再找一次。
                         起点可以打开（可能从外地过来），终点不要打开，
                         否则“平湖秋月”这种名字会被匹配到外省。
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

            result_city = _text(place.get("city"))
            city_matches = _city_matches(result_city, city)

            # 带城市查的那一轮，城市对不上就跳过；
            # 全国兜底那一轮（try_city 为空）才允许跨城
            if city and try_city and not city_matches:
                continue

            level = _text(place.get("level"))
            return {
                "name": place_name,
                "address": _text(place.get("formatted_address")),
                "location": location,
                "city": result_city,
                "province": _text(place.get("province")),
                "adcode": _text(place.get("adcode")),
                "level": level,
                "too_vague": (not level) or (level in VAGUE_LEVELS),
                "different_city": bool(city and not city_matches),
            }

    return None


def _traffic_text(steps):
    """把一段段路况按距离汇总成一句话，例如“畅通 70%，拥堵 17%”。"""
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


def _avoid_mode(avoid, mode):
    """用户说“不坐地铁”这类话时，判断某种方式要不要跳过。"""
    if mode == "drive":
        return "打车" in avoid or "开车" in avoid or "驾车" in avoid
    if mode == "bus":
        return "公交" in avoid or "地铁" in avoid
    if mode == "walk":
        return "走路" in avoid or "步行" in avoid
    if mode == "bike":
        return "骑车" in avoid or "骑行" in avoid
    return False


def collect_route_choices(start_place, end_place, companions="", weather_text="", avoid=""):
    """把四种方式的候选路线合在一起，返回（候选列表, 补充说明）。

    跨城只查驾车，因为公交/地铁和步行跨城没有意义。
    带老人/小孩、下雨天、用户明确不想用的方式，会少放一些方案进来。
    """
    if not start_place or not end_place:
        return [], "起点或终点没有查到，没法查路线。"

    start_point = start_place["location"]
    end_point = end_place["location"]
    same_city = start_place.get("city") == end_place.get("city")

    choices = []
    notes = []

    if not _avoid_mode(avoid, "drive"):
        choices.extend(get_drive_choices(start_point, end_point))

    if same_city and not _avoid_mode(avoid, "bus"):
        choices.extend(get_bus_choices(
            start_point,
            end_point,
            start_place.get("adcode", ""),
            end_place.get("adcode", ""),
        ))
    elif not same_city:
        notes.append("跨城路线只查了驾车方案")

    if same_city and not _avoid_mode(avoid, "walk"):
        walk = get_walk_choice(start_point, end_point)
        if walk and walk["distance_km"] <= WALK_MAX_KM and walk["minutes"] <= WALK_MAX_MINUTES:
            # 带老人走不了太远，带小孩也尽量别走太久
            if "老人" in companions and walk["distance_km"] > ELDER_WALK_MAX_KM:
                walk = None
            elif "小孩" in companions and walk["distance_km"] > CHILD_WALK_MAX_KM:
                walk = None

            if walk:
                choices.append(walk)

    if same_city and not _avoid_mode(avoid, "bike"):
        # 下雨或带老人时不推荐骑车，查都不查，省一次请求
        if "雨" not in weather_text and "老人" not in companions:
            bike = get_bike_choice(start_point, end_point)
            if bike and bike["distance_km"] <= BIKE_MAX_KM and bike["minutes"] <= BIKE_MAX_MINUTES:
                choices.append(bike)

    if not choices:
        return [], "没查到可用的路线，可能是地图服务暂时不可用，或你排除的方式太多。"

    return choices, "；".join(notes)


def _candidate_score(choice, preference, companions, weather_text, want_mode):
    """给一条候选路线打分，分越低越推荐。

    偏好不同，主要看的指标就不同；剩下的指标只用来打破平手。
    “综合”则把时间、费用、步行、换乘按权重加在一起。
    """
    minutes = choice["minutes"]
    cost = choice["cost_yuan"]
    walk = choice["walk_km"]
    transfers = choice["transfer_count"]

    if preference == PREFERENCE_FASTEST:
        score = minutes * 100 + cost
    elif preference == PREFERENCE_CHEAPEST:
        score = cost * 100 + minutes
    elif preference == PREFERENCE_LESS_WALK:
        score = walk * 100 + minutes
    elif preference == PREFERENCE_LESS_TRANSFER:
        score = transfers * 100 + minutes
    else:
        score = minutes * 2 + cost * 3 + walk * 10 + transfers * 5

    # 用户明确说了“坐地铁/打车”这类方式，符合的那条往前排
    if want_mode and choice["mode_name"] == want_mode:
        score -= 60

    # 下雨天走路和骑车更难受，加一点惩罚
    if "雨" in weather_text:
        if choice["mode"] == "walk":
            score += 30
        elif choice["mode"] == "bike":
            score += 20

    # 带老人时安全第一：走路和骑车都往后排，公交换乘多走的路也算进去
    if "老人" in companions:
        if choice["mode"] == "walk":
            score += 60
        elif choice["mode"] == "bike":
            score += 100
        elif choice["mode"] == "bus":
            score += walk * 10

    # 带小孩时少走路，但比老人宽松一点
    if "小孩" in companions:
        if choice["mode"] == "walk":
            score += 30
        elif choice["mode"] == "bike":
            score += 40
        elif choice["mode"] == "bus":
            score += walk * 5

    return score


def choose_recommended(choices, preference, companions="", weather_text="", want_mode=""):
    """按用户偏好挑一条推荐路线，返回它在列表里的位置。"""
    if not choices:
        return -1

    preference = normalize_preference(preference)
    want_mode = normalize_want_mode(want_mode)

    scores = [
        _candidate_score(choice, preference, companions, weather_text, want_mode)
        for choice in choices
    ]
    return scores.index(min(scores))


def format_choice_text(choices):
    """把候选路线拼成一段文字，给对比提示词用。"""
    lines = []

    for index, choice in enumerate(choices):
        name = get_choice_name(index)
        lines.append(f"{name}｜{choice['mode_name']}")
        lines.append(f"- 距离 {choice['distance_km']:.1f} 公里，用时约 {choice['minutes']} 分钟")

        if choice["mode"] == "drive":
            lines.append(f"- 打车参考价约 {choice['cost_yuan']:.1f} 元（含过路费 {choice['tolls_yuan']:.1f} 元）")
            lines.append(f"- {choice['detail']}")
        elif choice["mode"] == "bus":
            lines.append(f"- 费用 {choice['cost_yuan']:.1f} 元")
            lines.append(f"- 步行 {choice['walk_km']:.1f} 公里，换乘 {choice['transfer_count']} 次")
            lines.append(f"- 线路：{' → '.join(choice['lines']) if choice['lines'] else '公交/地铁'}")
        else:
            lines.append(f"- {choice['detail']}")

        lines.append("")

    return "\n".join(lines).strip()


def format_choice_label(choice):
    """给前端按钮用的短标签，一行能看完。"""
    if choice["mode"] == "drive":
        return (f"打车 · 约{choice['minutes']}分钟 · "
                f"{choice['distance_km']:.1f}公里 · 约{choice['cost_yuan']:.0f}元")

    if choice["mode"] == "bus":
        label = (f"公交 · 约{choice['minutes']}分钟 · "
                 f"{choice['cost_yuan']:.0f}元 · 步行{choice['walk_km']:.1f}公里")
        if choice["transfer_count"] > 0:
            label += f" · 换乘{choice['transfer_count']}次"
        return label

    if choice["mode"] == "walk":
        return f"步行 · 约{choice['minutes']}分钟 · {choice['distance_km']:.1f}公里"

    return f"骑行 · 约{choice['minutes']}分钟 · {choice['distance_km']:.1f}公里"


def format_need_text(need, start_place, end_place, weather_text=""):
    """拼出“需求确认”这一段，让用户看到系统到底理解成了什么。"""
    def place_line(place):
        address = place.get("address") or ""
        if address and address != place.get("name"):
            return f"{place['name']}（{address}）"
        return place.get("name") or ""

    lines = [
        f"起点：{place_line(start_place)}",
        f"终点：{place_line(end_place)}",
        f"出发时间：{need.get('departure_time') or '现在'}",
        f"偏好：{need.get('preference') or PREFERENCE_BALANCED}",
        f"同行：{need.get('companions') or '未说明'}",
    ]

    if need.get("want_mode"):
        lines.append(f"指定方式：{need['want_mode']}")
    if need.get("avoid"):
        lines.append(f"不想用：{need['avoid']}")
    if need.get("notes"):
        lines.append(f"备注：{need['notes']}")

    lines.append(f"天气：{weather_text or '未查到'}")
    return "\n".join(lines)


def make_route_title(need):
    """历史列表里显示的一行标题。"""
    start = need.get("origin") or "起点"
    end = need.get("destination") or "终点"
    return f"{start} → {end}"


if __name__ == "__main__":
    # 手动测：杭州东站 → 灵隐寺
    start = find_place("杭州东站", "杭州", allow_nationwide=True)
    end = find_place("灵隐寺", "杭州")

    print("起点：", start)
    print("终点：", end)

    if start and end:
        choices, note = collect_route_choices(start, end)
        print("补充说明：", note or "无")
        print()
        print(format_choice_text(choices))

        if choices:
            recommended = choose_recommended(choices, PREFERENCE_BALANCED)
            print("推荐位置：", recommended + 1)
            print("推荐标签：", format_choice_label(choices[recommended]))

    # 看两个容易认错的地方：断桥是余杭的村子，平湖秋月在杭州查不到
    print("\n断桥：", find_place("断桥", "杭州"))
    print("平湖秋月：", find_place("平湖秋月", "杭州"))
