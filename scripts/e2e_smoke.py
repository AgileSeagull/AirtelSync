"""Browser smoke test of the owner journey (English light + Hindi dark).

Needs: pip install playwright, and Google Chrome installed (uses channel="chrome").
Run the API with the built web app on :8000 first (see README), then:
    python scripts/e2e_smoke.py /tmp/shots
"""
import sys
from playwright.sync_api import sync_playwright
out = sys.argv[1] if len(sys.argv) > 1 else "."
errors = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 400, "height": 860}, device_scale_factor=1)
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://localhost:8000/")
    pg.wait_for_selector("text=English")
    pg.screenshot(path=f"{out}/1-welcome.png", full_page=True)
    pg.click("button:has-text('English')")
    pg.click("text=Start")
    pg.wait_for_selector(".bubble.bot")
    for msg in ["I run a dental clinic in Kochi", "12 staff, one clinic",
                "We need CCTV and business email. Home broadband now, about Rs 3000 a month", "32TTNXB7384T1ZW"]:
        n = pg.locator(".bubble").count()
        pg.fill("#msg", msg)
        pg.keyboard.press("Enter")
        pg.wait_for_function(f"document.querySelectorAll('.bubble').length >= {n + 2}")
    pg.wait_for_selector(".tier")
    pg.screenshot(path=f"{out}/2-chat.png", full_page=False)
    pg.locator(".tier.best").scroll_into_view_if_needed()
    pg.screenshot(path=f"{out}/3-tiers.png", full_page=False)
    pg.locator(".tier.best button").click()
    pg.wait_for_selector(".summary .price")
    pg.wait_for_timeout(500)
    pg.screenshot(path=f"{out}/4-quote.png", full_page=False)
    price12 = pg.locator(".summary .price").inner_text()
    pg.click("button:has-text('24 months')")
    pg.wait_for_timeout(600)
    price24 = pg.locator(".summary .price").inner_text()
    # toggle internet off -> fix banner
    pg.locator(".row").first.locator(".switch").click()
    pg.wait_for_selector(".notice.bad")
    pg.screenshot(path=f"{out}/5-fix.png", full_page=False)
    accept_disabled = pg.locator("button:has-text('Accept quote')").is_disabled()
    pg.locator(".notice.bad button").first.click()
    pg.wait_for_timeout(700)
    pg.locator(".row").first.locator(".switch").click()  # turn fibre back on
    pg.wait_for_timeout(700)
    fixes_left = pg.locator(".notice.bad").count()
    pg.click("button:has-text('Accept quote')")
    pg.wait_for_selector(".ref")
    pg.screenshot(path=f"{out}/6-order.png", full_page=False)
    print("price 12m:", price12, "| 24m:", price24, "| accept disabled while broken:", accept_disabled,
          "| fixes after repair:", fixes_left, "| order:", pg.locator(".ref").inner_text())
    # Hindi flow, dark mode
    pg2 = b.new_page(viewport={"width": 400, "height": 860}, color_scheme="dark")
    pg2.on("pageerror", lambda e: errors.append(str(e)))
    pg2.goto("http://localhost:8000/")
    pg2.click("button:has-text('हिन्दी')")
    pg2.click("text=शुरू करें")
    pg2.wait_for_selector(".bubble.bot")
    for msg in ["मेरी किराना दुकान है पटना में", "2 लोग", "बिलिंग और व्हाट्सएप चाहिए, अभी हॉटस्पॉट है, ₹800 महीना", "नहीं"]:
        n = pg2.locator(".bubble").count()
        pg2.fill("#msg", msg); pg2.keyboard.press("Enter")
        pg2.wait_for_function(f"document.querySelectorAll('.bubble').length >= {n + 2}")
    pg2.wait_for_selector(".tier")
    pg2.locator(".tier.best").scroll_into_view_if_needed()
    pg2.screenshot(path=f"{out}/7-hindi-dark.png", full_page=False)
    pg2.locator(".tier.best button").click()
    pg2.wait_for_selector(".summary .price")
    pg2.click("details.addons summary")
    pg2.wait_for_timeout(500)
    pg2.locator(".addon.locked").first.scroll_into_view_if_needed()
    pg2.screenshot(path=f"{out}/8-hindi-addons.png", full_page=False)
    b.close()
print("console/page errors:", errors or "none")
