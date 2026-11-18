"""出行模块的“判断代码”测试。

这些函数全是普通 if/else，没有模型参与：
输入一句话或几个数字，输出一个分类或一条推荐结论。

它们的共同毛病是：错了照样返回 200，用户照样看到结果，只是结果不对。
所以用测试把"当初定下的规矩"钉住。

跑法：
  .\\venv\\Scripts\\python.exe -m pytest tests\\test_trip_rules.py -v
"""

import pytest

from modules.trip.agent import is_weather_query
from modules.trip.route.need import check_need
from modules.trip.route.tools import (
    _candidate_score,
    choice_to_card,
    choose_recommended,
    format_choice_text,
    get_choice_name,
    normalize_preference,
    normalize_want_mode,
)


# ================================================================ 意图判断
# 来源：README「已经跑出的一次闭环」——杭州今天天气曾被当成闲聊，
# 导致模型自己编气温。这里是那次事故的守卫。

@pytest.mark.parametrize("query", [
    "杭州今天天气怎么样？",
    "北京气温多少",
    "明天会下雨吗",
    "杭州冷不冷",
])
def test_只问天气要认得出来(query):
    assert is_weather_query(query) is True


@pytest.mark.parametrize("query", [
    "从杭州东站到灵隐寺怎么走",
    "去西湖的路线",
    "坐什么车去机场",
])
def test_问路线不算问天气(query):
    assert is_weather_query(query) is False


def test_天气加路线一起问时不走纯天气分支():
    """
    “路上堵不堵、下不下雨”包含天气词也包含路线词。
    这时候必须交给路线子图，不能只答天气——否则用户问的路线就丢了。
    """
    assert is_weather_query("从家到机场冷不冷，路上堵不堵？") is False


def test_完全无关的话不算问天气():
    assert is_weather_query("你好") is False


# ================================================================ 偏好归一

@pytest.mark.parametrize("raw, expected", [
    ("最快", "最快"),
    ("我赶时间", "最快"),
    ("最省钱", "最省钱"),
    ("便宜点", "最省钱"),
    ("少走路", "少走路"),
    ("步行少一点", "少走路"),
    ("少换乘", "少换乘"),
    ("随便", "综合"),
    ("", "综合"),
])
def test_偏好归一(raw, expected):
    assert normalize_preference(raw) == expected


def test_偏好同时提到两个时间越短越优先():
    """
    故意钉住一个顺序：先说“赶时间”的，按最快算。
    以后要改这个优先级，这条测试会提醒你"你正在改变既有行为"。
    """
    assert normalize_preference("赶时间，也不想走路太多") == "最快"


# ================================================================ 方式归一

@pytest.mark.parametrize("raw, expected", [
    ("地铁", "公交/地铁"),
    ("坐公交", "公交/地铁"),
    ("打车", "打车/驾车"),
    ("自己开车", "打车/驾车"),
    ("步行", "步行"),
    ("骑车", "骑行"),
    ("", ""),
    ("随便什么都行", ""),
])
def test_出行方式归一(raw, expected):
    assert normalize_want_mode(raw) == expected


# ================================================================ 方案命名

def test_方案按序号命名():
    assert get_choice_name(0) == "方案一"
    assert get_choice_name(1) == "方案二"
    assert get_choice_name(5) == "方案六"


def test_超出预设名表时回退成数字():
    # CHOICE_NAMES 只有六个，第七个开始用阿拉伯数字
    assert get_choice_name(6) == "方案7"


# ================================================================ 需求检查

def _need(**kw):
    """造一份需求，默认是合法完整的需求，按需覆盖字段。"""
    base = {
        "origin": "杭州东站",
        "destination": "灵隐寺",
        "city": "杭州",
        "departure_time": "2026-11-18 09:00",
        "preference": "综合",
        "companions": "",
        "want_mode": "",
        "avoid": "",
        "notes": "",
    }
    base.update(kw)
    return base


def test_完整需求不需要追问():
    assert check_need(_need()) == ""


def test_缺起点要追问():
    assert "起点" in check_need(_need(origin=""))


def test_缺终点要追问():
    assert "终点" in check_need(_need(destination=""))


def test_起点太笼统要追问():
    msg = check_need(_need(origin="家"))
    assert msg != ""
    assert "太笼统" in msg


def test_终点太笼统要追问():
    msg = check_need(_need(destination="公司"))
    assert msg != ""
    assert "太笼统" in msg


def test_终点没城市时问城市而不是问终点():
    msg = check_need(_need(city=""))
    assert "哪个城市" in msg


# ================================================================ 打分与推荐

def _choice(minutes=30, cost=10.0, walk=1.0, transfers=1, mode="bus", mode_name="公交/地铁"):
    return {
        "mode": mode,
        "mode_name": mode_name,
        "minutes": minutes,
        "cost_yuan": cost,
        "walk_km": walk,
        "transfer_count": transfers,
        "distance_km": 5.0,
        "tolls_yuan": 0.0,
        "traffic_lights": 3,
        "detail": "测试用",
        "lines": [],
    }


def test_最快偏好时用时短的分数低():
    fast = _candidate_score(_choice(minutes=10, cost=50.0), "最快", "", "", "")
    slow = _candidate_score(_choice(minutes=60, cost=1.0), "最快", "", "", "")
    assert fast < slow


def test_最省钱偏好时费用低的分数低():
    cheap = _candidate_score(_choice(minutes=60, cost=1.0), "最省钱", "", "", "")
    pricey = _candidate_score(_choice(minutes=10, cost=50.0), "最省钱", "", "", "")
    assert cheap < pricey


def test_少走路偏好时步行短的分数低():
    less = _candidate_score(_choice(walk=0.2), "少走路", "", "", "")
    more = _candidate_score(_choice(walk=2.5), "少走路", "", "", "")
    assert less < more


def test_少换乘偏好时换乘少的分数低():
    few = _candidate_score(_choice(transfers=0), "少换乘", "", "", "")
    many = _candidate_score(_choice(transfers=3), "少换乘", "", "", "")
    assert few < many


def test_用户点名要坐地铁时地铁方案被提前():
    bus = _choice(minutes=40, cost=5.0, mode="bus", mode_name="公交/地铁")
    drive = _choice(minutes=20, cost=60.0, mode="drive", mode_name="打车/驾车")

    without = _candidate_score(bus, "综合", "", "", "")
    with_want = _candidate_score(bus, "综合", "", "", "公交/地铁")

    # 点名了就要降 60 分
    assert with_want == without - 60


def test_下雨时走路和骑车被惩罚():
    walk = _choice(mode="walk", mode_name="步行")
    bike = _choice(mode="bike", mode_name="骑行")

    assert _candidate_score(walk, "综合", "", "有雨", "") == \
        _candidate_score(walk, "综合", "", "", "") + 30
    assert _candidate_score(bike, "综合", "", "有雨", "") == \
        _candidate_score(bike, "综合", "", "", "") + 20


def test_带老人时骑车惩罚最重():
    """带老人安全第一：bike 加 100，walk 加 60，bus 按步行量加。"""
    bike = _choice(mode="bike", mode_name="骑行")
    assert _candidate_score(bike, "综合", "带老人", "", "") == \
        _candidate_score(bike, "综合", "", "", "") + 100


def test_带小孩比带老人宽松():
    walk = _choice(mode="walk", mode_name="步行")
    elder = _candidate_score(walk, "综合", "带老人", "", "")
    child = _candidate_score(walk, "综合", "带小孩", "", "")

    assert child < elder


def test_推荐位置在候选范围内且选的是高分那条():
    choices = [
        _choice(minutes=60, cost=1.0),
        _choice(minutes=10, cost=80.0),
        _choice(minutes=30, cost=20.0),
    ]
    index = choose_recommended(choices, "最快")

    assert index == 1


def test_没有候选时返回负一():
    assert choose_recommended([], "最快") == -1


def test_推荐会先把偏好归一再用():
    """传中文原话也能用，不要求调用方先归一。"""
    choices = [
        _choice(minutes=60, cost=1.0),
        _choice(minutes=10, cost=80.0),
    ]
    assert choose_recommended(choices, "我赶时间") == 1


# ================================================================ 展示

def test_卡片字段能直接给前端用():
    card = choice_to_card(_choice(mode="bus", mode_name="公交/地铁"))

    assert card["title"] == "公交 / 地铁"
    assert card["minutes"] == 30
    assert card["lines"] == ""
    # mode 必须是前端认识的几个值之一
    assert card["mode"] in ("drive", "bus", "walk", "bike")


def test_打车卡片带红绿灯数():
    card = choice_to_card(_choice(mode="drive", mode_name="打车/驾车"))
    assert any("红绿灯" in fact for fact in card["facts"])


def test_候选文字按方案一二三排版():
    choices = [_choice(), _choice(mode="drive", mode_name="打车/驾车")]
    text = format_choice_text(choices)

    assert "方案一" in text
    assert "方案二" in text


def test_空候选列表不会崩():
    assert format_choice_text([]) == ""
