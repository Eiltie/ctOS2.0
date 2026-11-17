"""打字机（typer.js）的行为测试。

为什么要测这个文件：
  它是前端唯一负责「把流式文字显示到气泡里」的地方，改错的表现很隐蔽——
  不是报错，而是文字重复、少字、或者整段闪出来。
  上一轮的 bug 就是这样：DONE 到达时用「已显示字数」去推算还差多少，
  但打字机是匀速往外放的，那时队列里还积着一大段没显示的字，
  于是同一段话被推了两遍，页面上就是重复一遍。

用 node 跑真实的 typer.js，套一个最小 DOM 模拟，不依赖浏览器。
"""

import json
import subprocess
import shutil
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TYPER_JS = ROOT / "static" / "shared" / "js" / "common" / "typer.js"
CONFIG_JS = ROOT / "static" / "shared" / "js" / "common" / "config.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="需要 node 才能跑前端逻辑测试",
)

HARNESS = textwrap.dedent("""
    // ---- 最小 DOM 模拟 ----
    class FakeNode {
      constructor(tag){
        this.tagName = tag; this.children = []; this.className = "";
        this.parentNode = null; this._classes = new Set();
        this.classList = {
          add: (c) => this._classes.add(c),
          remove: (c) => this._classes.delete(c),
          toggle: (c, on) => { on ? this._classes.add(c) : this._classes.delete(c); },
          contains: (c) => this._classes.has(c),
        };
      }
      appendChild(c){ this.children.push(c); c.parentNode = this; return c; }
      removeChild(c){ this.children = this.children.filter(x => x !== c); c.parentNode = null; }
      get isConnected(){ return true; }
      get textContent(){ return this.children.map(c => c.data ?? c.textContent ?? "").join(""); }
      set textContent(v){ this.children = []; if (v) this.children.push({ data: String(v) }); }
      set innerHTML(v){ this.innerHTMLValue = v; }
    }

    global.requestAnimationFrame = (fn) => setTimeout(fn, 16);
    global.cancelAnimationFrame = (id) => clearTimeout(id);
    global.document = {
      createTextNode: (t) => ({ data: t }),
      createElement: (tag) => new FakeNode(tag),
    };

    const feed = new FakeNode("div");
    const bubble = new FakeNode("div");
    feed.appendChild(bubble);

    function esc(s){ return String(s); }

    const typer = createTyper(feed, bubble);

    const TOKENS = %TOKENS%;
    const FINAL = %FINAL%;

    for (const t of TOKENS) typer.push(t);
    typer.pushRemaining(FINAL);

    setTimeout(() => {
      typer.done();
      setTimeout(() => {
        const shown = bubble.textContent || bubble.innerHTMLValue || "";
        console.log(JSON.stringify({ shown }));
      }, 2500);
    }, 400);
""")


def _run_typer(tmp_path, tokens, final):
    """跑一次真实 typer.js，返回最终显示到气泡里的文字。"""
    source = TYPER_JS.read_text(encoding="utf-8")
    config = CONFIG_JS.read_text(encoding="utf-8")
    script = (config + "\n" + source + "\n"
              + HARNESS
              .replace("%TOKENS%", json.dumps(tokens, ensure_ascii=False))
              .replace("%FINAL%", json.dumps(final, ensure_ascii=False)))
    harness = tmp_path / "harness.js"
    harness.write_text(script, encoding="utf-8")

    out = subprocess.run(
        ["node", str(harness)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert out.returncode == 0, f"node 运行失败：{out.stderr[:800]}"
    return json.loads(out.stdout.strip().splitlines()[-1])["shown"]


TEXT = "你好，我是 ctOS 的智能客服。我只负责回答关于这个项目本身的问题。"


def test_no_duplicate_when_backend_sends_tokens_and_done(tmp_path):
    """后端补发了 TOKEN，又发 DONE 全文时，页面不能出现两遍。

    这正是修复前的现象：DONE 用「已显示字数」算差额，
    结果把队列里还没显示的字又推了一遍。
    """
    tokens = [TEXT[i:i + 2] for i in range(0, len(TEXT), 2)]
    assert _run_typer(tmp_path, tokens, TEXT) == TEXT


def test_no_duplicate_with_model_stream(tmp_path):
    """模型流式（TOKEN 长度不固定）+ DONE 全文，同样不能重复。"""
    tokens = [TEXT[:10], TEXT[10:30], TEXT[30:]]
    assert _run_typer(tmp_path, tokens, TEXT) == TEXT


def test_done_only_without_tokens(tmp_path):
    """一个 TOKEN 都没有、只有 DONE 时，文字要完整显示出来。"""
    assert _run_typer(tmp_path, [], TEXT) == TEXT


def test_done_wins_when_it_contradicts_tokens(tmp_path):
    """模型中途改口（DONE 和 TOKEN 对不上）时，以定稿为准。"""
    assert _run_typer(tmp_path, ["完全不一样的开头"], TEXT) == TEXT
