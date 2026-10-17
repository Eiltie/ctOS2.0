"""智能客服 · 终端调试入口。

    python ctOS2_modules/ctOS2_customer_AI/main.py

对着图打字提问，会打印三层检索各命中了什么，以及最终回答。
这是模块开发阶段的验证工具，不参与 Web 服务。
"""

import sys
from pathlib import Path

# 直接运行本文件时项目根目录不在搜索路径里，先补一次（被 import 时重复无害）。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.create_graph import INITIAL_STATE, build_graph
from ctOS2_modules.ctOS2_customer_AI.rag_store import load_store

EXIT_WORDS = {"exit", "quit", "q", "退出"}      # 输入这些词就结束


def startup_check() -> None:
    """启动检查：把知识库加载好，顺便确认向量库、密钥都正常。

    有问题就在这里说清楚，不用等到用户打完第一个问题才报错。
    """
    try:
        store = load_store()
        print(f"知识库就绪：{store.total} 块内容")
    except RuntimeError as e:
        print(f"\n启动失败：{e}")
        sys.exit(1)         # 检查不过就直接退出，避免带病运行


def show_hits(title: str, hits: list[str]) -> None:
    """打印某一层检索到的片段（只显示开头一小段，看个大概）。"""
    print(f"\n【{title}】命中 {len(hits)} 条")
    for i, hit in enumerate(hits, start=1):
        first_line = hit.splitlines()[0][:50]       # 每段只取第一行前 50 字
        print(f"  {i}. {first_line}")


def main() -> None:
    """终端主循环：读一个问题 → 跑图 → 打印过程与回答。"""
    print("ctOS2.0-智能客服（输入 exit 退出）")

    startup_check()         # 先做启动检查，没问题才开始接受提问

    app = build_graph()     # 图只编译一次，之后每轮复用

    while True:
        query = input("\n你：").strip()
        if query.lower() in EXIT_WORDS:
            print("再见！")
            break
        if not query:              # 空输入直接跳过
            continue

        try:
            # 每轮从初始状态起步，只把 user_query 换成这一轮的问题
            result = app.invoke({**INITIAL_STATE, "user_query": query})

            # 把三层检索的结果都亮出来，方便对比每层命中了什么
            show_hits("第一层 · 关键词检索", result["keyword_hits"])
            show_hits("第二层 · 向量检索", result["vector_hits"])
            show_hits("第三层 · 混合检索", result["hybrid_hits"])

            print(f"\n【回答】\n{result['answer']}")
        except Exception as e:
            # 兜底：某一句出意外也别退出，下一句还能接着问
            print(f"\n（这次没跑通：{e}）")


if __name__ == "__main__":
    main()
