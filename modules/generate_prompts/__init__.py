"""提示词生成 Agent：把用户的一句话需求写成生图提示词。

不调生图接口、不存盘、不管尺寸，这一层只负责写提示词。
被 tools/imagesproduct.py 调用，是生图的第一步。

    state.py        状态：requirement / images / prompt / status / problem
    create_graph.py 建图
    node.py         唯一的节点
    prompts.py      系统提示词

单独跑看效果：python -X utf8 -m cli.prompts
"""
