"""提示词生成的终端入口：跑这个文件就能看「一句话需求 → 生图提示词」。

    python -X utf8 -m cli.prompts

只跑提示词 agent，不调生图接口、不花钱画图。
输入 exit 退出。
"""

from modules.generatePrompts.createGraph import create

# 图只建一次，循环里反复用
app = create()


def main():
    print("提示词生成（输入 exit 退出）")
    print("例如：画一只橘猫坐在窗台上，水彩风格")

    while True:
        try:
            requirement = input("\n需求：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if requirement.lower() in ("exit", "quit", "q", "退出"):
            print("再见！")
            break
        if not requirement:
            continue

        try:
            result = app.invoke({"requirement": requirement, "images": []})
        except Exception as e:
            print(f"\n（这次没跑通：{e}）")
            continue

        if result.get("status") == "ok" and result.get("prompt"):
            print("\n提示词：")
            print(result["prompt"])
        else:
            print(f"\n（没能写出提示词：{result.get('problem') or '原因未知'}）")


if __name__ == "__main__":
    main()
