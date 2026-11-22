"""提示词生成 Agent：一句话需求 → 生图提示词。

不调生图接口、不存盘、不管尺寸——只负责把用户的一句话写成能用的提示词。
被 tools/imagesproduct.py 调用（生图的第一个步骤）。

    state.py        图的状态：requirement / images / prompt / status / problem
    create_graph.py 建图
    node.py         唯一的节点 prompt_node
    prompts.py      系统提示词

单独跑一下看效果：

    python -X utf8 -m cli.prompts
"""
