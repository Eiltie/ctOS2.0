"""运行统计

做什么：记录每一次请求的耗时、token 用量、工具调用、结局，追加到 logs/stats.jsonl。
被谁用：
    common/llm.py          挂回调，自动拿 token
    api/main.py            中间件，记请求开始和结局
    common/tools/*.py      @tracked 装饰器，记工具调用

================================ 为什么是「追加一行 JSON」 ================================
不直接打印，也不写数据库，而是往文件里追加 JSON 行：
  · 不打印：日志一刷屏就找不着了，而且没法事后汇总
  · 不写库：统计失败不该影响业务，加表和事务是白担风险
  · JSON 行：每行独立，读的时候逐行解析，坏了跳过一行就行
后果是数据全在文件里，统计脚本可以随时重读、换个口径重算。

================================ 为什么用 contextvars ================================
一次请求里会调好多次模型和工具，这些调用要知道「我属于哪次请求」。
并发时多个请求同时在跑，不能用全局变量（会串）。
contextvars 是按协程隔离的，正是干这个用的。

注意一个坑：
  同步生成器（比如 trip 的 SSE）跑在线程池里，contextvars 传不进去。
  所以流式接口那条路径是在中间件里手动持有当前记录，见 main.py。
"""

import contextlib
import contextvars
import json
import time
import traceback
from datetime import datetime
from pathlib import Path

# 统计文件放哪：项目根下的 logs/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATS_DIR = _PROJECT_ROOT / "logs"
STATS_FILE = STATS_DIR / "stats.jsonl"

# 一次请求里，同一个工具调了多次，这里按工具名累计 [次数, 成功次数]
# 例如 {"amap": [4, 3], "weather": [1, 1]}
ToolCounts = dict[str, list[int]]

# 结局：四种。为什么分开记而不合并成「成功/失败」——
#   aborted 是用户自己关的页面，不是系统问题，和 error 混在一起会虚高故障率。
OUTCOME_OK = "ok"            # 正常跑完（含正常停在等用户操作）
OUTCOME_ERROR = "error"      # 过程中出了错
OUTCOME_ABORTED = "aborted"  # 客户中途断开（关页面、切网络）
OUTCOME_STALLED = "stalled"  # 卡住了，长时间没有新输出

# 多久没有新输出算卡住（秒）。攻略最慢一次 30~60 秒，留了余量
STALL_SECONDS = 90


class Record:
    """一次请求的累计数据。中间件开始时建一个，结束时结算。"""

    __slots__ = (
        "path", "module", "started_at", "last_output_at",
        "tokens_in", "tokens_out", "tool_counts", "model_calls",
        "saw_error", "error_message",
    )

    def __init__(self, path: str, module: str):
        self.path = path
        self.module = module
        self.started_at = time.time()
        # 最后一次「有新内容产出」的时刻，用来判断卡住
        self.last_output_at = self.started_at
        self.tokens_in = 0
        self.tokens_out = 0
        self.model_calls = 0
        self.tool_counts: ToolCounts = {}
        self.saw_error = False
        self.error_message = ""

    # ---------------------------------------------------------------- 记数

    def add_tokens(self, token_in: int = 0, token_out: int = 0) -> None:
        self.model_calls += 1
        self.tokens_in += int(token_in or 0)
        self.tokens_out += int(token_out or 0)

    def touch(self) -> None:
        """有新输出，刷新「最后一刻」的时间。判断卡住靠它。"""
        self.last_output_at = time.time()

    def add_tool(self, name: str, ok: bool) -> None:
        counts = self.tool_counts.setdefault(name, [0, 0])
        counts[0] += 1
        if ok:
            counts[1] += 1

    def mark_error(self, message: str = "") -> None:
        self.saw_error = True
        if message and not self.error_message:
            self.error_message = message[:200]

    # ---------------------------------------------------------------- 结算

    def outcome(self, aborted: bool = False) -> str:
        """判断这次请求的结局。

        顺序有讲究：
          先看有没有出错（哪怕最后被中断，也要记成 error，因为是我们的问题）；
          再看是不是被中断（用户关页面）；
          最后看卡住没有。
        """
        if self.saw_error:
            return OUTCOME_ERROR
        if aborted:
            return OUTCOME_ABORTED
        # 距最后一次输出太久，说明流程没正常收尾
        if time.time() - self.last_output_at > STALL_SECONDS:
            return OUTCOME_STALLED
        return OUTCOME_OK

    def to_json(self, aborted: bool = False) -> dict:
        elapsed = round(time.time() - self.started_at, 2)
        outcome = self.outcome(aborted)

        data = {
            "at": datetime.fromtimestamp(self.started_at).isoformat(timespec="seconds"),
            "path": self.path,
            "module": self.module,
            "outcome": outcome,
            "elapsed": elapsed,
            "model_calls": self.model_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tools": self.tool_counts,
        }
        if self.error_message:
            data["error"] = self.error_message
        return data


# 当前请求的记录。没在请求里时是 None（比如命令行跑脚本）
_current: contextvars.ContextVar[Record | None] = contextvars.ContextVar(
    "stats_record", default=None
)


def current() -> Record | None:
    """取当前请求的记录；不在请求里时返回 None。"""
    return _current.get()


def begin(path: str, module: str = "") -> Record:
    """开始记一次请求。中间件调用。"""
    record = Record(path, module)
    _current.set(record)
    return record


def finish(record: Record | None, aborted: bool = False) -> None:
    """结束并写一行 JSON。任何异常都吞掉 —— 统计失败绝不能影响业务。"""
    if record is None:
        return

    try:
        STATS_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_json(aborted), ensure_ascii=False)
        with open(STATS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # 统计坏了不该让用户的请求跟着失败
        traceback.print_exc()
    finally:
        # 必须清掉上下文。
        # 不清的话，同一个线程/协程处理下一个请求时，
        # current() 还会拿到上一个请求的记录，数据就串了。
        # 线程池复用时尤其明显。
        reset()


def reset() -> None:
    """清掉当前记录。"""
    _current.set(None)


# ============================================================
# 模型回调：挂到 LangChain 上，自动拿 token
# ============================================================

def llm_callback():
    """构造一个 LangChain 回调对象。

    llm.py 里 `self.callbacks = [...]` 挂上去就行。

    为什么用 LangChain 的回调而不是包一层客户端：
      包客户端要覆盖 invoke / stream / ainvoke 好几个方法，
      而且各处的调用方式不同（有的 .invoke()，有的 .stream()），
      漏一个就统计不到。回调是官方给的入口，全覆盖。
    """
    from langchain_core.callbacks import BaseCallbackHandler

    class _StatsCallback(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs) -> None:
            record = current()
            if record is None:
                return
            try:
                usage = _usage_of(response)
                record.add_tokens(usage.get("input_tokens", 0),
                                  usage.get("output_tokens", 0))
            except Exception:
                # 拿不到 usage 就只记次数，不影响主流程
                record.add_tokens(0, 0)

        def on_llm_error(self, error, **kwargs) -> None:
            record = current()
            if record is not None:
                record.mark_error(f"模型报错：{error}")

    return _StatsCallback()


def _usage_of(response) -> dict:
    """从 LangChain 的 LLMResult 里抠出 token 用量。

    不同厂商字段名不一样，这里都试一遍：
      DeepSeek/OpenAI 风格：token_usage.prompt_tokens / completion_tokens
      部分版本：usage_metadata.input_tokens / output_tokens
    """
    message = None
    generations = getattr(response, "generations", None) or []
    if generations and generations[0]:
        message = getattr(generations[0][0], "message", None)

    # 优先看 message.usage_metadata（新版接口）
    meta = getattr(message, "usage_metadata", None)
    if meta:
        return {
            "input_tokens": meta.get("input_tokens", 0),
            "output_tokens": meta.get("output_tokens", 0),
        }

    # 退回 response.llm_output["token_usage"]
    llm_output = getattr(response, "llm_output", None) or {}
    usage = llm_output.get("token_usage") or {}
    if usage:
        return {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }

    # 再看 response_metadata
    meta2 = getattr(message, "response_metadata", None) or {}
    usage2 = meta2.get("token_usage") or {}
    return {
        "input_tokens": usage2.get("prompt_tokens", 0),
        "output_tokens": usage2.get("completion_tokens", 0),
    }


# ============================================================
# 工具装饰器：记调用次数和成功次数
# ============================================================

def tracked(name: str):
    """给外部工具函数挂一层统计。

    用法：
        @tracked("amap")
        def find_place(...):
            ...

        # LangChain 的 @tool 对象也支持，但顺序要注意：
        @tracked("weather")     # ← 要在外层
        @tool
        def get_weather(...):
            ...

    只记「调了没有、成没成」，不改返回值也不吞异常。
    异常照样往上抛，让业务逻辑自己处理 —— 统计不能改变行为。

    两种对象都处理：
      · 普通函数：直接包
      · LangChain tool 对象：它没有 __call__，要用 invoke 才跑得起来，
        所以包一层 invoke
    """

    def decorator(target):
        # 判断是不是 LangChain tool：有 .invoke 且 .func 存在
        if hasattr(target, "invoke") and hasattr(target, "func"):
            # 不给 tool 对象本身换 invoke —— 它是 Pydantic 模型，禁止改字段。
            # 换成包装它内部的 .func：invoke() 最终就是调这个函数，
            # 包了它等于包了整条调用链。
            original_func = target.func
            wrapper = _wrap(original_func, name)

            # func 是 Pydantic 字段，允许赋值
            object.__setattr__(target, "func", wrapper)
            return target

        return _wrap(target, name)

    return decorator


def _wrap(func, name: str):
    """真正包一层的东西。普通函数和 tool 的内部函数都走这里。"""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        record = current()
        if record is None:
            # 不在请求里（命令行、单元测试）就不记，直接跑
            return func(*args, **kwargs)

        try:
            result = func(*args, **kwargs)
        except Exception:
            record.add_tool(name, False)
            raise

        record.add_tool(name, True)
        record.touch()
        return result

    return wrapper


# ============================================================
# 流式接口用：包装生成器，判断有没有中途断
# ============================================================

@contextlib.contextmanager
def streaming(record: Record):
    """包住一个流式生成器，收尾时结算。

    为什么要单独一个函数：
      生成器跑在线程池 / 事件循环里，中间件的 finally 可能在
      生成器结束之前就执行了。所以流式的结算必须在生成器自己收尾时做。

    判断中断（用户关页面）：
      生成器被外部关闭时，会抛 GeneratorExit。收到它就记 aborted。
    """
    aborted = False
    try:
        yield
    except GeneratorExit:
        # 客户端断开了
        aborted = True
        raise
    except Exception as e:
        record.mark_error(str(e))
        raise
    finally:
        finish(record, aborted=aborted)
