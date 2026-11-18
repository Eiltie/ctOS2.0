"""
端到端测试套件 —— 用真实浏览器 + 真实后端，验证「点击之后会发生什么」。

================================================================================
为什么要有这个
================================================================================
之前是靠截图看效果。截图只能看到某一瞬间的样子，看不到「点击后 300 毫秒里发生了什么」，
于是出现了「点会话会闪一下加载中」这种 bug —— 截图看不出来，只有连续观察才能发现。

这组测试解决的就是这个问题：驱动真实界面，观察一段时间内的行为，断言结果。
改完代码跑一遍，就知道有没有把别的地方弄坏。

================================================================================
怎么跑
================================================================================
    # 全部跑（推荐）
    venv\\Scripts\\python.exe -X utf8 web/scripts/e2e/run_all.py

    # 只跑某一组
    venv\\Scripts\\python.exe -X utf8 web/scripts/e2e/run_all.py chat
    venv\\Scripts\\python.exe -X utf8 web/scripts/e2e/run_all.py roleplay

前置条件：
    1. 后端在跑（默认 8082）
       PORT=8082 python -X utf8 -m api.main
    2. 前端已构建（static/dist 存在）
       cd web && npm run build
    3. 有自己的 Python venv（装了 playwright + 系统 Chrome）

================================================================================
加新测试怎么写
================================================================================
    1. 在下面 GROUPS 里写一个 test_xxx 函数
    2. 用 `await api.call(page, ...)` 造数据、`page.click` 驱动界面
    3. 用 `check(...)` 断言，失败会记账而不是立刻中断 —— 一次能看到所有问题

================================================================================
几条约定
================================================================================
    · 测试会**真的发消息给模型**，会花钱。默认只在关键路径上发一两句。
    · 每个测试自己造数据、自己清理，不依赖数据库里已有什么。
    · 断言用 check(条件, 说明)，不要用 assert —— 这样一次能报出多个失败点。
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

# ============================================================================
# 配置
# ============================================================================

BASE = os.environ.get("CTOS_BASE", "http://127.0.0.1:8082")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT
DIST_INDEX = PROJECT_ROOT / "static" / "dist" / "index.html"

# ============================================================================
# 记账
# ============================================================================

RESULTS = []  # [(test_name, ok, detail)]
CURRENT = {"name": "", "failures": []}


def begin(name: str):
    CURRENT["name"] = name
    CURRENT["failures"] = []
    print(f"\n  ▸ {name}")


def check(condition: bool, message: str):
    """断言。失败会记账，不中断，这样一次能报出所有问题。"""
    if condition:
        print(f"      ✓ {message}")
    else:
        print(f"      ✗ {message}")
        CURRENT["failures"].append(message)


def end():
    ok = not CURRENT["failures"]
    RESULTS.append((CURRENT["name"], ok, CURRENT["failures"]))
    return ok


# ============================================================================
# 辅助
# ============================================================================


def make_token() -> str:
    """在项目 venv 里签一个 token（测试用，走本机数据库）。"""
    sys.path.insert(0, str(BACKEND_DIR))
    from common.auth import create_token  # noqa: PLC0415
    from common.db import query_one  # noqa: PLC0415

    row = query_one(
        "SELECT u.id, u.tenant_id, u.email FROM users u "
        "JOIN sessions s ON s.tenant_id = u.tenant_id "
        "GROUP BY u.id, u.tenant_id, u.email "
        "ORDER BY COUNT(s.id) DESC LIMIT 1"
    )
    if not row:
        raise RuntimeError("数据库里没有带会话的账号，先手动聊几句")
    return create_token(row["id"], row["tenant_id"], row["email"])


class Api:
    """直接调后端接口造测试数据（绕过界面，快且稳）。"""

    def __init__(self, token: str):
        self.token = token

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            BASE + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def post(self, path: str, body: dict | None = None) -> dict:
        return self._request("POST", path, body or {})

    def delete(self, path: str) -> dict:
        return self._request("DELETE", path)


async def login(page, token: str):
    """把 token 塞进本地存储，然后刷新，让前端用它启动。"""
    await page.goto(BASE, wait_until="networkidle")
    await page.wait_for_timeout(300)
    await page.evaluate("(t) => localStorage.setItem('ctos_token', t)", token)
    await page.reload(wait_until="networkidle")
    await page.wait_for_timeout(1500)


async def sample(page, setup_js: str, action, duration_ms: int = 1800) -> list[dict]:
    """
    连续采样。

    在页面里每 30ms 记录一次状态，执行 action，返回采样结果。
    这是发现「闪一下」这类问题的关键手段。
    """
    await page.evaluate(
        f"""() => {{
            window.__samples = [];
            window.__sampling = true;
            const probe = () => ({setup_js});
            const tick = () => {{
                if (!window.__sampling) return;
                window.__samples.push(probe());
                setTimeout(tick, 30);
            }};
            tick();
        }}"""
    )

    await action
    await page.wait_for_timeout(duration_ms)

    return await page.evaluate(
        "() => { window.__sampling = false; return window.__samples; }"
    )


# ============================================================================
# 测试：基础设施
# ============================================================================


async def test_page_loads(page, api):
    begin("页面能打开，没有任何报错")

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    await page.goto(BASE, wait_until="networkidle")
    await page.wait_for_timeout(1500)

    check(await page.locator(".shell").count() > 0, "壳层渲染出来了")
    check(await page.locator(".topbar").count() > 0, "顶栏渲染出来了")
    check(len(errors) == 0, f"没有 JS 报错（实得 {len(errors)} 个）")
    end()


async def test_contract_matches(page, api):
    """契约测试不需要浏览器，直接问后端就行。

    之前在这里犯过一次错：用 page.evaluate 里的相对路径 fetch，
    page 还停在 about:blank，没有 base URL，跨域直接被拦。
    这种「和浏览器无关的检查」不该塞进浏览器里做。
    """
    begin("后端契约可用")

    try:
        with urllib.request.urlopen(BASE + "/contract", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        check(False, f"/contract 请求失败：{e}")
        end()
        return

    check("api" in data, "契约里有 api 段")
    check("sse_kinds" in data, "契约里有 sse_kinds 段")
    check(len(data.get("api", {})) > 20, f"接口数 > 20（实得 {len(data.get('api', {}))}）")
    check(len(data.get("sse_kinds", {})) >= 11, f"事件类型 >= 11（实得 {len(data.get('sse_kinds', {}))}）")
    end()


# ============================================================================
# 测试：闲聊
# ============================================================================


async def test_chat_list_loads(page, api):
    begin("闲聊：会话列表能加载")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1800)

    count = await page.locator(".session-item").count()
    check(count > 0, f"列表里有会话（实得 {count} 条）")

    # 列表出现之后不应该再显示「加载中」
    loading = await page.locator(".list-loading").count()
    check(loading == 0, "加载完成后不再显示「加载中」")
    end()


async def test_switch_session_no_flicker(page, api):
    begin("闲聊：切换会话时列表不闪烁")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1800)

    if await page.locator(".session-item").count() < 2:
        check(False, "至少要有 2 个会话才能测切换")
        end()
        return

    # 采样：列表是否闪「加载中」、列表条目是否归零、是否出现骨架
    samples = await sample(
        page,
        """{
            loading: (document.querySelector('.list-loading')?.innerText ?? '').includes('加载中'),
            items: document.querySelectorAll('.session-item').length,
            skeleton: document.querySelectorAll('.skeleton-row').length,
        }""",
        page.locator(".session-item").nth(1).click(),
    )

    loading_hits = sum(1 for s in samples if s["loading"])
    empty_hits = sum(1 for s in samples if s["items"] == 0)

    check(len(samples) > 10, f"采样到了足够的数据（{len(samples)} 次）")
    check(loading_hits == 0, f"列表没有闪「加载中」（实得 {loading_hits} 次）")
    check(empty_hits == 0, f"列表条目没有归零（实得 {empty_hits} 次）")
    end()


async def test_open_session_shows_messages(page, api):
    begin("闲聊：点会话能显示消息")

    sessions = api.get("/sessions")
    if not sessions:
        check(False, "没有会话可测")
        end()
        return

    # 找一个有消息的会话
    target = None
    for s in sessions:
        msgs = api.get(f"/sessions/{s['id']}/messages")
        if msgs:
            target = s
            break

    if target is None:
        check(False, "没有带消息的会话")
        end()
        return

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1800)

    # 点开那个会话
    item = page.locator(".session-item").filter(has_text=target["title"]).first
    if await item.count() == 0:
        check(False, "列表里找不到目标会话")
        end()
        return

    await item.click()
    await page.wait_for_timeout(1500)

    rendered = await page.locator(".msg").count()
    check(rendered > 0, f"页面上渲染出消息（实得 {rendered} 条）")
    end()


# ============================================================================
# 测试：角色扮演
# ============================================================================


async def test_roleplay_picker(page, api):
    begin("角色扮演：角色卡片能加载")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat/roles", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    cards = await page.locator(".role-card:not(.role-card--add)").count()
    check(cards >= 3, f"至少有 3 张角色卡（实得 {cards}）")

    names = await page.locator(".role-name").all_inner_texts()
    check("孙悟空" in names, f"预设角色里有孙悟空（实得 {names}）")
    end()


async def test_roleplay_start_chat(page, api):
    begin("角色扮演：选角色能开始对话")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat/roles", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    if await page.locator(".role-name").count() == 0:
        check(False, "没有角色可选")
        end()
        return

    await page.locator(".role-name").first.click()
    await page.wait_for_timeout(2500)

    # 应该跳到 /chat，标题是角色名，副标题是「角色扮演」
    check("/chat" in page.url, f"跳到了对话页（实得 {page.url}）")

    title = await page.locator(".chat-title").inner_text()
    check(len(title.strip()) > 0, f"标题有内容（实得 {title!r}）")

    sub = await page.locator(".chat-sub").inner_text()
    check("角色扮演" in sub, f"副标题标明是角色扮演（实得 {sub!r}）")

    # 角色会话应该有「档案 / 记忆 / 换个角色」按钮
    actions = await page.locator(".chat-head-actions button").count()
    check(actions >= 3, f"显示角色专属按钮（实得 {actions} 个）")

    # 开场白应该在页面上
    msgs = await page.locator(".msg").count()
    check(msgs > 0, f"开场白显示出来了（实得 {msgs} 条消息）")
    end()


async def test_roleplay_panels(page, api):
    begin("角色扮演：档案和记忆面板能打开")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat/roles", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    if await page.locator(".role-name").count() == 0:
        check(False, "没有角色可选")
        end()
        return

    await page.locator(".role-name").first.click()
    await page.wait_for_timeout(2500)

    # 档案
    await page.locator(".chat-head-actions button").filter(has_text="档案").click()
    await page.wait_for_timeout(1200)
    check(await page.locator(".panel").count() > 0, "档案面板打开了")
    profile_fields = await page.locator(".profile-fields dt").count()
    check(profile_fields > 0, f"档案里有字段（实得 {profile_fields} 个）")
    await page.locator(".panel-close").click()
    await page.wait_for_timeout(600)

    # 记忆
    await page.locator(".chat-head-actions button").filter(has_text="记忆").click()
    await page.wait_for_timeout(1200)
    check(await page.locator(".panel").count() > 0, "记忆面板打开了")
    await page.locator(".panel-close").click()
    await page.wait_for_timeout(400)
    end()


async def test_role_form_validation(page, api):
    begin("角色扮演：新建表单的校验")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat/roles", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    await page.locator(".role-card--add").first.click()
    await page.wait_for_timeout(800)

    check(await page.locator(".panel").count() > 0, "表单打开了")

    # 名字为空时，创建按钮应该是禁用的
    btn = page.locator(".primary-btn")
    disabled = await btn.is_disabled()
    check(disabled, "名字为空时「创建角色」不可点")

    # 填了名字就可以点
    await page.locator(".panel input.input").nth(1).fill("测试角色")
    await page.wait_for_timeout(300)
    now_disabled = await btn.is_disabled()
    check(not now_disabled, "填了名字后可以点")

    # 取消关闭，不保存
    await page.locator(".panel .ghost-btn").click()
    await page.wait_for_timeout(600)
    check(await page.locator(".panel").count() == 0, "取消后面板关闭了")
    end()


# ============================================================================
# 测试：导航
# ============================================================================


async def test_navigation(page, api):
    begin("导航：三个模块能互相切换")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    # 出行
    await page.locator(".tab").filter(has_text="出行").click()
    await page.wait_for_timeout(1200)
    check("/trip" in page.url, f"切到出行（实得 {page.url}）")

    # 客服
    await page.locator(".tab").filter(has_text="客服").click()
    await page.wait_for_timeout(1200)
    check("/customer" in page.url, f"切到客服（实得 {page.url}）")

    # 回对话
    await page.locator(".tab").filter(has_text="对话").click()
    await page.wait_for_timeout(1200)
    check("/chat" in page.url, f"切回对话（实得 {page.url}）")
    end()


async def test_playmode_bar(page, api):
    begin("玩法条：能在闲聊和角色扮演之间切换")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    await page.locator(".mode").filter(has_text="角色扮演").click()
    await page.wait_for_timeout(1500)
    check("/chat/roles" in page.url, f"切到角色扮演玩法（实得 {page.url}）")

    await page.locator(".mode").filter(has_text="闲聊").click()
    await page.wait_for_timeout(1500)
    check(page.url.rstrip("/").endswith("/chat"), f"切回闲聊（实得 {page.url}）")
    end()


# ============================================================================
# 测试：发消息（会花钱，默认只在关键路径跑一句）
# ============================================================================


async def test_send_message(page, api):
    begin("闲聊：发消息能收到流式回复")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1800)

    box = page.locator("textarea")
    await box.fill("只回答两个字：收到")
    await box.press("Enter")

    # 立刻检查：用户消息应该马上出现，发送按钮变成停止
    await page.wait_for_timeout(600)
    user_msgs = await page.locator(".msg--me").count()
    check(user_msgs > 0, "用户消息立刻显示")

    # 等回复
    try:
        await page.wait_for_function(
            """() => {
                const els = document.querySelectorAll('.msg--ai .msg-bubble');
                return els.length > 0 && els[els.length - 1].textContent.trim().length > 1;
            }""",
            timeout=90_000,
        )
        reply = await page.locator(".msg--ai .msg-bubble").last.inner_text()
        check(len(reply.strip()) > 0, f"收到回复（{reply.strip()[:40]!r}）")
    except Exception:
        check(False, "90 秒内没收到回复")

    # 结束后输入框应该恢复可用
    await page.wait_for_timeout(800)
    stop_btn = await page.locator(".composer-send--stop").count()
    check(stop_btn == 0, "生成结束后「停止」按钮消失")
    end()


# ============================================================================
# 测试：图片上传
# ============================================================================


def make_test_png(name: str = "test.png") -> Path:
    """
    生成一张最小的合法 PNG 用作上传测试。

    为什么不用现成的图片文件：
       测试不该依赖仓库里有没有某个图片。
       这里手写 PNG 字节，任何时候都能造出来。

    注意不要在 Windows 上用 TemporaryDirectory：
       浏览器上传后可能还占着句柄，退出时清理会报 PermissionError。
       统一放到一个固定目录，跑完不删（几 KB 而已）。
    """
    import struct
    import zlib

    width = height = 8
    # 每行：1 字节 filter(0) + width*3 字节 RGB
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")

    tmp_dir = Path(tempfile.gettempdir()) / "ctos-e2e"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / name
    path.write_bytes(png)
    return path


async def test_image_upload(page, api):
    begin("闲聊：可以上传图片并发出去")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1800)

    # 相机按钮应该在
    pic_btn = page.locator(".composer-icon[title='上传图片']")
    check(await pic_btn.count() > 0, "输入框旁边有上传图片按钮")

    if await pic_btn.count() == 0:
        end()
        return

    # 造一张图，通过隐藏的 file input 上传
    img = make_test_png("upload.png")
    await page.locator("input[type='file']").set_input_files(str(img))

    # 等上传完成：待发区出现缩略图
    try:
        await page.wait_for_selector(".pending-item .attachment-img", timeout=30_000)
        check(True, "上传后有缩略图预览")
    except Exception:
        check(False, "上传后没看到缩略图")
        end()
        return

    # 只发图不打字
    await page.locator("textarea").press("Enter")

    # 用户消息里应该出现图片
    await page.wait_for_timeout(1500)
    user_imgs = await page.locator(".msg--me .attachment-img").count()
    check(user_imgs > 0, f"发出的消息里有图片（实得 {user_imgs} 张）")

    # 待发区应该清空
    pending = await page.locator(".pending-item").count()
    check(pending == 0, f"发出去后待发区清空（实得 {pending} 个）")

    # 等模型回复（带图会慢一些）
    try:
        await page.wait_for_function(
            """() => {
                const els = document.querySelectorAll('.msg--ai .msg-bubble');
                return els.length > 0 && els[els.length - 1].textContent.trim().length > 1;
            }""",
            timeout=120_000,
        )
        reply = await page.locator(".msg--ai .msg-bubble").last.inner_text()
        check(True, f"模型回复了（{reply.strip()[:40]!r}）")
    except Exception:
        check(False, "120 秒内没收到回复")

    end()


async def test_image_remove_before_send(page, api):
    begin("闲聊：待发图片能删掉")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1800)

    img = make_test_png("remove.png")
    await page.locator("input[type='file']").set_input_files(str(img))

    try:
        await page.wait_for_selector(".pending-item .attachment-img", timeout=30_000)
    except Exception:
        check(False, "上传失败，无法继续测删除")
        end()
        return

    # 悬停显示删除按钮，点掉
    await page.locator(".pending-item").first.hover()
    await page.wait_for_timeout(300)
    await page.locator(".pending-remove").first.click()
    await page.wait_for_timeout(500)

    pending = await page.locator(".pending-item").count()
    check(pending == 0, f"删掉后待发区为空（实得 {pending} 个）")
    end()


# ============================================================================
# 测试：客服
# ============================================================================


async def test_customer_ui(page, api):
    begin("客服：页面和引导问题")

    await login(page, api.token)
    await page.goto(f"{BASE}/customer", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    # 空状态应该有引导问题
    hero = await page.locator(".customer-hero h2").count()
    check(hero > 0, "显示欢迎标题")

    suggestions = await page.locator(".suggestion").count()
    check(suggestions >= 3, f"有引导问题可点（实得 {suggestions} 个）")

    # 明确告诉用户「刷新后不保留」
    note = await page.locator(".composer-note").inner_text()
    check("不保留" in note, f"提示了刷新后不保留（实得 {note!r}）")

    # 客服没有左侧会话列表（后端不存）
    sidebar = await page.locator(".shell-sidebar, .chat-sidebar").count()
    check(sidebar == 0, "客服页没有左侧会话列表")
    end()


async def test_customer_ask(page, api):
    begin("客服：问一个问题能收到流式回答")

    await login(page, api.token)
    await page.goto(f"{BASE}/customer", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    box = page.locator("textarea")
    await box.fill("这个项目有哪些模块？")
    await box.press("Enter")

    # 立刻：用户消息出现，且显示「正在检索」
    await page.wait_for_timeout(1000)
    user_msgs = await page.locator(".msg--me").count()
    check(user_msgs > 0, "用户问题立刻显示")

    # 等回答
    try:
        await page.wait_for_function(
            """() => {
                const els = document.querySelectorAll('.msg--ai .msg-content');
                if (!els.length) return false;
                const last = els[els.length - 1];
                return last.textContent.trim().length > 10
                    && !last.classList.contains('msg-typing');
            }""",
            timeout=120_000,
        )
        answer = await page.locator(".msg--ai .msg-content").last.inner_text()
        check(len(answer.strip()) > 10, f"收到回答（{answer.strip()[:50]!r}…）")
    except Exception:
        check(False, "120 秒内没收到回答")

    # 结束后输入框恢复
    await page.wait_for_timeout(1000)
    stop_btn = await page.locator(".composer-send--stop").count()
    check(stop_btn == 0, "结束后「停止」按钮消失")
    end()


async def test_customer_suggestion(page, api):
    begin("客服：点引导问题直接提问")

    await login(page, api.token)
    await page.goto(f"{BASE}/customer", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    if await page.locator(".suggestion").count() == 0:
        check(False, "没有引导问题")
        end()
        return

    first = page.locator(".suggestion").first
    text = await first.inner_text()
    await first.click()

    # 点了之后应该在提问，欢迎页消失
    await page.wait_for_timeout(1500)
    hero = await page.locator(".customer-hero").count()
    check(hero == 0, "点击后进入对话状态（欢迎页消失）")

    user_msg = await page.locator(".msg--me .msg-content").first.inner_text()
    check(text.strip() in user_msg, f"用户消息就是问的那句（{user_msg.strip()[:30]!r}）")
    end()


async def test_customer_clear(page, api):
    begin("客服：能清空对话")

    await login(page, api.token)
    await page.goto(f"{BASE}/customer", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    # 先问一句（不用等回答，清空不看回答）
    await page.locator("textarea").fill("测试清空")
    await page.locator("textarea").press("Enter")
    await page.wait_for_timeout(1500)

    # 清空按钮应该出现了
    clear_btn = page.locator(".customer-head .ghost-btn")
    if await clear_btn.count() == 0:
        check(False, "没有清空按钮")
        end()
        return

    check(True, "有清空按钮")
    await clear_btn.click()
    await page.wait_for_timeout(800)

    # 回到空状态
    hero = await page.locator(".customer-hero").count()
    check(hero > 0, "清空后回到欢迎页")

    msgs = await page.locator(".msg").count()
    check(msgs == 0, f"消息都清掉了（实得 {msgs} 条）")
    end()


# ============================================================================
# 测试：智能出行
# ============================================================================


async def test_trip_ui(page, api):
    begin("出行：页面结构和空状态")

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    check(await page.locator(".trip-item").count() > 0, "左侧有出行记录")

    await page.locator(".new-btn").click()
    await page.wait_for_timeout(600)

    check(await page.locator(".trip-hero h2").count() > 0, "空状态显示欢迎标题")
    check(await page.locator(".example").count() >= 2, "有示例问题可点")
    end()


async def test_trip_list_independent(page, api):
    begin("出行：记录和对话列表是两套数据")

    await login(page, api.token)

    # 用接口直接比，界面只做辅助验证。
    # 注意不要断言「对话一定有会话」：测试账号可能只有出行记录、从没聊过天。
    # 这里要验证的是「两个列表来自不同接口」，不是「两边都有数据」。
    trip_rows = api.get("/trip/list")
    chat_rows = api.get("/sessions")

    check(isinstance(trip_rows, list), "GET /trip/list 返回列表")
    check(isinstance(chat_rows, list), "GET /sessions 返回列表")

    trip_ids = {row["id"] for row in trip_rows}
    chat_ids = {row["id"] for row in chat_rows}
    check(trip_ids != chat_ids, "两组 id 不同（说明是两张独立表）")

    # 界面上：出行页显示出行记录
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(1800)
    shown = await page.locator(".trip-item").count()
    check(shown == len(trip_rows), f"出行页显示 {len(trip_rows)} 条记录（实得 {shown} 条）")

    # 出行页不该显示对话的会话列表
    chat_list_visible = await page.locator(".session-item").count()
    check(chat_list_visible == 0, f"出行页没有对话会话列表（实得 {chat_list_visible} 个）")
    end()


async def test_trip_chat_path(page, api):
    begin("出行：直接回答（不启子图）")

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    await page.locator(".new-btn").click()
    await page.wait_for_timeout(500)

    await page.locator("textarea").fill("北京有什么好玩的")
    await page.locator("textarea").press("Enter")

    try:
        await page.wait_for_function(
            """() => {
                const el = document.querySelector('.msg-bubble-plain');
                return el && el.textContent.trim().length > 10;
            }""",
            timeout=120_000,
        )
        answer = await page.locator(".msg-bubble-plain").last.inner_text()
        check(len(answer.strip()) > 10, f"收到回答（{answer.strip()[:40]!r}）")
    except Exception:
        check(False, "120 秒内没收到回答")

    cards = await page.locator(".section-card").count()
    check(cards == 0, f"直接回答没有段落卡片（实得 {cards} 个）")

    await page.wait_for_timeout(1500)
    check(await page.locator(".trip-item").count() > 0, "记录出现在左侧")
    end()


async def test_trip_route_flow(page, api):
    begin("出行：路线（停等选方案 → 续流四段）")

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    await page.locator(".new-btn").click()
    await page.wait_for_timeout(500)

    await page.locator("textarea").fill("从杭州东站到灵隐寺怎么走")
    await page.locator("textarea").press("Enter")

    try:
        await page.wait_for_selector(".ask-panel .option", timeout=180_000)
        options = await page.locator(".ask-panel .option").count()
        check(options >= 2, f"给出多个候选方案（实得 {options} 个）")
    except Exception:
        check(False, "180 秒内没出现方案面板")
        end()
        return

    titles = await page.locator(".section-title").all_inner_texts()
    check("需求确认" in titles, f"需求确认段已渲染（实得 {titles}）")

    await page.locator(".ask-panel .option").first.click()
    await page.wait_for_timeout(400)
    await page.locator(".ask-panel .confirm-btn").click()

    try:
        await page.wait_for_function(
            """() => {
                const panels = document.querySelectorAll('.ask-panel');
                const titles = [...document.querySelectorAll('.section-title')]
                    .map(el => el.textContent.trim());
                const doing = document.querySelectorAll('.section-state--doing');
                return panels.length === 0
                    && titles.includes('出发提醒')
                    && doing.length === 0;
            }""",
            timeout=180_000,
        )
        final = await page.locator(".section-title").all_inner_texts()
        check(len(final) >= 3, f"四段都出来了（实得 {final}）")
        check("出发提醒" in final, "「出发提醒」完成")
    except Exception:
        check(False, "180 秒内没写完四段")
    end()


async def test_trip_guide_flow(page, api):
    begin("出行：攻略（停等勾景点 → 续流排行程）")

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    await page.locator(".new-btn").click()
    await page.wait_for_timeout(500)

    await page.locator("textarea").fill("下周去杭州玩三天")
    await page.locator("textarea").press("Enter")

    try:
        await page.wait_for_selector(".ask-panel .spot", timeout=300_000)
        spots = await page.locator(".ask-panel .spot").count()
        check(spots >= 2, f"给出多个景点可勾（实得 {spots} 个）")
    except Exception:
        check(False, "300 秒内没出现勾选面板")
        end()
        return

    titles = await page.locator(".section-title").all_inner_texts()
    check("天气" in titles, f"天气段已渲染（实得 {titles}）")
    check("景点清单" in titles, "景点清单段已渲染")

    await page.locator(".ask-panel .spot").first.click()
    await page.wait_for_timeout(300)

    hint = await page.locator(".foot-hint").inner_text()
    check("去掉" in hint, f"提示了去掉几个（实得 {hint!r}）")

    await page.locator(".ask-panel .confirm-btn").click()

    try:
        await page.wait_for_function(
            """() => {
                const panels = document.querySelectorAll('.ask-panel');
                const titles = [...document.querySelectorAll('.section-title')]
                    .map(el => el.textContent.trim());
                const doing = document.querySelectorAll('.section-state--doing');
                return panels.length === 0
                    && titles.includes('游玩建议')
                    && doing.length === 0;
            }""",
            timeout=300_000,
        )
        final = await page.locator(".section-title").all_inner_texts()
        check(len(final) >= 4, f"四段都出来了（实得 {final}）")
        check("游玩建议" in final, "「游玩建议」完成")
    except Exception:
        check(False, "300 秒内没写完四段")
    end()


async def test_trip_history_replay(page, api):
    begin("出行：打开历史记录能还原每一轮")

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(1800)

    items = page.locator(".trip-item")
    count = await items.count()
    found = False
    for i in range(min(count, 10)):
        await items.nth(i).click()
        await page.wait_for_timeout(900)
        if await page.locator(".section-card").count() > 0:
            found = True
            break

    if not found:
        check(False, "没有找到带卡片的记录（先跑一次路线或攻略）")
        end()
        return

    check(True, "打开了带卡片的记录")

    titles = await page.locator(".section-title").all_inner_texts()
    check(len(titles) > 0, f"还原出段落（{titles}）")

    doing = await page.locator(".section-state--doing").count()
    check(doing == 0, f"历史记录没有「生成中」残留（实得 {doing} 个）")
    end()


async def test_trip_list_no_flicker(page, api):
    begin("出行：切换记录时列表不闪")

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(1800)

    if await page.locator(".trip-item").count() < 2:
        check(False, "至少要有 2 条记录才能测切换")
        end()
        return

    samples = await sample(
        page,
        """{
            loading: (document.querySelector('.list-loading')?.innerText ?? '').includes('加载中'),
            items: document.querySelectorAll('.trip-item').length,
        }""",
        page.locator(".trip-item").nth(1).click(),
    )

    loading_hits = sum(1 for s in samples if s["loading"])
    empty_hits = sum(1 for s in samples if s["items"] == 0)

    check(loading_hits == 0, f"列表没有闪「加载中」（实得 {loading_hits} 次）")
    check(empty_hits == 0, f"列表条目没有归零（实得 {empty_hits} 次）")
    end()


async def test_trip_same_session(page, api):
    """同一个会话里连发多句，只应该有一条记录。

    这个曾经是个真 bug：
      后端在 CHAT / SAVED 事件里回了 chat_id，前端没同步到 currentTripId，
      于是下一轮又被当成「新会话」。结果每句话都变成一条独立记录。
    """
    begin("出行：同一会话连发多句不拆成多条记录")

    before = len(api.get("/trip/list"))

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    await page.locator(".new-btn").click()
    await page.wait_for_timeout(500)

    sentences = ["你好呀", "北京有什么好玩的"]

    for i, text in enumerate(sentences, 1):
        await page.locator("textarea").fill(text)
        await page.locator("textarea").press("Enter")

        # 等这一轮彻底跑完
        try:
            await page.wait_for_function(
                """() => {
                    const stop = document.querySelector('.composer-send--stop');
                    const typing = document.querySelector('.msg-bubble--typing');
                    return !stop && !typing;
                }""",
                timeout=120_000,
            )
        except Exception:
            check(False, f"第 {i} 句 120 秒没跑完")
            end()
            return
        await page.wait_for_timeout(1200)

    after = len(api.get("/trip/list"))
    added = after - before

    check(added == 1, f"连发 {len(sentences)} 句只新增 1 条记录（实得 {added} 条）")

    # 界面上应该是多条轮次，而不是多条记录
    turns = await page.locator(".turn").count()
    check(turns == len(sentences), f"界面有 {len(sentences)} 轮对话（实得 {turns} 轮）")

    # 左边第一条显示「2 轮对话」
    first_rounds = await page.locator(".trip-item").first.locator(".trip-sub").inner_text()
    check(
        "2 轮" in first_rounds,
        f"左侧首条显示轮次数（实得 {first_rounds!r}）",
    )
    end()


async def test_composer_keeps_focus(page, api):
    """发送后输入框要保持可输入状态。

    这个曾经是个真 bug：
      发送后把 textarea 设成 disabled，浏览器会把焦点踢到 body。
      等流结束 disabled 变回 false 时，焦点再也回不去了 ——
      用户想接着说话，还得再点一下输入框。

    正确做法：生成期间输入框**不 disabled**，只是发送被拦住
      （canSend() 里判断了 disabled，不会重复发送）。
      这样用户可以边等回复边打下一句。
    """
    begin("输入框：发送后焦点不丢，可以接着打字")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    box = page.locator("textarea")
    await box.click()
    await box.fill("测试焦点")
    await box.press("Enter")
    await page.wait_for_timeout(700)

    state = await page.evaluate(
        """() => {
            const ta = document.querySelector('textarea');
            return {
                focused: document.activeElement === ta,
                disabled: ta.disabled,
            };
        }"""
    )

    check(state["focused"], "发送后焦点还在输入框")
    check(not state["disabled"], "生成期间输入框没被禁用")

    # 生成期间还能继续打字
    await page.keyboard.type("接着打")
    await page.wait_for_timeout(300)
    value = await box.input_value()
    check("接着打" in value, f"生成期间可以继续打字（当前内容 {value!r}）")

    # 停下，别让测试挂太久
    stop_btn = page.locator(".composer-send--stop")
    if await stop_btn.count():
        await stop_btn.click()
    await page.wait_for_timeout(500)
    end()



# ============================================================================
# 测试：登录 / 注册 / 退出
# ============================================================================


async def test_auth_dialog(page, api):
    begin("登录：访客能打开登录/注册弹层")

    await login(page, api.token)
    await page.goto(BASE, wait_until="networkidle")
    await page.wait_for_timeout(1500)

    # 顶栏身份
    who = await page.locator(".account-btn .who").count()
    check(who > 0, "顶栏有身份显示")

    # 点头像开菜单
    await page.locator(".account-btn").click()
    await page.wait_for_timeout(500)
    check(await page.locator(".menu").count() > 0, "账号菜单打开")

    # 访客态下应该有「登录 / 注册」
    has_login = await page.locator(".menu-item--primary").count()
    check(has_login > 0, "访客态有「登录 / 注册」入口")

    # 点开弹层
    await page.locator(".menu-item--primary").click()
    await page.wait_for_timeout(600)
    check(await page.locator(".dialog").count() > 0, "登录弹层打开")

    # 有邮箱和密码两个输入
    inputs = await page.locator(".dialog input").count()
    check(inputs >= 2, f"登录表单有邮箱和密码（实得 {inputs} 个输入框）")

    # 能切到注册
    await page.locator(".switch-row .link").click()
    await page.wait_for_timeout(400)
    reg_inputs = await page.locator(".dialog input").count()
    check(reg_inputs >= 3, f"注册表单多了昵称和确认密码（实得 {reg_inputs} 个）")
    end()


async def test_auth_register_flow(page, api):
    begin("登录：注册能成功并切换身份")

    # 每次用不同邮箱，避免「已注册」
    stamp = int(time.time())
    email = f"e2e_{stamp}@test.local"
    password = "test123456"

    await login(page, api.token)
    await page.goto(BASE, wait_until="networkidle")
    await page.wait_for_timeout(1500)

    await page.locator(".account-btn").click()
    await page.wait_for_timeout(400)
    await page.locator(".menu-item--primary").click()
    await page.wait_for_timeout(500)

    # 切到注册
    await page.locator(".switch-row .link").click()
    await page.wait_for_timeout(400)

    inputs = page.locator(".dialog input")
    await inputs.nth(0).fill(email)
    await inputs.nth(1).fill("E2E 测试")
    await inputs.nth(2).fill(password)
    await inputs.nth(3).fill(password)
    await page.wait_for_timeout(300)

    await page.locator(".primary").click()

    # 弹层应该关掉
    try:
        await page.wait_for_selector(".dialog", state="detached", timeout=30_000)
        check(True, "注册成功，弹层关闭")
    except Exception:
        err = await page.locator(".error").count()
        msg = await page.locator(".error").inner_text() if err else "未知"
        check(False, f"注册失败：{msg}")
        end()
        return

    await page.wait_for_timeout(1200)

    # 顶栏应该显示注册的昵称
    who = await page.locator(".account-btn .who").inner_text()
    check("E2E" in who or "测试" in who, f"顶栏显示昵称（实得 {who!r}）")

    # 用接口确认身份真的换了
    me = await page.evaluate(
        """async () => {
            const t = localStorage.getItem('ctos_token');
            const r = await fetch('/auth/me', {headers: {'Authorization': 'Bearer ' + t}});
            return r.ok ? await r.json() : null;
        }"""
    )
    check(me is not None and me.get("email") == email, "后端身份是新注册的账号")
    end()


async def test_auth_validation(page, api):
    begin("登录：表单会校验")

    await login(page, api.token)
    await page.goto(BASE, wait_until="networkidle")
    await page.wait_for_timeout(1500)

    await page.locator(".account-btn").click()
    await page.wait_for_timeout(400)
    await page.locator(".menu-item--primary").click()
    await page.wait_for_timeout(500)

    # 邮箱格式不对
    await page.locator(".dialog input").nth(0).fill("不是邮箱")
    await page.locator(".dialog input").nth(1).fill("123456")
    await page.wait_for_timeout(400)

    hint = await page.locator(".hint").count()
    check(hint > 0, "邮箱格式错会提示")

    # 密码太短
    await page.locator(".dialog input").nth(0).fill("a@b.com")
    await page.locator(".dialog input").nth(1).fill("123")
    await page.wait_for_timeout(400)
    hint_text = await page.locator(".hint").inner_text()
    check("6" in hint_text, f"密码太短会提示（实得 {hint_text!r}）")

    # 提交按钮是禁用的
    disabled = await page.locator(".primary").is_disabled()
    check(disabled, "校验不过时提交按钮禁用")
    end()


# ============================================================================
# 测试：访客复用 / 多选删除 / 反馈
# ============================================================================


async def test_guest_persist(page, api):
    begin("访客：刷新后还是同一个账号")

    # 清掉身份，让它自动建访客
    await page.goto(BASE, wait_until="networkidle")
    await page.evaluate("() => localStorage.clear()")
    await page.reload(wait_until="networkidle")
    await page.wait_for_timeout(2500)

    email1 = await page.evaluate(
        """async () => {
            const t = localStorage.getItem('ctos_token');
            const r = await fetch('/auth/me', {headers: {'Authorization': 'Bearer ' + t}});
            return (await r.json()).email;
        }"""
    )

    # 刷新
    await page.reload(wait_until="networkidle")
    await page.wait_for_timeout(2500)

    email2 = await page.evaluate(
        """async () => {
            const t = localStorage.getItem('ctos_token');
            const r = await fetch('/auth/me', {headers: {'Authorization': 'Bearer ' + t}});
            return (await r.json()).email;
        }"""
    )

    check(bool(email1), f"第一次拿到访客身份（{email1}）")
    check(email1 == email2, f"刷新后还是同一个账号（{email2}）")
    end()


async def test_chat_batch_delete(page, api):
    begin("对话：会话能多选删除")

    await login(page, api.token)
    await page.goto(f"{BASE}/chat", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    before = len(api.get("/sessions"))

    if before < 2:
        check(False, f"至少要有 2 个会话才能测（实得 {before} 个）")
        end()
        return

    # 进多选
    await page.locator(".foot-action").click()
    await page.wait_for_timeout(400)
    check(await page.locator(".select-bar").count() > 0, "进入多选模式")

    # 勾两个
    await page.locator(".session-item").nth(0).click()
    await page.wait_for_timeout(200)
    await page.locator(".session-item").nth(1).click()
    await page.wait_for_timeout(300)

    count_text = await page.locator(".bar-count").inner_text()
    check("已选 2" in count_text, f"勾选生效（实得 {count_text!r}）")

    # 删除
    page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await page.locator(".bar-btn--danger").click()
    await page.wait_for_timeout(2500)

    after = len(api.get("/sessions"))
    check(after == before - 2, f"删掉了 2 个（{before} → {after}）")
    check(await page.locator(".select-bar").count() == 0, "删除后退出多选")
    end()


async def test_feedback_submit(page, api):
    begin("反馈：能提交并显示成功")

    # 每条反馈带一个唯一标记，跑完按标记删掉，别把垃圾留在库里
    stamp = int(time.time())
    marker = f"[E2E-{stamp}]"

    await login(page, api.token)
    await page.goto(BASE, wait_until="networkidle")
    await page.wait_for_timeout(1500)

    # 开菜单 → 意见反馈
    await page.locator(".account-btn").click()
    await page.wait_for_timeout(400)

    feedback_btn = page.locator(".menu-item--muted")
    check(await feedback_btn.count() > 0, "菜单里有「意见反馈」")
    await feedback_btn.click()
    await page.wait_for_timeout(600)

    check(await page.locator(".ratings").count() > 0, "反馈弹窗打开")

    # 四个评价选项
    ratings = await page.locator(".rating").count()
    check(ratings == 4, f"有 4 档评价（实得 {ratings} 个）")

    # 选一个 + 写内容
    await page.locator(".rating").nth(1).click()
    await page.wait_for_timeout(200)
    await page.locator(".textarea").fill(f"自动测试，可以忽略。{marker}")
    await page.wait_for_timeout(300)

    await page.locator(".primary").click()
    await page.wait_for_timeout(2000)

    done = await page.locator(".done h2").count()
    check(done > 0, "提交成功有感谢页")

    # 清掉这条测试反馈。
    # 为什么必须清：
    #   反馈是给真人看的东西，测试往里塞垃圾，看反馈时还得一条条分辨哪条是测试的。
    #   之前就是没清，库里堆了三条「E2E 自动测试反馈」。
    cleaned = cleanup_test_feedback(marker)
    check(cleaned, f"测试反馈已清理（匹配 {marker}）")
    end()


def cleanup_test_feedback(marker: str) -> bool:
    """删掉内容里带这个标记的反馈。返回是否删到了。

    用子进程调 Python 连库，不用当前进程：
      测试进程不该为了清一条数据去加载数据库模块（会触发建表逻辑），
      而且清理失败也不该让整个测试崩掉。
    """
    import subprocess
    import tempfile
    from pathlib import Path

    # 清理脚本写到临时文件再跑，避免在命令行里拼引号（中文 + 引号很容易出错）
    # 用 f-string 而不是 % 格式化：脚本里本身就有 %s，和 % 格式化会打架
    pattern = f"%{marker}%"
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(PROJECT_ROOT)!r})\n"
        "from common.db import transaction\n"
        "with transaction() as cur:\n"
        "    cur.execute('DELETE FROM feedback WHERE content LIKE %s', "
        f"({pattern!r},))\n"
        "    print(cur.rowcount)\n"
    )

    path = Path(tempfile.gettempdir()) / "ctos-e2e-cleanup-feedback.py"
    path.write_text(script, encoding="utf-8")

    try:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"      [清理失败] {result.stderr.strip()[:200]}")
            return False
        return result.stdout.strip().isdigit()
    except Exception as e:
        print(f"      [清理失败] {e}")
        return False


async def test_trip_batch_delete(page, api):
    begin("出行：记录能多选删除")

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    before = len(api.get("/trip/list"))

    if before < 2:
        check(False, f"至少要有 2 条记录才能测（实得 {before} 条）")
        end()
        return

    await page.locator(".foot-action").click()
    await page.wait_for_timeout(400)
    check(await page.locator(".select-bar").count() > 0, "进入多选模式")

    await page.locator(".trip-item").nth(0).click()
    await page.wait_for_timeout(200)
    await page.locator(".trip-item").nth(1).click()
    await page.wait_for_timeout(300)

    page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await page.locator(".bar-btn--danger").click()
    await page.wait_for_timeout(2500)

    after = len(api.get("/trip/list"))
    check(after == before - 2, f"删掉了 2 条（{before} → {after}）")
    end()


# ============================================================================
# 测试：出行生图（只验证判断，不真画 —— 画一张要花钱）
# ============================================================================


async def test_trip_image_offer(page, api):
    begin("出行：路线跑完会主动提议生成图")

    await login(page, api.token)
    await page.goto(f"{BASE}/trip", wait_until="networkidle")
    await page.wait_for_timeout(1500)

    await page.locator(".new-btn").click()
    await page.wait_for_timeout(500)

    await page.locator("textarea").fill("从杭州东站到灵隐寺怎么走")
    await page.locator("textarea").press("Enter")

    # 等到出现方案面板（这时应该已经提议过）
    try:
        await page.wait_for_selector(".ask-panel .option", timeout=180_000)
    except Exception:
        check(False, "180 秒内没出现方案面板")
        end()
        return

    await page.wait_for_timeout(2500)

    # 页面上应该有「要不要…生成…图」的提议
    body = await page.locator(".trip-feed").inner_text()
    offered = "要不要" in body and "图" in body
    check(offered, "Agent 主动提议了生成图")

    # 提议之后按回车不会自动画（要用户明确说要）
    img_before = await page.locator(".gen-image").count()
    check(img_before == 0, "仅提议不会自动出图")
    end()


# ============================================================================
# 分组
# ============================================================================

GROUPS = {
    "infra": [test_page_loads, test_contract_matches],
    "chat": [test_chat_list_loads, test_switch_session_no_flicker, test_open_session_shows_messages],
    "roleplay": [
        test_roleplay_picker,
        test_roleplay_start_chat,
        test_roleplay_panels,
        test_role_form_validation,
    ],
    "nav": [test_navigation, test_playmode_bar],
    "send": [test_send_message, test_composer_keeps_focus],
    "image": [test_image_upload, test_image_remove_before_send],
    "customer": [
        test_customer_ui,
        test_customer_ask,
        test_customer_suggestion,
        test_customer_clear,
    ],
    "trip": [
        test_trip_ui,
        test_trip_list_independent,
        test_trip_chat_path,
        test_trip_same_session,
        test_trip_route_flow,
        test_trip_guide_flow,
        test_trip_history_replay,
        test_trip_list_no_flicker,
    ],
    "auth": [
        test_auth_dialog,
        test_auth_register_flow,
        test_auth_validation,
    ],
    "feature": [
        test_guest_persist,
        test_chat_batch_delete,
        test_trip_batch_delete,
        test_feedback_submit,
    ],
    "tripimg": [
        test_trip_image_offer,
    ],
}

# ============================================================================
# 主流程
# ============================================================================


def pick_tests(argv: list[str]) -> tuple[list, list[str]]:
    """按命令行参数选要跑的分组。

    不传参数 = 全跑。
    传了参数就只跑这些分组（比如 
un_all.py trip image）。
    传了不存在的名字会提示可用分组。
    """
    if not argv:
        names = list(GROUPS)
    else:
        unknown = [a for a in argv if a not in GROUPS]
        if unknown:
            print(f"未知分组：{', '.join(unknown)}")
            print(f"可用分组：{', '.join(GROUPS)}")
            raise SystemExit(2)
        names = argv

    tests = []
    for name in names:
        tests.extend(GROUPS[name])

    return tests, names


async def run(tests):
    """跑一组测试。每个测试开一个新页面，互不干扰。"""
    from playwright.async_api import async_playwright

    token = make_token()
    api = Api(token)

    async with async_playwright() as p:
        # 用本机装的 Chrome，不用 playwright 自带浏览器
        browser = await p.chromium.launch(channel="chrome")

        for test in tests:
            page = await browser.new_page(viewport={"width": 1440, "height": 900})

            # 页面报错要能看到，否则测试失败时一头雾水
            page.on("pageerror", lambda e: print(f"      [页面错误] {e}"))

            try:
                await test(page, api)
            except Exception as e:
                # 某个测试崩了不该带走整轮，记下来接着跑
                check(False, f"异常：{type(e).__name__}: {e}")
                end()
            finally:
                await page.close()

        await browser.close()


def main():
    argvs = sys.argv[1:]
    tests, names = pick_tests(argvs)

    print("─" * 70)
    print(f"分组：{', '.join(names)}")
    print(f"共 {len(tests)} 个测试")
    print("─" * 70)

    start = time.time()

    import asyncio
    asyncio.run(run(tests))

    elapsed = time.time() - start

    # 汇总
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed

    print()
    print("=" * 70)
    print(f"结果：{passed} 通过，{failed} 失败（{elapsed:.1f} 秒）")
    print("=" * 70)

    if failed:
        print()
        print("失败项：")
        for name, ok, problems in RESULTS:
            if ok:
                continue
            print(f"  ✗ {name}")
            for problem in problems:
                print(f"      - {problem}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
