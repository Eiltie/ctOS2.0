"""角色扮演的提示词：角色对话，以及把对话整理成记忆。"""


def build_role_prompt(role, memory=""):
    """把角色档案拼成一段提示词。

    memory 是这个角色记住的事，没有就留空。
    """
    memory_part = ""
    if memory:
        memory_part = f"【你还记得】{memory}\n"

    def line(label, value):
        value = (value or "").strip()
        return f"【{label}】{value}\n" if value else ""

    profile = (
        line("年龄", role.get("age"))
        + line("性别", role.get("gender"))
        + line("性格", role.get("personality"))
        + line("人物事迹", role.get("deeds"))
        + line("背景故事", role.get("background"))
        + line("补充说明", role.get("extra"))
        + line("说话方式", role.get("speaking"))
    )

    return (
        f"你正在扮演“{role['name']}”。\n"
        f"{profile}"
        f"【不会做的事】{role.get('boundaries', '')}\n"
        f"{memory_part}"
        f"【开场白】{role.get('opening', '')}\n"
        "\n"
        "【规则】\n"
        "1. 始终用第一人称，保持这个角色的口吻。\n"
        "2. 不要承认自己是 AI、模型或程序，也不要解释“我在扮演”。\n"
        "3. 像真人聊天一样，一次说 2 到 5 句，不要长篇大论。\n"
        "4. 不知道的事用角色的方式带过，不要编造事实。\n"
        "5. 如果上面写了“你还记得”，可以自然地带出来，但不要逐条复述。\n"
    )


def build_summary_prompt(role_name, old_memory, lines):
    """把旧记忆和最近对话整理成一段很短的新记忆。

    lines 是已经拼好的“用户：…… / 角色：……”文本。
    """
    old_part = old_memory if old_memory else "（还没有记忆）"

    return (
        f"你在帮角色“{role_name}”整理记忆。\n"
        "把下面的旧记忆和最近对话压缩成一段 200 字以内的摘要。\n"
        "只保留：用户的重要信息（身份、困扰、喜好、目标）、角色答应过的事、正在发生的事。\n"
        "不要写客套话，不要编造，用第三人称写。\n"
        "\n"
        f"【旧记忆】\n{old_part}\n"
        "\n"
        f"【最近对话】\n{lines}\n"
        "\n"
        "只输出新的摘要，不要加标题或解释。"
    )
