import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.create_graph import INITIAL_STATE, build_graph
from ctOS2_modules.ctOS2_customer_AI.rag_store import load_store

# 客服模块的终端入口：只在开发时调试用，不参与 Web 服务

EXIT_WORDS = {"exit", "quit", "q", "退出"}


def startup_check() -> None:
    """启动检查：知识库加载不了就打印原因并退出。"""
    try:
        store = load_store()
        print(f"知识库就绪：{store.total} 块内容")
    except RuntimeError as e:
        print(f"\n启动失败：{e}")
        sys.exit(1)


def show_hits(title: str, hits: list[str]) -> None:
    """打印某一层检索命中的片段（每段只取第一行开头）。"""
    print(f"\n【{title}】命中 {len(hits)} 条")
    for i, hit in enumerate(hits, start=1):
        first_line = hit.splitlines()[0][:50]
        print(f"  {i}. {first_line}")


def main() -> None:
    """终端主循环：读一个问题 → 跑图 → 打印三层命中与回答。"""
    print("ctOS2.0-智能客服（输入 exit 退出）")

    startup_check()

    app = build_graph()

    while True:
        query = input("\n你：").strip()
        if query.lower() in EXIT_WORDS:
            print("再见！")
            break
        if not query:
            continue

        try:
            result = app.invoke({**INITIAL_STATE, "user_query": query})

            show_hits("第一层 · 关键词检索", result["keyword_hits"])
            show_hits("第二层 · 向量检索", result["vector_hits"])
            show_hits("第三层 · 混合检索", result["hybrid_hits"])

            print(f"\n【回答】\n{result['answer']}")
        except Exception as e:
            print(f"\n（这次没跑通：{e}）")


if __name__ == "__main__":
    main()
