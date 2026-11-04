"""Browser test: journey through KYC, AutoPay, fibre reroute, delay and activation on the tracker."""
import sys
from playwright.sync_api import sync_playwright
out = sys.argv[1] if len(sys.argv) > 1 else "."; errors = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 400, "height": 860})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto("http://localhost:8000/"); pg.click("button:has-text('English')"); pg.click("text=Start")
    pg.wait_for_selector(".bubble.bot")
    for msg in ["37NBLXS1145E1ZU", "electronics shop", "3 people", "UPI billing and CCTV", "that's all"]:
        n = pg.locator(".bubble").count(); pg.fill("#msg", msg); pg.keyboard.press("Enter")
        pg.wait_for_function(f"document.querySelectorAll('.bubble').length >= {n + 2}")
        if pg.locator(".tier").count(): break
    pg.locator(".tier").nth(2).locator("button").click()   # Complete tier
    pg.wait_for_selector(".summary .price"); pg.wait_for_timeout(400)
    pg.click("button:has-text('Accept quote')"); pg.wait_for_selector(".ref")
    pg.click("text=Verify now"); pg.wait_for_selector("text=I agree")
    pg.locator(".purpose input").nth(1).check(); pg.click("text=I agree")
    pg.wait_for_selector(".chips.wrap button"); pg.click(".chips.wrap button:has-text('K12')")
    pg.wait_for_selector(".esign", timeout=60000)
    pg.fill("#otp", "123456"); pg.click("text=Sign application"); pg.wait_for_selector("text=Track my order")
    pg.click("text=Track my order"); pg.wait_for_selector(".status-card")
    pg.screenshot(path=f"{out}/t1-mandate.png", full_page=True)
    pg.fill("#upi", "pooja@okbank"); pg.click("text=Approve AutoPay"); pg.wait_for_selector("text=AutoPay set up")
    pg.click("summary:has-text('Demo controls')")
    pg.click("text=Next step: fibre not available"); pg.wait_for_selector(".notice.ok")
    reroute = pg.locator(".notice.ok").inner_text()
    pg.click("text=Simulate install delay"); pg.wait_for_selector(".late-badge")
    pg.screenshot(path=f"{out}/t2-delayed.png", full_page=True)
    pg.click("button:has-text('Next step')"); pg.wait_for_timeout(600)
    pg.click("button:has-text('Next step')"); pg.wait_for_selector(".status-card.live")
    pg.screenshot(path=f"{out}/t3-live.png", full_page=True)
    msgs = pg.locator(".wa-msg").count()
    print("reroute note:", reroute[:160], "| messages:", msgs, "| final:", pg.locator(".status-label").inner_text())
    print("scrollWidth", pg.evaluate("document.documentElement.scrollWidth"))
    b.close()
print("errors:", errors or "none")
