"""
重拍 README 用的界面截图。

跑法：venv\\Scripts\\python.exe -X utf8 scripts\\make_screenshots.py
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web" / "scripts" / "e2e"))

from run_all import BASE, Api, login, make_token  # noqa: E402

OUT = ROOT / "screenshot"


async def main():
    from playwright.async_api import async_playwright

    OUT.mkdir(exist_ok=True)

    token = make_token()
    api = Api(token)

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        await login(page, token)

        # ---------- 闲聊 ----------
        print("对话…")
        sessions = api.get("/sessions")
        target = next((s for s in sessions if not s.get("role_id")), None)

        await page.goto(f"{BASE}/chat", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        if target:
            await page.locator(f".session-item").first.click()
            await page.wait_for_timeout(2500)

        await page.screenshot(path=str(OUT / "ctOS_chat.png"))

        # ---------- 角色扮演 ----------
        print("角色扮演…")
        await page.goto(f"{BASE}/chat/roles", wait_until="networkidle")
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(OUT / "ctOS_role.png"))

        # ---------- 出行：空状态 ----------
        print("出行…")
        await page.goto(f"{BASE}/trip", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        await page.locator(".new-btn").click()
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT / "ctOS_trip00.png"))

        # ---------- 出行：选方案 ----------
        print("出行选方案（要等模型）…")
        await page.locator("textarea").fill("从杭州东站到灵隐寺怎么走")
        await page.locator("textarea").press("Enter")

        try:
            await page.wait_for_selector(".ask-panel .option", timeout=180_000)
            await page.wait_for_timeout(2500)
            await page.screenshot(path=str(OUT / "ctOS_trip01.png"))
            print("  选方案截图 OK")
        except Exception as e:
            print(f"  ⚠️ 选方案超时：{e}")

        # ---------- 客服 ----------
        print("客服…")
        await page.goto(f"{BASE}/customer", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT / "ctOS_customer01.png"))

        await page.locator("textarea").fill("你们支持哪些付款方式")
        await page.locator("textarea").press("Enter")

        try:
            await page.wait_for_function(
                "() => document.querySelectorAll('.msg--ai').length > 0",
                timeout=120_000,
            )
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(OUT / "ctOS_customer02.png"))
            print("  客服回答截图 OK")
        except Exception as e:
            print(f"  ⚠️ 客服回答超时：{e}")

        # ---------- 登录弹层 ----------
        print("登录弹层…")
        await page.goto(f"{BASE}/chat", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        await page.locator(".account-btn").click()
        await page.wait_for_timeout(400)
        await page.locator(".menu-item--primary").click()
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT / "ctOS_login.png"))

        await browser.close()
        print("完成")


asyncio.run(main())
