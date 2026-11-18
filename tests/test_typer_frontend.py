"""打字机（TypewriterText）的行为测试。

为什么单独测这件事：
  「把流式文字显示到气泡里」的地方最容易出隐蔽的 bug——
  不是报错，而是文字重复、少字，或者整段闪出来。
  上一版就是这样：后端补发了 TOKEN，又发了一份 DONE 全文，
  前端算差额时把队列里还没显示的字又推了一遍，页面上同一段话出现两遍。

现在测的是新前端 web/src/shared/lib/typewriter.js 里的
「合并逻辑」（合并放在纯函数里，可以脱离浏览器直接跑）。

为什么要能单独跑这个函数：
  这个逻辑以前散在 DOM 操作里，只能靠模拟 DOM 去测。
  搬成纯函数之后，node 直接跑就行，不依赖 DOM、不依赖 Vue。

注意：新前端还没开始写时，这个测试会**跳过**而不是报错。
这样做是为了让 CI 在过渡期不红。
前端写好后，PATH 指向真实文件，测试自动生效。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 合并逻辑所在的文件（新前端的纯函数模块）
MERGE_JS = ROOT / "web" / "src" / "shared" / "lib" / "typewriter.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not MERGE_JS.exists(),
    reason="需要 node 和新前端的 typewriter 模块（还没写时跳过）",
)

TEXT = "你好，我是 ctOS 的智能客服。我只负责回答关于这个项目本身的问题。"


# 跑一段 node：导入真实的合并函数，喂入 tokens 和 done，输出最终文字
HARNESS = """
import { mergeStreamText } from %(module)s;

const tokens = %(tokens)s;
const done = %(done)s;
console.log(JSON.stringify({ text: mergeStreamText(tokens, done) }));
"""


def _run_merge(tmp_path, tokens, done):
    """跑真实的合并函数，返回最终应该显示的文字。"""
    spec = json.dumps(str(MERGE_JS.as_uri()))
    script = HARNESS % {
        "module": spec,
        "tokens": json.dumps(tokens, ensure_ascii=False),
        "done": json.dumps(done, ensure_ascii=False),
    }
    harness = tmp_path / "harness.mjs"
    harness.write_text(script, encoding="utf-8")

    out = subprocess.run(
        ["node", str(harness)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert out.returncode == 0, f"node 运行失败：{out.stderr[:800]}"
    return json.loads(out.stdout.strip().splitlines()[-1])["text"]


def test_no_duplicate_when_backend_sends_tokens_and_done(tmp_path):
    """后端补发了 TOKEN，又发 DONE 全文时，不能出现两遍。

    这正是修复前的现象：DONE 用「已显示字数」算差额，
    结果把队列里还没显示的字又推了一遍。
    """
    tokens = [TEXT[i:i + 2] for i in range(0, len(TEXT), 2)]
    assert _run_merge(tmp_path, tokens, TEXT) == TEXT


def test_no_duplicate_with_model_stream(tmp_path):
    """模型流式（TOKEN 长度不固定）+ DONE 全文，同样不能重复。"""
    tokens = [TEXT[:10], TEXT[10:30], TEXT[30:]]
    assert _run_merge(tmp_path, tokens, TEXT) == TEXT


def test_done_only_without_tokens(tmp_path):
    """一个 TOKEN 都没有、只有 DONE 时（客服的固定话术就是这样），文字要完整。"""
    assert _run_merge(tmp_path, [], TEXT) == TEXT


def test_done_wins_when_it_contradicts_tokens(tmp_path):
    """模型中途改口（DONE 和 TOKEN 对不上）时，以定稿为准。"""
    assert _run_merge(tmp_path, ["完全不一样的开头"], TEXT) == TEXT
