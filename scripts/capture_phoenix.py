"""Captura evidencia visual del panel local de Phoenix."""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "screenshots"
BROWSER_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


async def capture() -> None:
    SCREENSHOTS.mkdir(exist_ok=True)
    async with async_playwright() as playwright:
        executable = next(path for path in BROWSER_CANDIDATES if path.exists())
        browser = await playwright.chromium.launch(
            executable_path=str(executable), headless=True
        )
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})
        await page.goto("http://127.0.0.1:6006", wait_until="networkidle")
        await page.wait_for_timeout(2_000)

        project = page.get_by_text("preentrega7-agent-api", exact=False).first
        if await project.count():
            href = await project.evaluate(
                "element => element.closest('a')?.getAttribute('href')"
            )
            if href:
                await page.goto(f"http://127.0.0.1:6006{href}")
            else:
                await project.click()
            await page.get_by_text("GET /health", exact=True).first.wait_for(
                state="visible", timeout=60_000
            )

        await page.screenshot(
            path=SCREENSHOTS / "phoenix-cost-latency.png",
            full_page=True,
        )

        trace_row = None
        filter_editor = page.locator("[contenteditable='true']").first
        if await filter_editor.count():
            await filter_editor.evaluate(
                """element => {
                    element.focus();
                    const range = document.createRange();
                    range.selectNodeContents(element);
                    range.collapse(false);
                    const selection = window.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(range);
                }"""
            )
            await page.keyboard.type('name == "agent_job.execute" and ')
            await page.keyboard.press("Enter")
            trace_row = page.get_by_text("agent_job.execute", exact=True).nth(1)
            await trace_row.wait_for(state="visible", timeout=60_000)

        await page.screenshot(
            path=SCREENSHOTS / "phoenix-traces.png",
            full_page=True,
        )

        if trace_row is not None and await trace_row.count():
            await trace_row.click()
            await page.wait_for_timeout(2_000)

        await page.screenshot(
            path=SCREENSHOTS / "phoenix-trace-detail.png",
            full_page=True,
        )

        await page.get_by_text("Dashboards", exact=True).click()
        await page.get_by_text("Select project", exact=True).click()
        await page.get_by_text("preentrega7-agent-api", exact=True).last.click()
        await page.wait_for_timeout(5_000)
        await page.screenshot(
            path=SCREENSHOTS / "phoenix-dashboards.png",
            full_page=True,
        )
        print("Capturas de Phoenix generadas en screenshots/.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(capture())
