"""反馈的查看工具：在命令行里看用户提交了什么。

用法：
    python -X utf8 -m databases.feedback_view            最近 20 条
    python -X utf8 -m databases.feedback_view -n 50      最近 50 条
    python -X utf8 -m databases.feedback_view --contact  只看留了联系方式的
    python -X utf8 -m databases.feedback_view stats      统计

为什么单独一个文件：
    反馈只给维护者自己看，不对外提供查询接口，
    所以做成命令行工具，不用开一个可能被扫到的 HTTP 接口。
"""

import argparse

from databases.db_feedback import feedback_stats, list_feedback

# 模块代号 → 中文名，打印时显示中文
PAGE_LABELS = {
    "chat": "闲聊",
    "trip": "出行",
    "customer": "客服",
    "login": "登录页",
}


def _short(text: str, width: int) -> str:
    """把多行内容压成一行并截断，保证表格不错位。"""
    flat = " ".join((text or "").split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def show_list(rows: list[dict]) -> None:
    """表格形式打印反馈列表。"""
    if not rows:
        print("\n还没有收到反馈。")
        return

    print()
    print("=" * 78)
    print(f"  {'时间':<12}{'模块':<6}{'评价':<8}{'联系方式':<16}内容")
    print("=" * 78)

    for row in rows:
        when = row["created_at"].strftime("%m-%d %H:%M") if row["created_at"] else "-"
        page = PAGE_LABELS.get(row["page"], row["page"] or "-")
        rating = row["rating"] or "-"
        contact = _short(row["contact"], 15) or "-"
        content = _short(row["content"], 30) or "（只选了评价）"

        print(f"  {when:<12}{page:<6}{rating:<8}{contact:<16}{content}")

        # 内容较长时单独回车一行完整显示，表格里只放摘要
        if row["content"] and len(" ".join(row["content"].split())) > 30:
            print(f"  {'':<12}{'':<6}{'':<8}{'':<16}↳ {row['content'].strip()}")

    print("=" * 78)

    # 底部汇总
    rated = [r for r in rows if r["rating"]]
    counts: dict[str, int] = {}
    for row in rated:
        counts[row["rating"]] = counts.get(row["rating"], 0) + 1

    summary = "  ".join(f"{k} {v}" for k, v in counts.items()) or "无"
    contact_n = sum(1 for r in rows if r["contact"])
    print(f"  共 {len(rows)} 条 ｜ {summary}")
    if contact_n:
        print(f"  其中 {contact_n} 条留了联系方式")


def show_stats() -> None:
    """统计视图：总量 + 三个维度的分布。"""
    s = feedback_stats()

    print()
    print("=" * 50)
    print(f"  反馈总数：{s['total']}")
    print("=" * 50)

    if not s["total"]:
        print("  还没有收到反馈。")
        return

    print("  按评价：")
    for name, n in s["by_rating"].items():
        print(f"    {name:<8}{n:>4} 条")

    print("\n  按模块：")
    for page, n in s["by_page"].items():
        label = PAGE_LABELS.get(page, page)
        print(f"    {label:<8}{n:>4} 条")

    print("\n  最近几天：")
    for row in s["by_day"]:
        print(f"    {row['day']}    {row['n']:>4} 条")

    print(f"\n  留了联系方式的：{s['with_contact']} 条")
    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="查看用户反馈")
    parser.add_argument("-n", "--limit", type=int, default=20, help="显示最近多少条，默认 20")
    parser.add_argument("--contact", action="store_true", help="只看留了联系方式的")
    parser.add_argument("stats", nargs="?", help="传 stats 显示统计")
    args = parser.parse_args()

    if args.stats == "stats":
        show_stats()
        return

    rows = list_feedback(limit=args.limit, only_with_contact=args.contact)
    show_list(rows)


if __name__ == "__main__":
    main()
