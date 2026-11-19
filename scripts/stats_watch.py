"""运行统计监控 —— 启动后挂在终端里，实时看后端每次请求的数据。

怎么用：
    python -X utf8 scripts/stats_watch.py              # 跟着看，一直挂着
    python -X utf8 scripts/stats_watch.py --summary    # 只看当前汇总，看完退出
    python -X utf8 scripts/stats_watch.py --clear      # 清空统计文件

数据从哪来：
    common/stats.py 每次请求结束往 logs/stats.jsonl 追加一行 JSON。
    这个脚本就跟 tail -f 一样跟着读，读到新的就打印。

为什么是独立脚本而不是后端内置：
    后端重启用不着重启它；它挂了不影响后端；想看不同的汇总口径改这里就行。
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATS_FILE = PROJECT_ROOT / "logs" / "stats.jsonl"

# 结局的中文名和颜色
OUTCOME_LABELS = {
    "ok": ("正常", "\033[32m"),       # 绿
    "error": ("出错", "\033[31m"),    # 红
    "aborted": ("中断", "\033[33m"),  # 黄
    "stalled": ("卡住", "\033[35m"),  # 紫
}
RESET = "\033[0m"
DIM = "\033[2m"

# 模块中文名
MODULE_LABELS = {
    "chat": "对话",
    "chat-role": "角色",
    "trip": "出行",
    "customer": "客服",
    "image": "生图",
    "auth": "账号",
    "other": "其他",
}


def colorize(text: str, code: str) -> str:
    """上色。管道输出（不是终端）时不着色，免得重定向到文件里全是乱码。"""
    if not sys.stdout.isatty():
        return text
    return f"{code}{text}{RESET}"


def parse_line(line: str) -> dict | None:
    try:
        return json.loads(line)
    except Exception:
        return None


def load_all() -> list[dict]:
    """把文件里已有的全读进来。文件不存在就返回空。"""
    if not STATS_FILE.exists():
        return []

    rows = []
    with open(STATS_FILE, encoding="utf-8") as f:
        for line in f:
            item = parse_line(line.strip())
            if item:
                rows.append(item)
    return rows


def format_tools(tools: dict) -> str:
    """工具调用：高德×4✓3 天气×1✓1 这种形式。"""
    if not tools:
        return ""

    names = {"amap": "高德", "weather": "天气", "search": "搜索"}
    parts = []
    for name, counts in tools.items():
        total, ok = counts[0], counts[1]
        label = names.get(name, name)
        # 全成功就不显示勾，省点宽度
        if ok == total:
            parts.append(f"{label}×{total}")
        else:
            parts.append(f"{label}×{total}✓{ok}")
    return " ".join(parts)


def print_row(row: dict) -> None:
    """打印一行明细。"""
    at = row.get("at", "")
    try:
        clock = datetime.fromisoformat(at).strftime("%H:%M:%S")
    except Exception:
        clock = at[-8:] if at else "--:--:--"

    outcome = row.get("outcome", "ok")
    label, color = OUTCOME_LABELS.get(outcome, ("未知", ""))

    module = MODULE_LABELS.get(row.get("module", ""), row.get("module", ""))
    path = row.get("path", "")
    elapsed = row.get("elapsed", 0)
    tin = row.get("tokens_in", 0)
    tout = row.get("tokens_out", 0)
    tools = format_tools(row.get("tools") or {})

    # 拼一行：时间 路径 模块 结局 耗时 token 工具
    line = (
        f"{DIM}[{clock}]{RESET} "
        f"{path:<18} "
        f"{module:<4} "
        f"{colorize(label, color):<10} "
        f"{elapsed:>6.1f}s "
        f"in={tin:<6} out={tout:<6}"
    )
    if tools:
        line += f" {tools}"

    # 出错的话把原因带出来
    error = row.get("error")
    if error:
        line += f"\n{'':<10}{colorize('原因: ' + error, '\033[31m')}"

    print(line, flush=True)


def print_summary(rows: list[dict]) -> None:
    """打印累计汇总。"""
    if not rows:
        print(f"{DIM}（还没有数据）{RESET}")
        return

    total = len(rows)
    by_outcome: dict[str, int] = {}
    by_module: dict[str, int] = {}
    total_elapsed = 0.0
    total_in = 0
    total_out = 0
    tool_total = 0
    tool_ok = 0

    for row in rows:
        outcome = row.get("outcome", "ok")
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1

        module = row.get("module", "other")
        by_module[module] = by_module.get(module, 0) + 1

        total_elapsed += row.get("elapsed", 0)
        total_in += row.get("tokens_in", 0)
        total_out += row.get("tokens_out", 0)

        for counts in (row.get("tools") or {}).values():
            tool_total += counts[0]
            tool_ok += counts[1]

    ok_count = by_outcome.get("ok", 0)
    rate = ok_count / total * 100 if total else 0
    avg = total_elapsed / total if total else 0

    print()
    print("─" * 78)

    # 第一行：总次数和各结局分布
    parts = [f"共 {total} 次"]
    for key in ("ok", "error", "aborted", "stalled"):
        n = by_outcome.get(key, 0)
        if not n:
            continue
        label, color = OUTCOME_LABELS[key]
        parts.append(colorize(f"{label} {n}", color))
    print("  ".join(parts))

    # 第二行：完成率和平均
    line2 = f"完成率 {rate:.1f}%  平均 {avg:.1f}s  token {total_in + total_out}"
    if tool_total:
        line2 += f"  工具 {tool_total} 次，成功 {tool_ok}（{tool_ok / tool_total * 100:.0f}%）"
    print(line2)

    # 第三行：按模块分布
    if len(by_module) > 1:
        seg = []
        for module, n in sorted(by_module.items(), key=lambda x: -x[1]):
            seg.append(f"{MODULE_LABELS.get(module, module)} {n}")
        print("按模块：" + "  ".join(seg))

    print("─" * 78)


def follow() -> None:
    """跟着文件读。像 tail -f，但只认新追加的完整行。"""
    print(colorize("统计监控已启动", "\033[36m"))
    print(f"{DIM}数据文件：{STATS_FILE}{RESET}")
    print(f"{DIM}Ctrl+C 退出{RESET}")
    print()

    # 先把已有的全打一遍，然后接着跟
    rows = load_all()
    for row in rows:
        print_row(row)
    if rows:
        print_summary(rows)

    if not STATS_FILE.exists():
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATS_FILE.touch()

    # 记下读到哪了，只读后面新增的部分
    with open(STATS_FILE, encoding="utf-8") as f:
        f.seek(0, 2)
        position = f.tell()

    try:
        while True:
            # 文件被清空或重建了，从头读
            if not STATS_FILE.exists():
                time.sleep(1)
                continue

            size = STATS_FILE.stat().st_size
            if size < position:
                position = 0

            if size > position:
                with open(STATS_FILE, encoding="utf-8") as f:
                    f.seek(position)
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        item = parse_line(line)
                        if item:
                            print_row(item)
                            rows.append(item)
                    position = f.tell()
                # 每来一条就刷新汇总，挂在终端里一直能看到最新数字
                print_summary(rows)

            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        print(colorize("已退出", "\033[36m"))


def main() -> None:
    args = sys.argv[1:]

    if "--clear" in args:
        if STATS_FILE.exists():
            STATS_FILE.unlink()
        print("统计文件已清空")
        return

    if "--summary" in args:
        rows = load_all()
        print(f"数据文件：{STATS_FILE}")
        print_summary(rows)
        return

    follow()


if __name__ == "__main__":
    main()
