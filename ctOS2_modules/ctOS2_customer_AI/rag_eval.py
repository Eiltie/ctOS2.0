import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.rag_hybrid import MAX_HITS, hybrid_search
from ctOS2_modules.ctOS2_customer_AI.rag_store import load_store

# 检索测评脚本：按题库跑一遍，统计各层命中率
# 题库与结果存放位置
EVAL_DIR = Path(__file__).resolve().parent / "eval"
GOLDEN_FILE = EVAL_DIR / "golden.json"


def _read_golden():
    """读题库文件；不存在就说清楚该放哪。"""
    if not GOLDEN_FILE.exists():
        raise SystemExit(
            f"没找到题库：{GOLDEN_FILE}\n"
            f"题库应该放在 {EVAL_DIR} 目录下，文件名 golden.json"
        )
    return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))


def load_cases(category=None):
    """读题目，给了 category 就只留那一类。"""
    data = _read_golden()
    cases = data["cases"]
    if category:
        cases = [c for c in cases if c.get("category") == category]
    return cases


def load_version():
    """取题库版本号，存结果时写进文件名。"""
    return _read_golden().get("_版本", "?")


def judge(case, hits):
    """判一题过没过，返回（是否通过, 命中关键词, 最好名次）。"""
    keywords = case.get("expect_keywords") or []

    if not keywords:
        return True, [], 0

    matched = []
    best_rank = 0
    for rank, hit in enumerate(hits, start=1):
        hit_kws = [k for k in keywords if k in hit]
        if hit_kws:
            matched.extend(k for k in hit_kws if k not in matched)
            if best_rank == 0:
                best_rank = rank

    return bool(matched), matched, best_rank


def run(cases, verbose=False):
    """跑全部题，返回每题的结果、命中和名次。"""
    load_store()

    results = []
    for case in cases:
        hits = hybrid_search(case["question"])
        passed, matched, rank = judge(case, hits)
        results.append({
            "case": case,
            "hits": hits,
            "passed": passed,
            "matched": matched,
            "rank": rank,
        })

        if verbose:
            mark = "PASS" if passed else "FAIL"
            rank_txt = f"第{rank}名" if rank else "未命中"
            top = hits[0].splitlines()[0][:44] if hits else "(无结果)"
            print(f"  [{mark}] #{case['id']:<2} {case['question'][:26]:<28} {rank_txt:<8} Top1: {top}")

    return results


def report(results):
    """按类别打印命中率表，并列出名次靠后和未命中的题。"""
    order = []
    stat = {}
    for r in results:
        cat = r["case"]["category"]
        if cat not in stat:
            stat[cat] = {"total": 0, "passed": 0, "top1": 0}
            order.append(cat)
        stat[cat]["total"] += 1
        stat[cat]["passed"] += int(r["passed"])
        stat[cat]["top1"] += int(r["rank"] == 1)

    print()
    print("=" * 70)
    print(f"检索测评结果（检测层，前 {MAX_HITS} 条判定）")
    print("=" * 70)
    print(f"  {'类别':<12}{'题数':>6}{'命中@4':>8}{'命中率@4':>10}{'命中@1':>8}{'命中率@1':>10}")
    print("  " + "-" * 66)

    total = passed_all = top1_all = 0
    for cat in order:
        s = stat[cat]
        rate4 = s["passed"] / s["total"] * 100
        rate1 = s["top1"] / s["total"] * 100
        total += s["total"]
        passed_all += s["passed"]
        top1_all += s["top1"]
        print(f"  {cat:<12}{s['total']:>6}{s['passed']:>8}{rate4:>9.0f}%{s['top1']:>8}{rate1:>9.0f}%")

    print("  " + "-" * 66)
    o4 = (passed_all / total * 100) if total else 0
    o1 = (top1_all / total * 100) if total else 0
    print(f"  {'总计':<12}{total:>6}{passed_all:>8}{o4:>9.0f}%{top1_all:>8}{o1:>9.0f}%")
    print("=" * 70)

    late = [r for r in results if r["passed"] and r["rank"] >= 3]
    if late:
        print(f"\n名次靠后（第 3 名及以后），模型容易看漏的 {len(late)} 题：")
        for r in late:
            c = r["case"]
            print(f"  #{c['id']:<2} [{c['category']}] {c['question']}  -> 第{r['rank']}名")

    fails = [r for r in results if not r["passed"]]
    if fails:
        print(f"\n完全未命中 {len(fails)} 题：")
        for r in fails:
            c = r["case"]
            top = r["hits"][0].splitlines()[0][:46] if r["hits"] else "(无结果)"
            print(f"  #{c['id']:<2} [{c['category']}] {c['question']}")
            print(f"        期望含: {c['expect_keywords']}")
            print(f"        实际Top1: {top}")
    else:
        print("\n（没有完全未命中的题）")


def save_result(results, version):
    """把这次结果存进 eval/runs/，文件名带时间和题库版本。"""
    from datetime import datetime

    run_dir = EVAL_DIR / "runs"
    run_dir.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_file = run_dir / f"{stamp}_v{version}.txt"

    order, stat = [], {}
    for r in results:
        cat = r["case"]["category"]
        if cat not in stat:
            stat[cat] = {"total": 0, "passed": 0, "top1": 0}
            order.append(cat)
        stat[cat]["total"] += 1
        stat[cat]["passed"] += int(r["passed"])
        stat[cat]["top1"] += int(r["rank"] == 1)

    lines = [
        f"题库版本：v{version}",
        f"运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"判定：前 {MAX_HITS} 条",
        "",
        f"{'类别':<12}{'题数':>6}{'命中@4':>8}{'命中率@4':>10}{'命中@1':>8}{'命中率@1':>10}",
    ]
    total = passed = top1 = 0
    for cat in order:
        s = stat[cat]
        total += s["total"]
        passed += s["passed"]
        top1 += s["top1"]
        lines.append(
            f"{cat:<12}{s['total']:>6}{s['passed']:>8}"
            f"{s['passed']/s['total']*100:>9.0f}%{s['top1']:>8}{s['top1']/s['total']*100:>9.0f}%"
        )
    lines.append(
        f"{'总计':<12}{total:>6}{passed:>8}{passed/total*100:>9.0f}%{top1:>8}{top1/total*100:>9.0f}%"
    )
    lines += ["", "未命中的题："]
    fails = [r for r in results if not r["passed"]]
    if fails:
        for r in fails:
            lines.append(f"  #{r['case']['id']} [{r['case']['category']}] {r['case']['question']}")
    else:
        lines.append("  （无）")

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n结果已保存：{out_file}")


def main():
    """解析命令行参数，跑题、输出报告，需要时存档。"""
    parser = argparse.ArgumentParser(description="RAG 检索测评")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印每题的命中详情")
    parser.add_argument("-c", "--category", help="只跑某一类，例如 原词 / 同义改写 / 跨章节 / 库外")
    parser.add_argument("--fails", action="store_true", help="只显示失败的题（等价于 report 里的失败清单）")
    parser.add_argument("--save", action="store_true", help="把结果存到 eval/runs/ 下，方便以后对比")
    args = parser.parse_args()

    cases = load_cases(args.category)
    if not cases:
        print(f"没有找到题目（category={args.category}）")
        return

    print(f"共 {len(cases)} 题" + (f"（类别：{args.category}）" if args.category else ""))
    results = run(cases, verbose=args.verbose)

    if args.fails:
        fails = [r for r in results if not r["passed"]]
        print(f"\n未命中 {len(fails)} 题：")
        for r in fails:
            c = r["case"]
            print(f"  #{c['id']} [{c['category']}] {c['question']}")
            print(f"        期望含: {c['expect_keywords']}")
            if r["hits"]:
                print(f"        实际Top1: {r['hits'][0].splitlines()[0][:60]}")
        return

    report(results)

    if args.save:
        save_result(results, load_version())


if __name__ == "__main__":
    main()
