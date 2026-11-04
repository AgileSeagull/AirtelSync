"""Render architecture.html to a one-page A3 landscape PDF (and a PNG preview) with Chrome.
Usage: python docs/architecture/render.py   (needs playwright; uses the installed Chrome)"""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1587, "height": 1123}, device_scale_factor=2)
    pg.goto((HERE / "architecture.html").as_uri())
    pg.wait_for_function("window.__drawn === true")
    over = pg.evaluate("document.body.scrollHeight > 1123 || document.body.scrollWidth > 1587")
    print("overflow:", over, pg.evaluate("[document.body.scrollWidth, document.body.scrollHeight]"))
    pg.screenshot(path=str(HERE / "architecture_preview.png"))
    pg.pdf(path=str(HERE / "AirtelSync_Solution_Architecture.pdf"), width="420mm", height="297mm", print_background=True)
    b.close()
