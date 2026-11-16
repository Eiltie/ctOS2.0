"""出行｜路线决策的业务规则

做什么：决定"查出来的这几条候选，推荐哪条、凭什么、摆给用户看什么字"。
        查数据不在这里——地点和候选路线是 core/tools/amap.py 的事。
被谁用：stream.py（查地点、拼需求确认）、
        graph.py（查候选、选推荐、排版）。
注意：本文件不再直接发网络请求，只做判断和文字，方便单独调规则。
"""

from core.tools.amap import (
    get_bike_choice,
    get_bus_choices,
    get_drive_choices,
    get_walk_choice,
)

# 步行和骑行的距离上限。超过以后就算查得到，也不适合放进候选
WALK_MAX_KM = 6
WALK_MAX_MINUTES = 90
BIKE_MAX_KM = 15
BIKE_MAX_MINUTES = 60

# 用户偏好。模型解析出来的值必须落在这几个里面，不然按"综合"算
PREFERENCE_FASTEST = "最快"
PREFERENCE_CHEAPEST = "最省钱"
PREFERENCE_LESS_WALK = "少走路"
PREFERENCE_LESS_TRANSFER = "少换乘"
PREFERENCE_BALANCED = "综合"

# 带老人/小孩时，走路超过这个距离就不放进候选了
ELDER_WALK_MAX_KM = 2
CHILD_WALK_MAX_KM = 3

# 候选的固定叫法，对比和按钮都用这一套
CHOICE_NAMES = ("方案一", "方案二", "方案三", "方案四", "方案五", "方案六")


def get_choice_name(index):
    """把候选位置换成"方案一"这种叫法。"""
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
    """把"地铁""坐公交"这类说法，归到候选里的方式名。"""
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


def _avoid_mode(avoid, mode):
    """用户说"不坐地铁"这类话时，判断某种方式要不要跳过。"""
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
    "综合"则把时间、费用、步行、换乘按权重加在一起。
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

    # 用户明确说了"坐地铁/打车"这类方式，符合的那条往前排
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


def choice_to_card(choice):
    """把一条候选整理成卡片用的字段，前端直接摆出来就行。"""
    mode = choice["mode"]

    if mode == "drive":
        title, desc = "打车", "点到点直达 · 不用换乘"
    elif mode == "bus":
        title, desc = "公交 / 地铁", "最省钱 · 不受路况影响"
    elif mode == "walk":
        title, desc = "步行", "适合短途 · 不堵车"
    else:
        title, desc = "骑行", "灵活 · 不堵车"

    facts = []
    if mode in ("drive", "bus"):
        facts.append(f"步行 {choice['walk_km']:.1f} 公里")
    if mode == "bus" and choice["transfer_count"] > 0:
        facts.append(f"换乘 {choice['transfer_count']} 次")
    if mode == "drive":
        facts.append(f"红绿灯 {choice['traffic_lights']} 个")
    if choice.get("traffic_text"):
        facts.append(choice["traffic_text"])

    lines = choice.get("lines") or []

    return {
        "mode": mode,
        "title": title,
        "desc": desc,
        "minutes": choice["minutes"],
        "cost": round(choice["cost_yuan"]),
        "distance": round(choice["distance_km"], 1),
        "facts": facts,
        "lines": " → ".join(lines) if lines else "",
    }


def choice_to_row(choice):
    """把一条候选整理成"表格里的一行"。

    和 choice_to_card 的区别：
      card 是用来"展示一张卡"的，带描述和标签，适合单独看；
      row 是用来"横向比较"的，只留能对齐成列的几个数，适合并排比。

    前端两种都会拿到：先摆表格（一眼比），表格下面再给完整文字。
    """
    mode = choice["mode"]

    if mode == "drive":
        name = "打车"
    elif mode == "bus":
        name = "公交/地铁"
    elif mode == "walk":
        name = "步行"
    else:
        name = "骑行"

    # 换乘只在公交有意义，其他方式给"—"，表格里才不会出现"0 次"这种误导
    transfer = f"{choice['transfer_count']} 次" if mode == "bus" else "—"

    return {
        "name": name,
        "minutes": f"{choice['minutes']} 分钟",
        "distance": f"{choice['distance_km']:.1f} km",
        "cost": f"{choice['cost_yuan']:.0f} 元",
        "walk": f"{choice['walk_km']:.1f} km" if choice["walk_km"] else "0",
        "transfer": transfer,
    }


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
    """拼出"需求确认"这一段，让用户看到系统到底理解成了什么。"""
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
    from core.tools.amap import find_place

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
