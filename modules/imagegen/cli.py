"""生图｜命令行入口

做什么：不依赖任何前端/接口，直接在终端里和生图图对话。
被谁用：调试。验证「这张图能不能自己跑完」。

两种运行方式都支持：
    直接跑文件    python modules/imagegen/cli.py
    当模块跑      python -m modules.imagegen.cli

带参数只跑一次：
    python modules/imagegen/cli.py "画一只橘猫在窗台上"
"""

import sys
from pathlib import Path

# 直接跑本文件时（python cli.py），sys.path 里是 modules/imagegen，
# 找不到 `modules.xxx`。把项目根补进去，让两种运行方式都能导入。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modules.imagegen.state import STATUS_NEED_MORE, STATUS_OK  # noqa: E402
from modules.imagegen.stream import resume_image, run_graph  # noqa: E402

BANNER = """==================================================
 生图 Agent（命令行版）
 直接说想画什么；需求太笼统会先问你一句
 输入 /exit 退出，/spec 查看上一次的结构化规格
==================================================
"""


def show_result(result, verbose=True):
    """把结果打到终端。"""
    status = result.get("status")

    if status == STATUS_OK:
        print(f"\n  出图成功")
        if verbose:
            print(f"  规格：{format_spec(result.get('spec'))}")
            print(f"  提示词（{len(result.get('prompt') or '')} 字）：{result.get('prompt')}")
            print(f"  尺寸：{result.get('size')}")
        print(f"  文件：{result.get('image_path')}\n")
        return True

    if status == STATUS_NEED_MORE:
        print(f"\n  需要更多信息：{result.get('question')}")
        print(f"  （线程 {result.get('thread_id', '')[:16]}…）\n")
        return True

    print(f"\n  失败：{result.get('problem')}\n")
    return False


def format_spec(spec):
    """规格打一行，空的字段跳过。"""
    if not spec:
        return "（空）"

    labels = (
        ("subject", "主体"), ("action", "动作"), ("scene", "场景"),
        ("style", "风格"), ("lighting", "光线"), ("aspect", "比例"),
        ("text_in_image", "图内文字"), ("negative", "不要"),
    )

    parts = [f"{name}={spec.get(key)}" for key, name in labels if spec.get(key)]
    return "  ".join(parts) if parts else "（空）"


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    args = sys.argv[1:]

    # ---- 带参数：跑一次就退出 ----
    if args:
        query = " ".join(args).strip()
        print(f"需求：{query}\n")
        result = run_graph(query)

        # 需要更多信息时，直接在终端里问
        while result.get("status") == STATUS_NEED_MORE:
            show_result(result)
            answer = input("  > ").strip()
            if not answer:
                print("  没输入，放弃\n")
                return
            result = resume_image(result["thread_id"], answer)

        show_result(result)
        return

    # ---- 交互模式 ----
    print(BANNER)

    history = []
    last_result = None

    while True:
        try:
            line = input("想画 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not line:
            continue
        if line == "/exit":
            print("再见。")
            break
        if line == "/spec":
            if last_result:
                print(f"  {format_spec(last_result.get('spec'))}\n")
            else:
                print("  还没画过\n")
            continue

        result = run_graph(line, history=history)

        # 图上停下来了，在终端里接着答
        while result.get("status") == STATUS_NEED_MORE:
            show_result(result)
            try:
                answer = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                answer = ""
            if not answer:
                print("  没输入，这轮放弃\n")
                break
            result = resume_image(result["thread_id"], answer)

        show_result(result)
        last_result = result

        if result.get("status") == STATUS_OK:
            history.append(line)


if __name__ == "__main__":
    main()
