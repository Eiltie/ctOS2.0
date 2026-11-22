"""跨模块复用的外部数据工具。

放这里的标准：**两个以上模块在用**。
  - search.py         联网搜索（chat 角色扮演 + trip 攻略）
  - imagesproduct.py  生图（chat 对话 + trip 出行）

只有单个模块用的工具，放那个模块自己的文件夹里，比如：
  - modules/trip/amap.py     高德地图（只有出行用）
  - modules/trip/weather.py  天气（只有出行用）

约定：
  - 只负责「查数据」，不判断、不推荐、不写提示词
  - 失败返回空值或给模型看的提示文字，不抛异常
"""
