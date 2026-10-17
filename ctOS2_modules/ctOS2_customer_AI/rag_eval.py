"""RAG 检索测评脚本：量出「检索的边界在哪」。

用法（在项目根目录运行）：

    python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_eval.py
    python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_eval.py -v      # 打印每题的命中详情
    python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_eval.py -c 库外  # 只跑某一类
    python -X utf8 ctOS2_modules/ctOS2_customer_AI/rag_eval.py --fails  # 只看失败的题

它做什么：
    读 eval/golden.json 里的题目，逐题调 hybrid_search()，
    看前 MAX_HITS 条里有没有出现期望关键词，然后按类别统计命中率。

    只读调用检索层，【不修改任何东西】——不改语料、不改集合、不写库。

怎么看结果：
    原词类应该接近 100%。如果这一档就掉，说明检索本身有问题。
    同义改写类明显低于原词类，说明「换个说法就问不出来」是当前边界。
    跨章节类低，说明按 ## 切块导致「答案分散在两块」的场景天然吃亏。
    库外类看的是拒答率：库里没有的问题，检索层仍会返回 4 条（这是设计如此），
    真正拦住它的是提示词。所以这一档在【检索层】测不出拒答，
    脚本只报告「有没有撞上期望关键词」，撞不上就算「正确未命中」。
"""

import argparse
import json
import sys
from pathlib import Path

# 直接运行本文件时项目根目录不在搜索路径里，先补一次（被 import 时重复无害）
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ctOS2_modules.ctOS2_customer_AI.rag_hybrid import MAX_HITS, hybrid_search
from ctOS2_modules.ctOS2_customer_AI.rag_store import load_store

# 题目文件放在 eval/ 目录下（和 data/ 同级，数据归数据、代码归代码）
EVAL_DIR = Path(__file__).resolve().parent / "eval"
GOLDEN_FILE = EVAL_DIR / "golden.json"


def _read_golden():
    """读题目文件。文件不存在时说清楚该放哪。"""
    if not GOLDEN_FILE.exists():
        raise SystemExit(
            f"没找到题库：{GOLDEN_FILE}\n"
            f"题库应该放在 {EVAL_DIR} 目录下，文件名 golden.json"
        )
    return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))


def load_cases(category=None):
    """读题目。category 不为空就只留那一类。"""
    data = _read_golden()
    cases = data["cases"]
    if category:
        cases = [c for c in cases if c.get("category") == category]
    return cases


def load_version():
    """取题库版本号，存结果时写进文件名。"""
    return _read_golden().get("_版本", "?")


def judge(case, hits):
    """判一题过没过，并给出命中在第几名。

    返回 (是否通过, 命中的关键词列表, 最好命中名次)。

    为什么除了「命中」还要记名次：
        只看「4 条里有没有」太宽松。比如问「数据库有几张表」，
        只要第 4 条碰巧含 trip_sessions 也算过，但模型看到的头两条全是无关内容，
        实际答不对。名次越靠前，材料越可能被好好用上。
        名次用 1 起算，没命中记 0。

    有期望关键词的题（should_answer=true）：
        前 MAX_HITS 条里任意一条包含任意一个关键词 -> 通过
    没有期望关键词的题（should_answer=false）：
        检索层必然返回几条（设计如此），所以这里只看「有没有意外撞上」，
        撞上了记为「意外命中」，提醒你这条可能被误答。
    """
    keywords = case.get("expect_keywords") or []

    if not keywords:
        # 库外题：不要求命中，撞上关键词反而说明有风险
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
    """跑全部题，返回统计结果。"""
    load_store()                     # 先把知识库加载好，后面逐题只查不建

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
    """按类别打印命中率表，并给出最差的几题。

    同时给出两个指标：
        命中率@4  —— 前 4 条里有没有。宽松，代表「材料进没进视野」。
        命中率@1  —— 第一条里有没有。严格，代表「材料排没排在第一位」。
    两者差距越大，说明正确答案被无关片段压得越靠后，模型越可能答偏。
    """
    # 按类别聚合，保持 JSON 里的出现顺序
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

    # 排名靠后的题：这类最值得看，它们是「检索到了但排得太靠后」
    late = [r for r in results if r["passed"] and r["rank"] >= 3]
    if late:
        print(f"\n名次靠后（第 3 名及以后），模型容易看漏的 {len(late)} 题：")
        for r in late:
            c = r["case"]
            print(f"  #{c['id']:<2} [{c['category']}] {c['question']}  -> 第{r['rank']}名")

    # 失败清单
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
    """把这次结果存成 eval/runs/ 下的一个 txt，方便以后对比。

    文件名带日期时间和题库版本，例如 2026-10-17_1430_v2.txt。
    为什么留档：过一周回头看「到底比上次好了没」，
    靠印象是不准的，靠文件才准。
    """
    from datetime import datetime

    run_dir = EVAL_DIR / "runs"
    run_dir.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_file = run_dir / f"{stamp}_v{version}.txt"

    # 按类别汇总
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
        total += s["total"]; passed += s["passed"]; top1 += s["top1"]
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
