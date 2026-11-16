"""旅游攻略模块。

对外只有两个出口（都返回 SSE 事件流）：
    stream.start_guide   开始做攻略，停在景点清单
    stream.resume_guide  勾完景点之后继续，一路跑到游玩建议

读这里的顺序：
    1. graph.py    这张图就是攻略的全部流程
    2. stream.py   开始、暂停、继续、存库
    3. prompts.py  四段内容各自的提示词
"""
