"""角色记忆：每聊 6 轮，把最近对话压缩成一段短摘要。

不用存完整对话，只存摘要，这样：
    - 数据库小
    - 下次塞进提示词不会太长
    - 角色还能记得上次聊过什么
"""

from core.llm import get_llm
from databases.db_roleplay import get_memory, get_role_messages, save_memory
from modules.roleplay.prompts import build_summary_prompt

# 摘要最多留 200 字，太长了反而记不住重点
MEMORY_LIMIT = 200

# 整理记忆要稳一点，不需要活泼
SUMMARY_TEMPERATURE = 0.3


def format_lines(rows):
    """把消息列表拼成“用户：…… / 角色：……”的文本。"""
    lines = []
    for row in rows:
        who = "用户" if row["role"] == "user" else "角色"
        lines.append(f"{who}：{row['content']}")
    return "\n".join(lines)


async def refresh_memory(tenant_id, role_id, role_name):
    """重新整理这个角色的记忆；失败只打印，不影响聊天。"""
    try:
        old_memory = get_memory(tenant_id, role_id)
        rows = get_role_messages(tenant_id, role_id, limit=12)
        if not rows:
            return

        prompt = build_summary_prompt(role_name, old_memory, format_lines(rows))
        result = await get_llm(temperature=SUMMARY_TEMPERATURE).ainvoke(prompt)
        text = (result.content or "").strip()

        if text:
            save_memory(tenant_id, role_id, text[:MEMORY_LIMIT])
    except Exception as e:
        print(f"[角色记忆] 更新失败：{e}")
