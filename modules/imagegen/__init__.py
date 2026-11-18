"""生图模块：一张能自己跑完的图。

结构：
    START → plan →（ask 或 generate）→ END
             ↑         │
             └─ ask ───┘

为什么它是一张图而不是一个函数：
    plan 节点要判断「需求够不够」——
    够了才花钱画，不够就停下来问。
    这个分支是 agent 和"调一次 API"的分界线。

对外只用 stream.py 的两个函数：
    generate_image(query)  跑一次
    resume_image(tid, ans) 用户答完接着跑
"""
