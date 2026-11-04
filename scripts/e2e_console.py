"""Browser test: seeds leads and a KYC review, then exercises every console tab and assisted mode."""
import sys, json, urllib.request
from playwright.sync_api import sync_playwright
out = sys.argv[1] if len(sys.argv) > 1 else "."; errors = []
B = "http://localhost:8000"
def post(path, body=None):
    req = urllib.request.Request(B + "/api" + path, data=json.dumps(body or {}).encode(), headers={"content-type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))
# seed: two unclosed advisor leads and one KYC review case
for msgs in (["Restaurant chain in Pune", "60 staff, 6 outlets", "billing and backup internet", "no"], ["kirana store in Patna", "2 people", "billing", "no"], ["Law office in Delhi", "25 staff", "office phone lines", "32TTNXB7384T1ZW"]):
    sid = post("/advisor/sessions")["session_id"]
    for m in msgs: post(f"/advisor/sessions/{sid}/messages", {"text": m})
cid = post("/kyc/cases")["id"]; post(f"/kyc/cases/{cid}/consent", {"purposes": ["kyc_verification"]}); post(f"/kyc/cases/{cid}/sample/K07"); post(f"/kyc/cases/{cid}/verify")
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(B + "/#/console"); pg.wait_for_selector(".tiles")
    pg.screenshot(path=f"{out}/c1-overview.png", full_page=True)
    pg.click("text=Leads to call"); pg.wait_for_selector(".c-table tbody tr")
    rows = pg.locator(".c-table tbody tr").count()
    pg.locator("text=Offer help").first.click(); pg.wait_for_selector(".assist")
    code = pg.locator(".assist .muted").inner_text().split("demo: ")[1].strip(")")
    pg.fill(".assist input", code); pg.click(".assist >> text=Confirm"); pg.wait_for_selector("text=Continue journey")
    pg.screenshot(path=f"{out}/c2-leads.png", full_page=True)
    pg.click("text=Re-engage Q2"); pg.wait_for_selector(".c-table tbody tr")
    pg.screenshot(path=f"{out}/c3-reengage.png")
    pg.click("text=KYC reviews"); pg.wait_for_selector(".review")
    pg.locator(".review").first.locator("input").fill("Legal name altered vs GST records")
    pg.locator(".review").first.locator("text=Reject").click(); pg.wait_for_timeout(800)
    pg.click("text=Lead score model"); pg.wait_for_selector(".coefs")
    pg.screenshot(path=f"{out}/c4-model.png")
    pg.click("text=Channel partner"); pg.wait_for_timeout(800)
    tabs = pg.locator(".c-tabs button").all_inner_texts()
    pg2 = b.new_page(viewport={"width": 400, "height": 860}); pg2.goto(B + "/#/console"); pg2.wait_for_selector(".tiles")
    sw = pg2.evaluate("document.documentElement.scrollWidth")
    pg2.screenshot(path=f"{out}/c5-phone.png", full_page=True)
    print("lead rows:", rows, "| partner tabs:", tabs, "| phone scrollWidth:", sw)
    b.close()
print("errors:", errors or "none")
