"""Render privacy_note.html to a one-page A4 PDF (and a PNG preview) with Chrome.
Usage: services/api/.venv/bin/python docs/privacy/render.py"""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=2)
    pg.goto((HERE / "privacy_note.html").as_uri())
    pg.evaluate("document.fonts.ready")
    print("content bottom:", pg.evaluate("Math.max(...[...document.querySelectorAll('section')].map(e => e.getBoundingClientRect().bottom))"),
          "footer top:", pg.evaluate("document.querySelector('footer').getBoundingClientRect().top"))
    pg.screenshot(path=str(HERE / "privacy_note_preview.png"))
    pg.pdf(path=str(HERE / "UdyamSaathi_Privacy_Security_Note.pdf"), width="210mm", height="297mm", print_background=True)
    b.close()
