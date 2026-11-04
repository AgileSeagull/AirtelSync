"""Browser test: full journey ending in Smart KYC + e-sign, and the K01-K12 demo applicants.
Same prerequisites as e2e_smoke.py.   python scripts/e2e_kyc.py /tmp/shots
"""
import sys
from playwright.sync_api import sync_playwright
out = sys.argv[1] if len(sys.argv) > 1 else "."; errors = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 400, "height": 860})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    # full journey: advisor -> quote -> accept -> KYC with matching K12 documents -> esign
    pg.goto("http://localhost:8000/"); pg.click("button:has-text('English')"); pg.click("text=Start")
    pg.wait_for_selector(".bubble.bot")
    for msg in ["37NBLXS1145E1ZU", "electronics shop", "3 people", "UPI billing", "that's all"]:
        n = pg.locator(".bubble").count(); pg.fill("#msg", msg); pg.keyboard.press("Enter")
        pg.wait_for_function(f"document.querySelectorAll('.bubble').length >= {n + 2}")
        if pg.locator(".tier").count(): break
    pg.wait_for_selector(".tier"); pg.locator(".tier.best button").click()
    pg.wait_for_selector(".summary .price"); pg.wait_for_timeout(400)
    pg.click("button:has-text('Accept quote')"); pg.wait_for_selector(".ref")
    pg.click("text=Verify now")
    pg.wait_for_selector("text=I agree"); pg.screenshot(path=f"{out}/k1-consent.png", full_page=True)
    pg.click("text=I agree"); pg.wait_for_selector("text=Check my documents")
    # upload real files through the file inputs
    import os
    D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "kyc_documents")
    for slot, f in [("gst_certificate", "K12_gst_certificate.png"), ("udyam_certificate", "K12_udyam_certificate.png"),
                    ("signatory_id", "K12_signatory_id.png"), ("address_proof", "K12_address_proof.png")]:
        idx = ["gst_certificate","udyam_certificate","signatory_id","address_proof"].index(slot)
        pg.locator("input[type=file]").nth(idx).set_input_files(os.path.join(D, f))
        pg.wait_for_function(f"document.querySelectorAll('.row .pill').length >= {idx + 1}", timeout=30000)
    pg.click("text=Check my documents")
    pg.wait_for_selector(".verdict", timeout=30000)
    pg.screenshot(path=f"{out}/k2-approved.png", full_page=True)
    verdict = pg.locator(".verdict strong").inner_text()
    pg.fill("#otp", "123456"); pg.click("text=Sign application")
    pg.wait_for_selector("text=Application signed"); pg.screenshot(path=f"{out}/k3-signed.png")
    # demo samples: K01 blocked, K05 confirm udyam fix
    pg2 = b.new_page(viewport={"width": 400, "height": 860})
    pg2.on("pageerror", lambda e: errors.append(str(e)))
    pg2.goto("http://localhost:8000/"); pg2.click("button:has-text('English')")
    pg2.goto("http://localhost:8000/#/kyc-demo"); pg2.wait_for_selector("text=I agree"); pg2.click("text=I agree")
    pg2.wait_for_selector(".chips.wrap button")
    res = {}
    for k in ["K01", "K07", "K11", "K05"]:
        pg2.click(f".chips.wrap button:has-text('{k}')")
        pg2.wait_for_selector(".chips.wrap button:disabled", timeout=5000)
        pg2.wait_for_selector(".chips.wrap button:disabled", state="detached", timeout=60000)
        res[k] = pg2.locator(".verdict strong").inner_text()
        pg2.screenshot(path=f"{out}/k-{k}.png", full_page=True)
    pg2.click("text=Yes, that's mine"); pg2.wait_for_timeout(1500)
    res["K05-fixed"] = pg2.locator(".verdict strong").inner_text()
    print("journey verdict:", verdict, "| demo:", res)
    b.close()
print("errors:", errors or "none")
