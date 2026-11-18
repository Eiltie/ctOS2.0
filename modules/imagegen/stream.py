"""生图｜模块对外唯一出口

做什么：把一句话交给生图图，跑完（或暂停）返回结果。
被谁用：命令行 `cli.py`；将来接闲聊和出行也走这里。

两个入口：
    generate_image(query, ...)   跑一次；需求不足时返回 need_more 和线程号
    resume_image(thread_id, ...) 用户回答了提问，接着跑

为什么分成两个：
    图会停在 interrupt 上，现场存在检查点里。
    调用方拿到线程号，下一轮用同一个线程号恢复，不能重开新会话。
"""

import uuid

from langgraph.types import Command

from modules.imagegen.graph import image_checkpointer, image_graph
from modules.imagegen.state import STATUS_NEED_MORE


def _new_thread_id() -> str:
    """生图线程号统一加前缀，和出行的 route- / guide- 分开。"""
    return "image-" + uuid.uuid4().hex


def _interrupt_of(snapshot):
    """从一次运行的结果里取出 interrupt 的内容和线程号。"""
    interrupts = snapshot.get("__interrupt__") or []
    if not interrupts:
        return None

    first = interrupts[0]
    return getattr(first, "value", None)


def run_graph(query, history=None, tenant_id=None, thread_id=None):
    """跑一次生图图，返回一个结果字典。

    返回：
        {
          "status": "ok" | "need_more" | "api_failed" | "prompt_failed",
          "thread_id": "image-xxx",     # need_more 时调用方要留着这个
          "question": "想画点什么…",     # need_more 时给用户看的问题
          "image_path": "...",          # ok 时的绝对路径
          "image_url": "generated/xx",  # ok 时的相对地址
          "spec": {...},                # 结构化规格，便于调试
          "prompt": "...",              # 实际发出去的提示词
          "problem": "",                # 失败原因
        }
    """
    tid = thread_id or _new_thread_id()
    config = {"configurable": {"thread_id": tid}}

    initial = {
        "user_query": (query or "").strip(),
        "history": list(history or []),
        "tenant_id": tenant_id,
        "asked_once": False,
    }

    try:
        snapshot = image_graph.invoke(initial, config)
    except Exception as e:
        return {
            "status": "api_failed",
            "thread_id": tid,
            "problem": f"生图流程没跑通：{e}",
        }

    result = _build_result(snapshot, tid)

    # 跑完了就把检查点删掉，别留垃圾
    if result["status"] != STATUS_NEED_MORE:
        _drop_thread(tid)

    return result


def resume_image(thread_id, answer, tenant_id=None):
    """用户回答了提问，接着跑，返回结果。

    参数不对（线程号不存在、不是本租户的）时返回一条明确的错误，
    不要抛异常——调用方多半在流式接口里，抛出去用户只看到 500。
    """
    if not thread_id:
        return {"status": "api_failed", "problem": "没有会话号，无法继续"}

    config = {"configurable": {"thread_id": thread_id}}
    snapshot = image_graph.get_state(config)

    if not snapshot.values:
        return {"status": "api_failed", "problem": "这次生图已经失效了，请重新说一次"}

    saved_tenant = snapshot.values.get("tenant_id")
    if saved_tenant is not None and tenant_id is not None and saved_tenant != tenant_id:
        return {"status": "api_failed", "problem": "这次生图不属于当前账号"}

    try:
        out = image_graph.invoke(Command(resume=str(answer or "")), config)
    except Exception as e:
        return {"status": "api_failed", "problem": f"继续生图失败：{e}"}

    result = _build_result(out, thread_id)

    if result["status"] != STATUS_NEED_MORE:
        _drop_thread(thread_id)

    return result


def _build_result(snapshot, thread_id) -> dict:
    """把图的最终状态整理成调用方能直接用的形状。"""
    values = snapshot if isinstance(snapshot, dict) else {}

    # 停在 interrupt：还没跑完，信息不够
    interrupt_value = _interrupt_of(values)
    if interrupt_value is not None:
        question = ASK_FALLBACK
        if isinstance(interrupt_value, dict):
            question = interrupt_value.get("question") or ASK_FALLBACK

        return {
            "status": STATUS_NEED_MORE,
            "thread_id": thread_id,
            "question": question,
        }

    return {
        "status": values.get("status") or "api_failed",
        "thread_id": thread_id,
        "image_path": values.get("image_path") or "",
        "image_url": values.get("image_url") or "",
        "spec": values.get("spec") or {},
        "prompt": values.get("final_prompt") or "",
        "size": values.get("size") or "",
        "problem": values.get("problem") or "",
    }


ASK_FALLBACK = "你想画点什么？"


def _drop_thread(thread_id):
    """删检查点，失败只打印。"""
    try:
        image_checkpointer.delete_thread(thread_id)
    except Exception as e:
        print(f"[生图] 清理检查点失败（不影响结果）：{e}")
