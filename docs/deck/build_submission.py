"""Build the Udyam Saathi submission deck (cover + 7 slides) on the official SYNC template.

    python docs/deck/build_submission.py "path/to/Submission Template_Sync.pptx" docs/deck/UdyamSaathi_Submission_7_Slides.pptx

Condensed from the 10-slide business case (build_deck.py, whose helpers and slides it reuses):
problem + target customers, solution + pricing, Smart KYC + privacy, field force & partners,
architecture + evidence, and metrics + rollout + risks.
"""
from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches

sys.path.insert(0, str(Path(__file__).parent))
from build_deck import (AMBER, AMBER_SOFT, BLUE, BLUE_SOFT, GREEN, GREEN_SOFT, GREY, INK, LINE, MUTED, PANEL,  # noqa: E402
                        RED, RED_SOFT, WHITE, Slide, apply_motion, arrow, box, footer, group, header, label_in,
                        metrics, partners, phone, rollout, stagger, text)

HERE = Path(__file__).parent
REPO = "https://github.com/AgileSeagull/UdyamSaathi"
VIDEO = "https://drive.google.com/file/d/1w1bql5tn_JVBzBwIGaljY0U5yy1IlhZ3/view?usp=sharing"


# ------------------------------------------------------------------ 1 · cover
def cover(prs, blob):
    sl = Slide(prs, blob)
    g = stagger(300, 250)
    sl.anim(text(sl, 0.65, 2.6, 4.4, 0.55, "Udyam Saathi", size=34, bold=True, color=WHITE), "rise", next(g), 700)
    sl.anim(text(sl, 0.65, 3.23, 4.3, 0.6, "Small businesses go digital in one sitting: advice, quote, KYC and activation on a phone, in their language.",
                 size=11.5, color=RGBColor(0xEE, 0xEE, 0xEE), spacing=1.15), "rise", next(g), 700)
    sl.anim(box(sl, 0.65, 3.97, 0.5, 0.04, fill=RED, radius=0), "wipe", next(g), 500)
    light = RGBColor(0xC8, 0xC8, 0xC8)
    tb = text(sl, 0.65, 4.1, 4.4, 1.1, [
        [("Team CTRL ALT ELITE", {"bold": True, "color": WHITE, "size": 10})],
        [("Vishal Dev Verma  ·  Kartik Patel", {})],
        [("Vellore Institute of Technology", {})],
        [("▶  Watch the demo video (2:52)", {"bold": True, "color": WHITE})],
        [("Code: github.com/AgileSeagull/UdyamSaathi", {})]], size=8.5, color=light, spacing=1.25)
    for i, url in ((3, VIDEO), (4, REPO)):  # transparent click areas keep the text white (text links render blue)
        hot = sl.s.shapes.add_shape(1, Inches(0.6), Inches(4.12 + i * 0.185), Inches(3.2), Inches(0.19))
        hot.fill.background()
        hot.line.fill.background()
        hot.click_action.hyperlink.address = url
    sl.anim(tb, "fade", next(g), 600)
    sl.notes("Udyam Saathi: a working digital-first acquisition and onboarding journey for Accel Business's MSME customers. "
             "The demo video and the code repository are linked on this slide; every figure is backed by the case data and the running prototype.")
    return sl


# ------------------------------------------------------------------ 2 · problem + target customers
def problem_and_target(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "The problem & who we target first (Q1)", "Only 7.4% of small-business leads become customers")
    kpis = [("7.4%", "of leads activate"), ("17.6 days", "from lead to activation"), ("₹15,053", "spent per activation"),
            ("3.0", "calls chasing status, per customer")]
    d = stagger(450, 140)
    for i, (big, small) in enumerate(kpis):
        b = box(sl, 0.55 + (i % 2) * 2.02, 1.58 + (i // 2) * 0.98, 1.92, 0.88, fill=WHITE, line=LINE, radius=0.1)
        label_in(b, [[(big, {"size": 18, "bold": True, "color": RED if i == 0 else INK})], [(small, {"size": 8, "color": GREY})]],
                 align=PP_ALIGN.LEFT)
        b.text_frame.margin_left = Inches(0.14)
        sl.anim(b, "rise", next(d), 500)
    ins = box(sl, 0.55, 3.56, 3.94, 1.48, fill=RED_SOFT, radius=0.08)
    label_in(ins, [[("Where leads are lost", {"bold": True, "color": RED, "size": 9.5})],
                   [("The steepest drop is needs assessed → quote accepted (44%). ", {"bold": True}),
                    ("1,624 of 4,632 lost leads (35%) dropped for reasons a digital journey removes: no visit possible (827), "
                     "slow or confusing quotes (385), paperwork (273), install delays or no fibre (139).", {})]],
             size=9, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
    ins.text_frame.margin_left = Inches(0.16)
    ins.text_frame.margin_top = Inches(0.1)
    sl.anim(ins, "rise", 1100, 600)

    # target segments
    x0 = 4.75
    cols = [("Segment", 1.9), ("Share", 0.62), ("Activation", 0.78), ("Cost / act.", 0.82), ("Churn", 0.5)]
    x = x0
    for name, w in cols:
        text(sl, x + (0.12 if x == x0 else 0), 1.58, w, 0.2, name.upper(), size=6.5, bold=True, color=MUTED)
        x += w
    rows = [("Professional offices", "25%", "11.1%", "₹10,695", "14%", "1 · Lead: self-serve + calls", GREEN, GREEN_SOFT),
            ("Small multi-site", "15%", "11.0%", "₹15,614", "11%", "2 · Digital quote, field rollout", BLUE, BLUE_SOFT),
            ("Small manufacturers", "6%", "12.8%", "₹15,324", "8%", "3 · Field sales: leased lines", BLUE, BLUE_SOFT),
            ("Micro retail & services", "54%", "4.1%", "₹20,007", "23%", "Volume · self-serve only", AMBER, AMBER_SOFT)]
    d = stagger(700, 150)
    y = 1.8
    for name, share, act, cost, churn, play, fg, bg in rows:
        g = group(sl)
        box(sl, x0, y, 4.7, 0.76, fill=WHITE, line=LINE, radius=0.12, container=g)
        text(sl, x0 + 0.12, y + 0.1, 1.8, 0.2, name, size=9, bold=True, container=g)
        pill = box(sl, x0 + 0.1, y + 0.4, 1.72, 0.25, fill=bg, radius=0.5, container=g)
        label_in(pill, play, size=6.5, bold=True, color=fg)
        xx = x0 + cols[0][1]
        for val, (_, w) in zip((share, act, cost, churn), cols[1:]):
            text(sl, xx, y + 0.26, w, 0.25, val, size=10, bold=val != share, container=g,
                 color=RED if val == "₹20,007" else (GREY if val == share else INK))
            xx += w
        sl.anim(g, "rise", next(d), 450)
        y += 0.82
    footer(sl, "Source: smb_leads.csv, 5,000 leads, Apr–Jun 2026 (synthetic). Cost per activation = acquisition cost ÷ activations; churn at 6 months.")
    sl.notes("Field-led selling is slow and expensive, and a third of losses come from visits, quotes and paperwork. Professional offices convert at 11.1% "
             "with low churn: the lead segment. Micro retail is 54% of leads but only pays back if acquisition is digital.")
    return sl


# ------------------------------------------------------------------ 3 · solution + pricing
def solution(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "The solution: needs discovery without a salesperson (Q2)", "From “what do I need?” to activated, in one sitting")
    steps = [("s1-chat.png", "1  Talk", "An AI advisor asks about 5 questions in the owner's language, by text or voice. A GSTIN fills in the details."),
             ("s3-quote.png", "2  Choose", "Three bundles with a reason for every item. One monthly price incl. GST; switch add-ons on or off."),
             ("s6-kyc-ok.png", "3  Verify", "Consent, then DigiLocker or a photo, checked against GST and Udyam records. Aadhaar e-sign."),
             ("s7-track.png", "4  Track", "UPI AutoPay, technician slot, live ETAs and WhatsApp updates. No calls to chase status.")]
    d = stagger(450, 260)
    w, crop_h = 0.92, 1.72
    for i, (img, title, cap) in enumerate(steps):
        cx = 0.6 + i * 2.25
        g, h = phone(sl, img, cx, 1.55, w)
        pic = g.shapes[1]
        pic.crop_bottom = 1 - crop_h / h
        pic.height = Inches(crop_h)
        g.shapes[0].height = Inches(crop_h + 0.1)
        delay = next(d)
        sl.anim(g, "rise", delay, 600)
        t = text(sl, cx + w + 0.13, 1.6, 1.1, 1.7, [[(title, {"bold": True, "size": 10.5, "color": RED, "space_after": 3})],
                                                     [(cap, {"size": 7.5, "color": GREY})]], spacing=1.12)
        sl.anim(t, "fade", delay + 150, 500)
    text(sl, 0.55, 3.55, 8.9, 0.2, "WHAT OWNERS PAY · REAL QUOTES FROM THE PROTOTYPE, 12-MONTH PLANS INCL. GST", size=6.5, bold=True, color=MUTED)
    bundles = [("Dukaan Digital", "Kirana, 2 people, Patna", "₹3,004", "Fibre 100 · 2 SIMs · Cloud POS & UPI billing", "No setup fee · live in 5 days"),
               ("Clinic & Office Pro", "Dental clinic, 12 staff, Kochi", "₹6,701", "Fibre 300 · SIMs · CCTV · email · security · backup", "₹4,248 setup · live in 5 days"),
               ("Chain Connect", "Restaurant chain, 6 outlets, Pune", "₹23,339", "Fibre 300 ×6 · failover ×6 · POS ×6 · 3 SIMs", "₹28,320 setup · live in 5 days"),
               ("Factory Line", "Textile unit, 80 staff, Surat", "₹18,308", "Leased line · 8 machine IoT · SIMs · security", "₹40,120 setup · live in 21 days")]
    d = stagger(1500, 140)
    for i, (name, who, price, items, meta) in enumerate(bundles):
        b = box(sl, 0.55 + i * 2.25, 3.78, 2.15, 1.27, fill=WHITE, line=LINE, radius=0.08)
        label_in(b, [[(name, {"bold": True, "size": 9.5})], [(who, {"size": 7, "color": MUTED})],
                     [(price, {"bold": True, "size": 14, "color": RED}), ("/month", {"size": 7, "color": GREY})],
                     [(items, {"size": 7, "color": INK})], [(meta, {"size": 6.5, "color": MUTED})]],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        b.text_frame.margin_left = Inches(0.12)
        b.text_frame.margin_top = Inches(0.07)
        sl.anim(b, "rise", next(d), 500)
    footer(sl, "Screens from the working prototype. Prices from its rules engine: 5% off for 3+ categories, setup waived for micro firms on 12+ months, 24 months is cheaper.")
    sl.notes("Demo flow: a dental clinic owner chats in Hindi, shares a GSTIN that pre-fills the profile, gets three plans, toggles items, "
             "verifies the business in minutes and tracks installation without calling.")
    return sl


# ------------------------------------------------------------------ 4 · Smart KYC + privacy
def kyc(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "Near-instant KYC, DPDP-compliant (Q3)", "Documents checked in seconds, against the source of truth")
    layers = [("Quality", "blur score, auto-straighten"), ("Format", "GSTIN checksum repairs OCR errors"),
              ("Completeness", "GST/Udyam, signatory ID, address proof"), ("Registry", "GSTIN active? names & address match"),
              ("Consistency", "same business on every document"), ("Recency", "utility bill ≤ 90 days, ID valid")]
    d = stagger(450, 130)
    y = 1.58
    for i, (h, s) in enumerate(layers):
        b = box(sl, 0.55 + i * 0.06, y, 3.3 - i * 0.06, 0.4, fill=WHITE, line=LINE, radius=0.2)
        label_in(b, [[(f"{i + 1}  {h}", {"bold": True, "size": 8.5}), (f"   {s}", {"size": 7, "color": GREY})]], align=PP_ALIGN.LEFT)
        b.text_frame.margin_left = Inches(0.14)
        sl.anim(b, "rise", next(d), 450)
        y += 0.47
    res = [("K01", "Blocked", "GSTIN cancelled", RED, RED_SOFT), ("K02", "Approved", "tilted scan fixed", GREEN, GREEN_SOFT),
           ("K03", "Approved", "", GREEN, GREEN_SOFT), ("K04", "Fix", "photo too blurry", AMBER, AMBER_SOFT),
           ("K05", "Fix", "Udyam missing → confirm", AMBER, AMBER_SOFT), ("K06", "Approved", "", GREEN, GREEN_SOFT),
           ("K07", "Review", "legal name altered", BLUE, BLUE_SOFT), ("K08", "Approved", "", GREEN, GREEN_SOFT),
           ("K09", "Approved", "", GREEN, GREEN_SOFT), ("K10", "Approved", "", GREEN, GREEN_SOFT),
           ("K11", "Fix", "bill > 90 days old", AMBER, AMBER_SOFT), ("K12", "Approved", "", GREEN, GREEN_SOFT)]
    text(sl, 4.1, 1.55, 3.0, 0.2, "12 SAMPLE APPLICANTS, ALL CALLED CORRECTLY", size=6.5, bold=True, color=MUTED)
    d = stagger(1150, 70)
    for i, (k, v, why, fg, bg) in enumerate(res):
        bx, by = 4.1 + (i % 3) * 0.98, 1.8 + (i // 3) * 0.66
        b = box(sl, bx, by, 0.92, 0.58, fill=bg, radius=0.14)
        label_in(b, [[(k, {"bold": True, "size": 8.5, "color": INK}), (f"  {v}", {"bold": True, "size": 7, "color": fg})],
                     [(why or "clean", {"size": 6, "color": GREY})]])
        sl.anim(b, "fade", next(d), 350)
    g, h = phone(sl, "s5-kyc-k01.png", 7.35, 1.55, 1.55)
    pic = g.shapes[1]
    crop_h = 2.75
    pic.crop_bottom = 1 - crop_h / h
    pic.height = Inches(crop_h)
    g.shapes[0].height = Inches(crop_h + 0.1)
    sl.anim(g, "rise", 1700, 600)
    strip = box(sl, 0.55, 4.5, 8.9, 0.55, fill=PANEL, radius=0.14)
    label_in(strip, [[("Privacy by design  ", {"bold": True, "color": RED}),
                      ("purpose-wise consent, optional purposes unticked · documents never sent to the AI; Aadhaar, PAN and account numbers "
                       "stripped from chat · photos encrypted and deleted once decided · IDs masked · audit log of every decision", {"color": INK})]],
             size=7.5, align=PP_ALIGN.LEFT)
    strip.text_frame.margin_left = Inches(0.16)
    sl.anim(strip, "rise", 2100, 500)
    footer(sl, "K01–K12: specimen documents and mock GSTIN/Udyam registries from the case pack; verdicts from the prototype vs our own answer key.")
    sl.notes("K01's certificate looks perfect but GST records say cancelled; only a registry check catches it. Owners fix most issues themselves "
             "(retake, DigiLocker, one-tap Udyam confirmation); only suspected tampering goes to a person.")
    return sl


# ------------------------------------------------------------------ 6 · architecture + evidence
def architecture(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "How it's built", "A working prototype: the AI talks, the rules decide")
    d = stagger(450, 110)

    def col_title(x, y, t):
        text(sl, x, y, 2.3, 0.2, t.upper(), size=6.5, bold=True, color=MUTED)

    col_title(0.55, 1.55, "Channels")
    for i, (h, s) in enumerate([("Owner app", "phone web app · 10 languages · voice"), ("WhatsApp updates", "with the owner's opt-in"),
                                ("Sales & partner console", "lead scores · reviews · assisted mode")]):
        b = box(sl, 0.55, 1.78 + i * 0.78, 1.9, 0.66, fill=WHITE, line=LINE, radius=0.12)
        label_in(b, [[(h, {"bold": True, "size": 9})], [(s, {"size": 7, "color": GREY})]])
        sl.anim(b, "rise", next(d), 400)
    core = box(sl, 2.75, 1.55, 3.75, 2.75, fill=PANEL, radius=0.06)
    label_in(core, [[("Backend (FastAPI)", {"bold": True, "size": 8, "color": MUTED})]], anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT)
    core.text_frame.margin_left = Inches(0.12)
    core.text_frame.margin_top = Inches(0.07)
    sl.anim(core, "fade", next(d), 400)
    mods = [("AI advisor", "5 tools · price guard", False), ("Rules engine", "eligibility · price", True), ("Smart KYC", "OCR · 6 check layers", False),
            ("Consent & audit", "DPDP ledger", False), ("Order tracker", "states · ETAs · SLA", False), ("Lead score", "explainable model", False)]
    for i, (h, s, hot) in enumerate(mods):
        bx, by = 2.9 + (i % 2) * 1.75, 1.92 + (i // 2) * 0.76
        b = box(sl, bx, by, 1.62, 0.64, fill=RED if hot else WHITE, line=None if hot else LINE, radius=0.12)
        label_in(b, [[(h, {"bold": True, "size": 9, "color": WHITE if hot else INK})], [(s, {"size": 7, "color": WHITE if hot else GREY})]])
        sl.anim(b, "rise", next(d), 400)
    right = [("AI services", "Gemini (Claude optional) for conversation only · Tesseract OCR runs locally"),
             ("Mock integrations", "GSTIN · Udyam · DigiLocker · e-sign · UPI AutoPay · fibre feasibility"),
             ("Data", "SQLite store · encrypted document vault with auto-delete · catalogue & registries")]
    col_title(6.8, 1.55, "Around the core")
    for i, (h, s) in enumerate(right):
        b = box(sl, 6.8, 1.78 + i * 0.86, 2.65, 0.76, fill=WHITE, line=LINE, radius=0.1)
        label_in(b, [[(h, {"bold": True, "size": 9})], [(s, {"size": 7, "color": GREY})]], align=PP_ALIGN.LEFT)
        b.text_frame.margin_left = Inches(0.12)
        sl.anim(b, "rise", next(d), 400)
    for i in range(3):
        sl.anim(arrow(sl, 2.47, 2.11 + i * 0.78, 2.73, 2.11 + i * 0.78), "fade", 1500, 300)
        sl.anim(arrow(sl, 6.52, 2.16 + i * 0.86, 6.78, 2.16 + i * 0.86), "fade", 1550, 300)
    proofs = [("128", "automated tests"), ("30 / 30", "advisor test conversations"), ("12 / 12", "KYC applicants called correctly"),
              ("49 / 49", "rule-breaking Q2 sales rejected"), ("5,000", "lead profiles get valid bundles")]
    d = stagger(1700, 110)
    for i, (big, small) in enumerate(proofs):
        b = box(sl, 0.55 + i * 1.8, 4.45, 1.7, 0.6, fill=WHITE, line=LINE, radius=0.14)
        label_in(b, [[(big, {"bold": True, "size": 12, "color": RED})], [(small, {"size": 6.5, "color": GREY})]])
        sl.anim(b, "rise", next(d), 400)
    footer(sl, "Prices, eligibility and KYC verdicts are deterministic code; a guard rejects AI replies with unverified prices; a rule-based advisor covers AI outages.")
    sl.notes("Single FastAPI backend serving the owner app, WhatsApp notifications and the console. AI is used for conversation only. "
             "Swapping mocks for GSTN, Udyam, DigiLocker and NPCI APIs is an adapter change.")
    return sl


def main(template: str, out: str) -> None:
    prs = Presentation(template)
    blobs = []
    for s in prs.slides:
        pics = [sh for sh in s.shapes if sh.shape_type == 13]
        blobs.append(pics[0].image.blob if pics else None)
    cover_bg, content_bg = blobs[0], blobs[1]
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        prs.part.drop_rel(sldId.rId)
        sldIdLst.remove(sldId)
    builders = [cover, problem_and_target, solution, kyc, partners, architecture, metrics, rollout]
    for i, b in enumerate(builders):
        sl = b(prs, cover_bg if i == 0 else content_bg)
        apply_motion(sl)
    prs.save(out)
    print(f"wrote {out} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(HERE.parents[2] / "Submission Template_Sync.pptx"),
         sys.argv[2] if len(sys.argv) > 2 else str(HERE / "UdyamSaathi_Submission_7_Slides.pptx"))
