"""ctOS 2.0 最小测评脚本。

做三件事：
  1. 按 eval/cases.json 跑真实接口
  2. 自动检查关键词、字数、耗时
  3. 生成一份 JSON 明细 + Markdown 报告

用法：
  python -X utf8 eval/run_eval.py
  python -X utf8 eval/run_eval.py --only role-identity,role-boundary
  python -X utf8 eval/run_eval.py --base http://127.0.0.1:8080
"""

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).resolve().parent
CASES_FILE = EVAL_DIR / "cases.json"
RESULTS_DIR = EVAL_DIR / "results"
DEFAULT_BASE = "http://127.0.0.1:8080"


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def short(text, limit=220):
    text = (text or "").strip().replace("\r", "")
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def read_cases(only=None):
    data = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    cases = data["cases"]
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        cases = [c for c in cases if c["id"] in wanted]
    return data.get("version", "?"), cases


def sse_events(response):
    """读 SSE，返回解析后的事件列表。"""
    events = []
    for line in response.iter_lines():
        line = (line or "").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return events


def post_text(client, base, path, body, headers, timeout=240):
    """普通流式文本接口，返回（全文、会话 id、耗时）。"""
    start = time.time()
    with client.stream("POST", base + path, json=body, headers=headers,
                       timeout=httpx.Timeout(timeout, connect=10)) as res:
        res.raise_for_status()
        text = "".join(res.iter_text())
        session_id = res.headers.get("x-session-id")
    return text, session_id, time.time() - start


def post_sse(client, base, path, body, headers, timeout=240):
    """SSE 接口，返回（事件列表、耗时）。"""
    start = time.time()
    with client.stream("POST", base + path, json=body, headers=headers,
                       timeout=httpx.Timeout(timeout, connect=10)) as res:
        res.raise_for_status()
        events = sse_events(res)
    return events, time.time() - start


def trip_text(events):
    """从出行事件里取最终文本，TOKEN 只是过程，不重复算。"""
    parts = []
    for ev in events:
        if ev.get("kind") in ("DONE", "CHAT"):
            text = (ev.get("text") or ev.get("message") or "").strip()
            if text and text not in parts:
                parts.append(text)

    if parts:
        return "\n\n".join(parts)

    # 没有 DONE 时退回 TOKEN，至少能看到模型写了什么
    tokens = [ev.get("text") or "" for ev in events if ev.get("kind") == "TOKEN"]
    return "".join(tokens).strip()


def find_chat_id(events):
    for ev in events:
        if ev.get("chat_id"):
            return ev["chat_id"]
    return None


def trip_answer(client, base, query, headers):
    """跑一次出行；遇到景点/路线/方案选择时自动选默认项。"""
    start = time.time()
    events, _ = post_sse(client, base, "/trip/chat",
                         {"query": query, "history": []}, headers)
    parts = []
    chat_id = None

    for _ in range(4):
        chat_id = chat_id or find_chat_id(events)
        text = trip_text(events)
        if text:
            parts.append(text)

        ask = next((ev for ev in events
                    if ev.get("kind") in ("ASK", "ASK_SPOTS", "ASK_ROUTE")), None)
        if not ask:
            break

        kind = ask.get("kind")
        thread_id = ask.get("thread_id") or ""

        if kind == "ASK_SPOTS":
            events, _ = post_sse(client, base, "/trip/guide/spots", {
                "thread_id": thread_id,
                "removed": [],
                "added": "",
            }, headers)

        elif kind == "ASK_ROUTE":
            events, _ = post_sse(client, base, "/trip/guide/route", {
                "thread_id": thread_id,
                "want_route": False,
                "query": "",
                "city": "",
                "chat_id": chat_id,
            }, headers)

        else:
            options = ask.get("options") or []
            choice = ask.get("recommended_id") or (options[0]["id"] if options else "1")
            events, _ = post_sse(client, base, "/trip/route/choose", {
                "thread_id": thread_id,
                "choice_id": choice,
                "chat_id": chat_id,
            }, headers)

    return "\n\n".join(parts), time.time() - start, chat_id


def check_answer(case, answer, elapsed, extra=None):
    """按规则打分；返回检查明细和是否通过。"""
    checks = []
    passed = True
    text = (answer or "").strip()

    if not text:
        checks.append("没有返回内容")
        passed = False

    for word in case.get("must_have_all") or []:
        ok = word in text
        checks.append(("有" if ok else "缺") + f"「{word}」")
        passed = passed and ok

    for word in case.get("must_have_any") or []:
        hit = next((item for item in case["must_have_any"] if item in text), None)
        if hit:
            checks.append(f"命中「{hit}」")
            break
        checks.append("缺任一项：" + " / ".join(case["must_have_any"]))
        passed = False
        break

    for group in case.get("must_have_groups") or []:
        hit = next((word for word in group if word in text), None)
        if hit:
            checks.append(f"命中「{hit}」")
        else:
            checks.append("缺任一项：" + " / ".join(group))
            passed = False

    for word in case.get("must_not") or []:
        if word in text:
            checks.append(f"出现禁止内容「{word}」")
            passed = False

    min_chars = case.get("min_chars")
    if min_chars and len(text) < min_chars:
        checks.append(f"太短（{len(text)} 字）")
        passed = False

    max_chars = case.get("max_chars")
    if max_chars and len(text) > max_chars:
        checks.append(f"太长（{len(text)} 字，上限 {max_chars}）")
        passed = False

    limit = case.get("max_seconds")
    if limit and elapsed > limit:
        checks.append(f"超时（{elapsed:.1f}s，上限 {limit}s）")
        passed = False

    if extra:
        checks.extend(extra)

    return passed, checks


def run_chat(client, base, case, headers):
    answer, session_id, elapsed = post_text(
        client, base, "/chat", {"messages": case["input"]}, headers)
    return answer, elapsed, f"会话 {session_id}"


def run_roleplay(client, base, case, headers):
    start = client.post(base + "/roleplay/start",
                        json={"role_id": case["role_id"]}, headers=headers)
    start.raise_for_status()
    data = start.json()
    session_id = data["session_id"]
    opening = data.get("opening") or ""

    answer = ""
    start_time = time.time()

    for index, turn in enumerate(case.get("turns") or []):
        # 聊满 6 轮后，给后台记忆整理留一点时间
        if index == 6:
            time.sleep(2.5)

        answer, _, _ = post_text(client, base, "/chat", {
            "messages": turn,
            "session_id": session_id,
            "role_id": case["role_id"],
        }, headers)

    elapsed = time.time() - start_time
    extra = f"开场白：{short(opening, 50)}"
    return answer, elapsed, extra


def run_customer(client, base, case, headers):
    events, elapsed = post_sse(client, base, "/customer/chat",
                               {"query": case["input"], "history": []}, headers)
    done = [ev.get("text") or "" for ev in events if ev.get("kind") == "DONE"]
    if done:
        answer = max(done, key=len)
    else:
        answer = "".join(ev.get("text") or "" for ev in events
                         if ev.get("kind") == "TOKEN")
    return answer, elapsed, ""


def run_platform_session(client, base, case, headers):
    answer, session_id, elapsed = post_text(
        client, base, "/chat", {"messages": case["input"]}, headers)
    if not session_id:
        return answer, elapsed, "没有拿到会话 id"

    messages = client.get(base + f"/sessions/{session_id}/messages",
                          headers=headers)
    messages.raise_for_status()
    rows = messages.json()
    saved = any((row.get("content") or "").strip() == case["input"] for row in rows)

    deleted = client.delete(base + f"/sessions/{session_id}", headers=headers)
    deleted.raise_for_status()

    extra = "会话已保存" if saved else "会话没有保存"
    passed_note = "已删除" if deleted.json().get("ok", True) else "删除失败"
    return answer, elapsed, f"{extra}；{passed_note}"


def run_platform_role(client, base, case, headers):
    start = client.post(base + "/roleplay/start",
                        json={"role_id": case["role_id"]}, headers=headers)
    start.raise_for_status()
    session_id = start.json()["session_id"]

    info = client.get(base + f"/roleplay/session/{session_id}", headers=headers)
    info.raise_for_status()
    role = info.json().get("role")
    deleted = client.delete(base + f"/sessions/{session_id}", headers=headers)
    deleted.raise_for_status()

    answer = "角色会话可以创建、识别、删除"
    if not role:
        return "", 0, "角色会话识别失败"
    return answer, 0, f"角色 {role.get('name')}；已删除"


def run_case(client, base, case, headers):
    module = case["module"]
    start = time.time()

    try:
        if module == "chat":
            answer, elapsed, extra = run_chat(client, base, case, headers)
        elif module == "roleplay":
            answer, elapsed, extra = run_roleplay(client, base, case, headers)
        elif module == "customer":
            answer, elapsed, extra = run_customer(client, base, case, headers)
        elif module == "trip":
            answer, elapsed, chat_id = trip_answer(client, base, case["input"], headers)
            extra = f"会话 {chat_id}" if chat_id else ""
        elif case.get("kind") == "role_session":
            answer, elapsed, extra = run_platform_role(client, base, case, headers)
        else:
            answer, elapsed, extra = run_platform_session(client, base, case, headers)
    except Exception as e:
        return {
            "id": case["id"],
            "module": module,
            "passed": False,
            "critical": bool(case.get("critical")),
            "elapsed": time.time() - start,
            "checks": [f"请求失败：{e}"],
            "answer": "",
            "extra": "",
        }

    passed, checks = check_answer(case, answer, elapsed, [extra] if extra else [])
    return {
        "id": case["id"],
        "module": module,
        "passed": passed,
        "critical": bool(case.get("critical")),
        "elapsed": elapsed,
        "checks": checks,
        "answer": answer,
        "extra": extra,
    }


def p95(values):
    if not values:
        return 0
    values = sorted(values)
    index = math.ceil(len(values) * 0.95) - 1
    return values[max(index, 0)]


def write_report(version, results, out_dir):
    now = datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    json_file = out_dir / f"{stamp}.json"
    md_file = out_dir / f"{stamp}.md"

    payload = {
        "version": version,
        "time": now_text(),
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "critical_failures": sum(1 for r in results if r["critical"] and not r["passed"]),
        "results": results,
    }
    json_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    modules = {}
    for result in results:
        modules.setdefault(result["module"], []).append(result)

    lines = [
        "# ctOS 2.0 测评结果",
        "",
        f"- 题库版本：{version}",
        f"- 运行时间：{now_text()}",
        f"- 通过：{payload['passed']} / {payload['total']}",
        f"- 严重失败：{payload['critical_failures']}",
        f"- 平均耗时：{sum(r['elapsed'] for r in results) / len(results):.1f}s",
        f"- P95 耗时：{p95([r['elapsed'] for r in results]):.1f}s",
        "",
        "## 分类",
        "",
        "| 模块 | 通过 | 总数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]

    for module, items in modules.items():
        ok = sum(1 for r in items if r["passed"])
        lines.append(f"| {module} | {ok} | {len(items)} | {ok / len(items) * 100:.0f}% |")

    lines += ["", "## 明细", "", "| 用例 | 模块 | 结果 | 耗时 | 检查 |",
              "| --- | --- | --- | ---: | --- |"]

    for result in results:
        mark = "✅" if result["passed"] else "❌"
        checks = "；".join(result["checks"])
        lines.append(f"| {result['id']} | {result['module']} | {mark} | "
                     f"{result['elapsed']:.1f}s | {checks} |")

    failed = [r for r in results if not r["passed"]]
    if failed:
        lines += ["", "## 失败详情", ""]
        for result in failed:
            lines += [
                f"### {result['id']}",
                "",
                f"- 检查：{'；'.join(result['checks'])}",
                f"- 回答：{short(result['answer'], 500)}",
                "",
            ]

    md_file.write_text("\n".join(lines), encoding="utf-8")
    return json_file, md_file, payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    version, cases = read_cases(args.only)
    if not cases:
        print("没有选中任何用例")
        return

    print(f"题库版本：{version}")
    print(f"接口：{base}")
    print(f"用例：{len(cases)} 条\n")

    with httpx.Client() as client:
        trial = client.post(base + "/auth/trial", timeout=20)
        trial.raise_for_status()
        token = trial.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        results = []
        for case in cases:
            print(f"跑 {case['id']} ...", end=" ", flush=True)
            result = run_case(client, base, case, headers)
            results.append(result)
            print(("PASS" if result["passed"] else "FAIL") +
                  f" {result['elapsed']:.1f}s")

    json_file, md_file, payload = write_report(version, results, RESULTS_DIR)

    print("\n结果：")
    print(f"  通过 {payload['passed']} / {payload['total']}")
    print(f"  严重失败 {payload['critical_failures']}")
    print(f"  JSON：{json_file}")
    print(f"  报告：{md_file}")


if __name__ == "__main__":
    main()
