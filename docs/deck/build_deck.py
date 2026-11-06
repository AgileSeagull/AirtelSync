"""Build the 10-slide Udyam Saathi business case on the official SYNC submission template.

    pip install -r docs/deck/requirements.txt
    python docs/deck/build_deck.py "path/to/Submission Template_Sync.pptx" docs/deck/UdyamSaathi_Business_Case.pptx

Every figure on the slides comes from smb_leads.csv / the mock registries / the prototype's
test results (see notes on each slide). Animations are native PowerPoint entrance effects
(fade, rise, wipe) that play automatically in sequence; slides use fade transitions.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).parent
IMG = HERE / "img"

# ------------------------------------------------------------------ design tokens
RED = RGBColor(0xE4, 0x00, 0x00)
RED_SOFT = RGBColor(0xFD, 0xEC, 0xEC)
INK = RGBColor(0x1B, 0x1B, 0x1F)
GREY = RGBColor(0x5F, 0x63, 0x68)
MUTED = RGBColor(0x8A, 0x8D, 0x93)
LINE = RGBColor(0xE3, 0xE4, 0xE8)
PANEL = RGBColor(0xF5, 0xF6, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x1E, 0x8E, 0x3E)
GREEN_SOFT = RGBColor(0xE6, 0xF4, 0xEA)
AMBER = RGBColor(0xB2, 0x6A, 0x00)
AMBER_SOFT = RGBColor(0xFE, 0xF3, 0xE0)
BLUE = RGBColor(0x1A, 0x5F, 0xB4)
BLUE_SOFT = RGBColor(0xE8, 0xF0, 0xFE)
BAR = RGBColor(0xC9, 0xCB, 0xD1)
FONT = "Montserrat"


# ------------------------------------------------------------------ helpers
class Slide:
    def __init__(self, prs, bg_blob: bytes | None):
        layout = next(l for l in prs.slide_layouts if l.name == "BLANK")
        self.s = prs.slides.add_slide(layout)
        for ph in list(self.s.placeholders):
            ph._element.getparent().remove(ph._element)
        if bg_blob:
            self.s.shapes.add_picture(io.BytesIO(bg_blob), 0, 0, prs.slide_width, prs.slide_height)
        self.anims: list[tuple[int, str, int, int]] = []

    def anim(self, shape, effect="fade", delay=0, dur=500):
        self.anims.append((shape.shape_id, effect, delay, dur))
        return shape

    def notes(self, text: str):
        self.s.notes_slide.notes_text_frame.text = text


def text(sl: Slide, x, y, w, h, content, size=11, bold=False, color=INK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=1.1, container=None):
    """content: str, or list of paragraphs; a paragraph is a str or a list of (text, style) runs."""
    shapes = container.shapes if container is not None else sl.s.shapes
    tb = shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        runs = para if isinstance(para, list) else [(para, {})]
        for t, st in runs:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = FONT
            f.size = Pt(st.get("size", size))
            f.bold = st.get("bold", bold)
            f.italic = st.get("italic", False)
            f.color.rgb = st.get("color", color)
        if isinstance(para, list) and para and para[0][1].get("space_after"):
            p.space_after = Pt(para[0][1]["space_after"])
    return tb


def box(sl: Slide, x, y, w, h, fill=WHITE, line=None, radius=0.08, shape=MSO_SHAPE.ROUNDED_RECTANGLE, container=None,
        line_w=0.75):
    shapes = container.shapes if container is not None else sl.s.shapes
    s = shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(line_w)
    s.shadow.inherit = False
    s.text_frame.margin_left = s.text_frame.margin_right = Inches(0.08)
    return s


def label_in(shape, content, size=10, bold=False, color=INK, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        runs = para if isinstance(para, list) else [(para, {})]
        for t, st in runs:
            r = p.add_run()
            r.text = t
            r.font.name = FONT
            r.font.size = Pt(st.get("size", size))
            r.font.bold = st.get("bold", bold)
            r.font.color.rgb = st.get("color", color)
    return shape


def group(sl: Slide):
    return sl.s.shapes.add_group_shape()


def header(sl: Slide, kicker: str, title: str):
    k = text(sl, 0.55, 0.74, 7.6, 0.2, kicker.upper(), size=8, bold=True, color=RED)
    t = text(sl, 0.55, 0.92, 8.6, 0.5, title, size=19, bold=True, color=INK, spacing=1.0)
    sl.anim(k, "fade", 0, 400)
    sl.anim(t, "rise", 100, 600)


def footer(sl: Slide, source: str):
    text(sl, 0.55, 5.2, 7.2, 0.2, source, size=6.5, color=MUTED)


def phone(sl: Slide, img: str, x, y, w):
    from PIL import Image  # pillow ships with python-pptx

    iw, ih = Image.open(IMG / img).size
    h = w * ih / iw
    g = group(sl)
    bez = 0.05
    box(sl, x - bez, y - bez, w + 2 * bez, h + 2 * bez, fill=INK, radius=0.09, container=g)
    g.shapes.add_picture(str(IMG / img), Inches(x), Inches(y), Inches(w), Inches(h))
    return g, h


def arrow(sl: Slide, x1, y1, x2, y2, color=MUTED, width=1.25):
    c = sl.s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    tail = etree.SubElement(ln, qn("a:tailEnd"))
    tail.set("type", "triangle")
    tail.set("w", "med")
    tail.set("h", "med")
    return c


# ------------------------------------------------------------------ animations & transitions (raw PresentationML)
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _effect_xml(ids, spid, effect, delay, dur):
    n = lambda: str(next(ids))  # noqa: E731
    tgt = f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
    show = (f'<p:set><p:cBhvr><p:cTn id="{n()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
            f'{tgt}<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>'
            f'<p:to><p:strVal val="visible"/></p:to></p:set>')
    if effect == "wipe":
        preset, sub = 22, 8
        body = (f'<p:animEffect transition="in" filter="wipe(left)"><p:cBhvr><p:cTn id="{n()}" dur="{dur}"/>{tgt}'
                f'</p:cBhvr></p:animEffect>')
    elif effect == "rise":  # "Ascend": fade in while rising slightly
        preset, sub = 42, 0
        body = (f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{n()}" dur="{dur}"/>{tgt}</p:cBhvr></p:animEffect>'
                f'<p:anim calcmode="lin" valueType="num"><p:cBhvr><p:cTn id="{n()}" dur="{dur}" fill="hold"/>{tgt}'
                f'<p:attrNameLst><p:attrName>ppt_x</p:attrName></p:attrNameLst></p:cBhvr><p:tavLst>'
                f'<p:tav tm="0"><p:val><p:strVal val="#ppt_x"/></p:val></p:tav>'
                f'<p:tav tm="100000"><p:val><p:strVal val="#ppt_x"/></p:val></p:tav></p:tavLst></p:anim>'
                f'<p:anim calcmode="lin" valueType="num"><p:cBhvr><p:cTn id="{n()}" dur="{dur}" decel="100000" fill="hold"/>{tgt}'
                f'<p:attrNameLst><p:attrName>ppt_y</p:attrName></p:attrNameLst></p:cBhvr><p:tavLst>'
                f'<p:tav tm="0"><p:val><p:strVal val="#ppt_y+.06"/></p:val></p:tav>'
                f'<p:tav tm="100000"><p:val><p:strVal val="#ppt_y"/></p:val></p:tav></p:tavLst></p:anim>')
    else:  # fade
        preset, sub = 10, 0
        body = (f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{n()}" dur="{dur}"/>{tgt}'
                f'</p:cBhvr></p:animEffect>')
    outer = n()
    return (f'<p:par><p:cTn id="{outer}" presetID="{preset}" presetClass="entr" presetSubtype="{sub}" fill="hold" '
            f'nodeType="withEffect"><p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>{show}{body}'
            f'</p:childTnLst></p:cTn></p:par>')


def apply_motion(sl: Slide, transition="fade"):
    sld = sl.s._element
    # transition
    trans = etree.fromstring(f'<p:transition xmlns:p="{P_NS}" spd="med"><p:{transition}/></p:transition>')
    clr = sld.find(qn("p:clrMapOvr"))
    (clr if clr is not None else sld.find(qn("p:cSld"))).addnext(trans)
    if not sl.anims:
        return
    import itertools

    ids = itertools.count(5)
    effects = "".join(_effect_xml(ids, spid, eff, delay, dur) for spid, eff, delay, dur in sl.anims)
    text_ids = {sh.shape_id for sh in sl.s.shapes if sh.has_text_frame and sh.text_frame.text.strip()}
    bld = "".join(f'<p:bldP spid="{spid}" grpId="0" animBg="1"/>' for spid, *_ in sl.anims if spid in text_ids)
    xml = (f'<p:timing xmlns:p="{P_NS}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
           f'<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
           f'<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/>'
           f'<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>'
           f'<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>{effects}'
           f'</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn>'
           f'<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
           f'<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
           f'</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>'
           + (f'<p:bldLst>{bld}</p:bldLst>' if bld else '') + '</p:timing>')
    sld.find(qn("p:transition")).addnext(etree.fromstring(xml))


def stagger(start, step):
    d = start
    while True:
        yield d
        d += step


# ------------------------------------------------------------------ slides
def cover(prs, blob):
    sl = Slide(prs, blob)
    g = stagger(300, 250)
    sl.anim(text(sl, 0.65, 2.75, 4.2, 0.55, "Udyam Saathi", size=34, bold=True, color=WHITE), "rise", next(g), 700)
    sl.anim(text(sl, 0.65, 3.38, 4.2, 0.6, "Small businesses go digital in one sitting: advice, quote, KYC and activation on a phone, in their language.",
                 size=11.5, color=RGBColor(0xEE, 0xEE, 0xEE), spacing=1.15), "rise", next(g), 700)
    sl.anim(box(sl, 0.65, 4.12, 0.5, 0.04, fill=RED, radius=0), "wipe", next(g), 500)
    sl.anim(text(sl, 0.65, 4.25, 4.2, 0.45, [
        [("Project Udyam Digital  ·  Enterprise Track A", {"bold": True})],
        "Business case · Team CTRL ALT ELITE · github.com/AgileSeagull/AirtelSync"], size=8.5, color=RGBColor(0xC8, 0xC8, 0xC8)),
        "fade", next(g), 600)
    sl.notes("Udyam Saathi: a working digital-first acquisition and onboarding journey for Accel Business's MSME customers. "
             "Everything in this deck is backed by the synthetic case data and the running prototype.")
    return sl


def problem(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "The problem", "Only 7.4% of small-business leads become customers")
    funnel = [("Leads", 5000, None), ("Contacted", 3406, 68), ("Needs assessed", 1974, 58), ("Quote accepted", 861, 44),
              ("KYC complete", 588, 68), ("Activated", 368, 63)]
    d = stagger(500, 130)
    y = 1.62
    for name, n, pct in funnel:
        steep = name == "Quote accepted"
        text(sl, 0.55, y + 0.04, 1.35, 0.25, name, size=9.5, bold=steep, color=RED if steep else INK, align=PP_ALIGN.RIGHT)
        w = 2.6 * n / 5000
        sl.anim(box(sl, 2.02, y, max(w, 0.06), 0.3, fill=RED if steep else BAR, radius=0.15), "wipe", next(d), 450)
        lbl = [(f"{n:,}", {"bold": True, "size": 10})]
        if pct:
            lbl.append((f"  {pct}%", {"size": 8.5, "color": RED if steep else MUTED, "bold": steep}))
        text(sl, 2.1 + w, y + 0.04, 1.2, 0.25, [lbl])
        y += 0.43
    kpis = [("7.4%", "of leads activate"), ("17.6 days", "from lead to activation"), ("₹15,053", "spent per activation"),
             ("3.0", "calls chasing status, per customer")]
    d = stagger(1100, 150)
    for i, (big, small) in enumerate(kpis):
        x = 5.55 + (i % 2) * 1.98
        yy = 1.6 + (i // 2) * 1.12
        b = box(sl, x, yy, 1.86, 1.0, fill=WHITE, line=LINE, radius=0.1)
        label_in(b, [[(big, {"size": 20, "bold": True, "color": RED if i == 0 else INK})], [(small, {"size": 8.5, "color": GREY})]],
                 align=PP_ALIGN.LEFT)
        b.text_frame.margin_left = Inches(0.14)
        sl.anim(b, "rise", next(d), 500)
    ins = box(sl, 0.55, 4.32, 8.9, 0.72, fill=RED_SOFT, radius=0.12)
    label_in(ins, [[("1,624 of the 4,632 lost leads (35%) ", {"bold": True, "color": RED}),
                    ("dropped for reasons a digital journey removes: no visit possible (827), slow or confusing quotes (385), "
                     "paperwork and documents (273), installation delays or no fibre (139).", {})]],
             size=9.5, align=PP_ALIGN.LEFT)
    ins.text_frame.margin_left = Inches(0.18)
    sl.anim(ins, "rise", 1800, 600)
    footer(sl, "Source: smb_leads.csv, 5,000 leads, Apr–Jun 2026 (synthetic). Cost per activation = total acquisition cost ÷ activations.")
    sl.notes("The steepest drop is needs assessed → quote accepted (44%). Field-led selling is slow (17.6 days) and expensive (₹15k per activation). "
             "A third of losses are caused by visits, quotes and paperwork, exactly what a digital journey removes.")
    return sl


def segments(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "Who we target first (Q1)", "Lead with professional offices; micro retail goes self-serve")
    cols = [("Segment", 1.75), ("Share", 0.6), ("Activation", 0.85), ("Cost / activation", 1.15), ("Median bundle", 1.05),
            ("6-mo churn", 0.85), ("Play", 2.65)]
    rows = [
        ("Professional offices", "25%", "11.1%", "₹10,695", "₹6,575", "14%", ("1 · Lead segment: self-serve + inside sales", GREEN, GREEN_SOFT)),
        ("Small multi-site", "15%", "11.0%", "₹15,614", "₹28,080", "11%", ("2 · Digital quote, field-assisted rollout", BLUE, BLUE_SOFT)),
        ("Small manufacturers", "6%", "12.8%", "₹15,324", "₹15,910", "8%", ("3 · Field sales for leased lines and IoT", BLUE, BLUE_SOFT)),
        ("Micro retail & services", "54%", "4.1%", "₹20,007", "₹2,470", "23%", ("Volume · Self-serve only (app + WhatsApp)", AMBER, AMBER_SOFT)),
    ]
    x0, y = 0.55, 1.55
    x = x0
    for name, w in cols:
        text(sl, x, y, w - 0.05, 0.2, name.upper(), size=6.5, bold=True, color=MUTED)
        x += w
    y += 0.24
    d = stagger(450, 140)
    for r in rows:
        g = group(sl)
        box(sl, x0, y, 8.9, 0.36, fill=WHITE, line=LINE, radius=0.18, container=g)
        x = x0 + 0.12
        for i, (name, w) in enumerate(cols[:-1]):
            text(sl, x, y + 0.09, w - 0.08, 0.2, r[i], size=8.5 if i else 9, bold=(i == 0), container=g,
                 color=RED if (i == 3 and r[i] == "₹20,007") else INK)
            x += w if i else w - 0.12
        play, fg, bg = r[-1]
        pill = box(sl, x - 0.02, y + 0.06, 2.6, 0.24, fill=bg, radius=0.5, container=g)
        label_in(pill, play, size=7.5, bold=True, color=fg)
        sl.anim(g, "rise", next(d), 450)
        y += 0.42
    bundles = [
        ("Dukaan Digital", "Kirana, 2 people, Patna", "₹3,004", "Biz Fibre 100 · 2 business SIMs · Cloud POS & UPI billing", "No setup fee · live in 5 days"),
        ("Clinic & Office Pro", "Dental clinic, 12 staff, Kochi", "₹6,701", "Fibre 300 · 2 SIMs · 2 CCTV · email ×7 · security · backup", "₹4,248 setup · live in 5 days"),
        ("Chain Connect", "Restaurant chain, 6 outlets, Pune", "₹23,339", "Fibre 300 ×6 · failover ×6 · POS ×6 · 3 SIMs", "₹28,320 setup · live in 5 days"),
        ("Factory Line", "Textile unit, 80 staff, Surat", "₹18,308", "Leased line 20 · 8 machine IoT · 4 SIMs · email · security", "₹40,120 setup · live in 21 days"),
    ]
    d = stagger(1150, 150)
    for i, (name, who, price, items, meta) in enumerate(bundles):
        bx = 0.55 + i * 2.25
        b = box(sl, bx, 3.62, 2.15, 1.3, fill=WHITE, line=LINE, radius=0.08)
        label_in(b, [[(name, {"bold": True, "size": 10})], [(who, {"size": 7, "color": MUTED})],
                     [(price, {"bold": True, "size": 15, "color": RED}), ("/month incl. GST", {"size": 7, "color": GREY})],
                     [(items, {"size": 7, "color": INK})], [(meta, {"size": 6.5, "color": MUTED})]],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        b.text_frame.margin_left = Inches(0.12)
        b.text_frame.margin_top = Inches(0.08)
        sl.anim(b, "rise", next(d), 500)
    footer(sl, "Segment economics from smb_leads.csv (Q2 activations). Bundles: the prototype's recommendation engine, 12-month plans; 24 months is cheaper.")
    sl.notes("Professional offices convert at 11.1% with ₹6.6k bundles and low churn, and are ideal for self-serve. Micro retail is 54% of leads, "
             "but at ₹20k cost per activation against ₹2.5k a month and 23% churn it only pays back if acquisition is digital.")
    return sl


def journey(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "The solution", "From “what do I need?” to activated, in one sitting")
    steps = [("s1-chat.png", "1  Talk", "≤6 questions in 10 languages, by text or voice; GSTIN fills the details"),
             ("s3-quote.png", "2  Choose", "One monthly price incl. GST; switch add-ons on/off; 12 or 24 months"),
             ("s6-kyc-ok.png", "3  Verify", "Consent, DigiLocker or a photo, checked against GST & Udyam; e-sign"),
             ("s7-track.png", "4  Track", "AutoPay, technician slot, live ETAs and WhatsApp updates; no calls")]
    d = stagger(450, 300)
    w = 1.42
    for i, (img, title, cap) in enumerate(steps):
        cx = 1.45 + i * 2.33
        g, h = phone(sl, img, cx - w / 2, 1.5, w)
        crop_h = min(h, 2.85)
        # crop the long screenshots to a common height
        pic = g.shapes[1]
        if h > crop_h:
            pic.crop_bottom = 1 - crop_h / h
            pic.height = Inches(crop_h)
            g.shapes[0].height = Inches(crop_h + 0.1)
        delay = next(d)
        sl.anim(g, "rise", delay, 600)
        t = text(sl, cx - 1.05, 4.5, 2.1, 0.62, [[(title, {"bold": True, "size": 10.5, "color": RED})], [(cap, {"size": 7.5, "color": GREY})]],
                 align=PP_ALIGN.CENTER)
        sl.anim(t, "fade", delay + 200, 500)
        if i < 3:
            sl.anim(arrow(sl, cx + w / 2 + 0.17, 2.9, cx + 2.33 - w / 2 - 0.17, 2.9, color=RED, width=1.5), "wipe", delay + 300, 300)
    footer(sl, "Screens from the working prototype (Hindi conversation, quote builder, Smart KYC approved, tracker after a fibre-to-AirFiber reroute).")
    sl.notes("Demo flow: a dental clinic owner chats in Hindi, shares a GSTIN that pre-fills the profile, gets three plans, toggles items, "
             "verifies the business in minutes and tracks installation without calling.")
    return sl


def advisor(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "Needs discovery without a salesperson (Q2)", "The AI talks. The rules decide.")
    points = [
        ("Talks like a good advisor", "Gemini (or Claude) chats in the owner's language, by text or voice, and asks at most six questions."),
        ("Knows the business already", "A GSTIN lookup fills the name, city and registration status, so fewer questions and no typos."),
        ("Never invents a price", "Eligibility, dependencies and prices come from a rules engine over the catalogue; a guard blocks any number the engine didn't return."),
        ("Explains and hands over", "Three options with a reason for every item; a person calls back on request or above ₹25k/month."),
    ]
    d = stagger(450, 180)
    y = 1.6
    for i, (h, body) in enumerate(points):
        g = group(sl)
        n = box(sl, 0.55, y + 0.02, 0.3, 0.3, fill=RED, radius=0.3, container=g)
        label_in(n, str(i + 1), size=9, bold=True, color=WHITE)
        text(sl, 1.0, y, 3.75, 0.75, [[(h, {"bold": True, "size": 10.5})], [(body, {"size": 8.5, "color": GREY})]], container=g)
        sl.anim(g, "rise", next(d), 500)
        y += 0.84
    proofs = [("49 / 49", "rule-breaking sales from Q2 rejected by the engine"), ("5,000/5,000", "lead profiles get a valid bundle"),
              ("30 / 30", "advisor test conversations pass (English, Hindi)")]
    d = stagger(1250, 150)
    for i, (big, small) in enumerate(proofs):
        b = box(sl, 5.05 + i * 1.48, 1.6, 1.4, 1.15, fill=WHITE, line=LINE, radius=0.1)
        label_in(b, [[(big, {"bold": True, "size": 13, "color": RED})], [(small, {"size": 7.5, "color": GREY})]])
        sl.anim(b, "rise", next(d), 500)
    flow = [("Owner", "text or voice", PANEL, INK), ("AI model", "conversation", PANEL, INK), ("Tools", "lookup · profile · recommend", PANEL, INK),
            ("Rules engine", "eligibility · price", RED, WHITE), ("Guard", "only engine numbers", PANEL, INK)]
    d = stagger(1800, 160)
    y = 3.2
    for i, (h, s, bg, fg) in enumerate(flow):
        # row 1 left→right: Owner, AI, Tools; row 2 right→left: Rules engine (under Tools), Guard (under AI)
        bx = 5.05 + i * 1.48 if i < 3 else (8.01 if i == 3 else 6.53)
        by = y if i < 3 else y + 0.95
        b = box(sl, bx, by, 1.36, 0.7, fill=bg, radius=0.12, line=None if bg == RED else LINE)
        label_in(b, [[(h, {"bold": True, "size": 9.5, "color": fg})], [(s, {"size": 7, "color": WHITE if bg == RED else GREY})]])
        sl.anim(b, "fade", next(d), 400)
    sl.anim(arrow(sl, 6.41, 3.55, 6.53, 3.55, color=RED), "fade", 2000, 200)
    sl.anim(arrow(sl, 7.89, 3.55, 8.01, 3.55, color=RED), "fade", 2150, 200)
    sl.anim(arrow(sl, 8.69, 3.91, 8.69, 4.14, color=RED), "fade", 2300, 200)
    sl.anim(arrow(sl, 8.0, 4.5, 7.9, 4.5, color=RED), "fade", 2450, 200)
    footer(sl, "Tested with the prototype's eval harness; if the AI is unavailable the advisor continues in a rule-based mode, so the journey never dead-ends.")
    sl.notes("The language model only converses and explains. Every product, eligibility decision and price comes from deterministic code, "
             "so judges' scenarios cannot trip it into selling something the catalogue forbids.")
    return sl


def kyc(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "Near-instant KYC, DPDP-compliant (Q3)", "Documents checked in seconds, against the source of truth")
    layers = [("Quality", "blur score, auto-straighten"), ("Completeness", "GST/Udyam, signatory ID, address proof"),
              ("Format", "GSTIN checksum repairs OCR errors"), ("Registry", "GSTIN active? names & address match records"),
              ("Consistency & recency", "same business everywhere; bill ≤ 90 days")]
    d = stagger(450, 150)
    y = 1.58
    for i, (h, s) in enumerate(layers):
        b = box(sl, 0.55 + i * 0.07, y, 3.25 - i * 0.07, 0.48, fill=WHITE, line=LINE, radius=0.18)
        label_in(b, [[(f"{i + 1}  {h}", {"bold": True, "size": 9}), (f"   {s}", {"size": 7, "color": GREY})]], align=PP_ALIGN.LEFT)
        b.text_frame.margin_left = Inches(0.14)
        sl.anim(b, "rise", next(d), 450)
        y += 0.56
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
                      ("consent per purpose, nothing pre-ticked · documents read on our servers, not sent to the AI · photos encrypted "
                       "and deleted once decided · IDs masked everywhere · every access audit-logged", {"color": INK})]],
             size=8, align=PP_ALIGN.LEFT)
    strip.text_frame.margin_left = Inches(0.16)
    sl.anim(strip, "rise", 2100, 500)
    footer(sl, "K01–K12: specimen documents and mock GSTIN/Udyam registries from the case pack; verdicts from the prototype vs our own answer key.")
    sl.notes("K01's certificate looks perfect but GST records say cancelled; only a registry check catches it. Owners fix most issues themselves "
             "(retake, DigiLocker, one-tap Udyam confirmation); only suspected tampering goes to a person.")
    return sl


def partners(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "Field force & partners (Q4)", "People where they add value, paid for activations")
    text(sl, 0.55, 1.55, 3.9, 0.2, "COST PER ACTIVATION BY CHANNEL, Q2", size=6.5, bold=True, color=MUTED)
    chans = [("WhatsApp", 4026), ("Referral", 4099), ("Inbound call", 5113), ("Website", 6352), ("Channel partner", 20851), ("Field sales", 24335)]
    d = stagger(450, 120)
    y = 1.82
    for name, v in chans:
        dig = v < 10000
        text(sl, 0.55, y + 0.04, 1.15, 0.22, name, size=8.5, align=PP_ALIGN.RIGHT)
        w = 2.35 * v / 24335
        sl.anim(box(sl, 1.82, y, w, 0.27, fill=GREEN if dig else BAR, radius=0.15), "wipe", next(d), 450)
        text(sl, 1.9 + w, y + 0.04, 0.8, 0.22, f"₹{v:,}", size=8.5, bold=True, color=GREEN if dig else INK)
        y += 0.37
    note = text(sl, 0.55, 4.12, 3.95, 0.5, [[("Digital channels cost a fifth as much per customer. ", {"bold": True}),
                                            ("People should do the work digital can't.", {"color": GREY})]], size=8.5)
    sl.anim(note, "fade", 1300, 500)
    roles = [("Inside sales", "Call the leads the advisor didn't close, best first. The lead score lifts conversion: the top 10% activate at 18.2% vs 7.4% overall.", BLUE, BLUE_SOFT),
             ("Field sales", "Multi-site chains and manufacturers: leased lines, site surveys, SD-WAN. The quote and KYC are done online before the visit.", RED, RED_SOFT),
             ("Channel partners", "Tier-2 micro retail: installers and assisted sign-up on the owner's own journey (the owner shares a code). Paid on activation, not on leads.", AMBER, AMBER_SOFT)]
    d = stagger(900, 200)
    for i, (h, body, fg, bg) in enumerate(roles):
        b = box(sl, 4.75, 1.55 + i * 0.95, 4.7, 0.85, fill=WHITE, line=LINE, radius=0.1)
        label_in(b, [[(h, {"bold": True, "size": 10, "color": fg})], [(body, {"size": 8, "color": INK})]], align=PP_ALIGN.LEFT)
        b.text_frame.margin_left = Inches(0.16)
        sl.anim(b, "rise", next(d), 500)
    win = box(sl, 4.75, 4.42, 4.7, 0.62, fill=GREEN_SOFT, radius=0.12)
    label_in(win, [[("Win-back: ", {"bold": True, "color": GREEN}),
                    ("3,026 Q2 leads lost before a needs assessment (unreachable, no time for a visit) get a WhatsApp link to the self-serve advisor.", {})]],
             size=8, align=PP_ALIGN.LEFT)
    win.text_frame.margin_left = Inches(0.16)
    sl.anim(win, "rise", 1700, 500)
    footer(sl, "Cost per activation = acquisition cost of all leads from a channel ÷ its activations (smb_leads.csv). Lead score tested on June leads it never saw (AUC 0.70).")
    sl.notes("The console ranks leads the advisor didn't close by activation probability × value and routes them. Partners stop competing with the "
             "digital journey because they are paid when a customer activates, whichever path they came through.")
    return sl


def architecture(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "How it's built", "A working prototype: rules at the core, AI at the edges")
    d = stagger(450, 110)

    def col_title(x, y, t):
        text(sl, x, y, 2.3, 0.2, t.upper(), size=6.5, bold=True, color=MUTED)

    col_title(0.55, 1.55, "Channels")
    for i, (h, s) in enumerate([("Owner app", "phone web app · 10 languages · voice"), ("WhatsApp updates", "every order change"), ("Sales & partner console", "leads · reviews · assisted mode")]):
        b = box(sl, 0.55, 1.78 + i * 0.78, 1.9, 0.66, fill=WHITE, line=LINE, radius=0.12)
        label_in(b, [[(h, {"bold": True, "size": 9})], [(s, {"size": 7, "color": GREY})]])
        sl.anim(b, "rise", next(d), 400)
    core = box(sl, 2.75, 1.55, 3.75, 2.75, fill=PANEL, radius=0.06)
    label_in(core, [[("Backend (FastAPI)", {"bold": True, "size": 8, "color": MUTED})]], anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT)
    core.text_frame.margin_left = Inches(0.12)
    core.text_frame.margin_top = Inches(0.07)
    sl.anim(core, "fade", next(d), 400)
    mods = [("Advisor", "AI + tools", False), ("Rules engine", "eligibility · price", True), ("Smart KYC", "OCR · 5 check layers", False),
            ("Consent & audit", "DPDP ledger", False), ("Order tracker", "states · ETAs · SLA", False), ("Lead score", "explainable model", False)]
    for i, (h, s, hot) in enumerate(mods):
        bx, by = 2.9 + (i % 2) * 1.75, 1.92 + (i // 2) * 0.76
        b = box(sl, bx, by, 1.62, 0.64, fill=RED if hot else WHITE, line=None if hot else LINE, radius=0.12)
        label_in(b, [[(h, {"bold": True, "size": 9, "color": WHITE if hot else INK})], [(s, {"size": 7, "color": WHITE if hot else GREY})]])
        sl.anim(b, "rise", next(d), 400)
    right = [("AI services", "Gemini or Claude (conversation) · Tesseract OCR runs locally"),
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
    q = box(sl, 0.55, 4.48, 8.9, 0.56, fill=WHITE, line=LINE, radius=0.14)
    label_in(q, [[("Tested  ", {"bold": True, "color": RED}),
                  ("112 automated tests · 30 advisor conversations · 12/12 KYC applicants · 4 end-to-end browser journeys · "
                   "code: github.com/AgileSeagull/AirtelSync", {})]], size=8, align=PP_ALIGN.LEFT)
    q.text_frame.margin_left = Inches(0.16)
    sl.anim(q, "rise", 1800, 500)
    footer(sl, "Government and payment integrations are mocks behind the interfaces a production adapter would implement.")
    sl.notes("Single FastAPI backend serving the owner app, WhatsApp notifications and the console. All decisions are deterministic code; "
             "AI is used for conversation only. Swapping mocks for GSTN, Udyam, DigiLocker and NPCI APIs is an adapter change.")
    return sl


def metrics(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "How we measure success (Q5)", "Five numbers, measured from day one")
    cols = [("Metric", 2.55), ("Q2 baseline", 1.35), ("6-month target", 1.45), ("What moves it", 3.55)]
    rows = [("Lead → activation", "7.4%", "15%", "Self-serve advisor, instant quote, online KYC"),
            ("Lead → activation time", "17.6 days", "≤ 7 days", "Same-day KYC, feasibility before payment, parallel installs"),
            ("Cost per activation", "₹15,053", "≤ ₹5,000", "Digital-first acquisition; partners paid on activation"),
            ("Status-chase calls per customer", "3.0", "≤ 0.5", "Live tracker and proactive WhatsApp updates"),
            ("6-month churn", "15.2%", "≤ 10%", "Right-fit bundles, no rule-breaking sales, fewer delays")]
    x = 0.55
    for name, w in cols:
        text(sl, x + 0.12, 1.55, w, 0.2, name.upper(), size=6.5, bold=True, color=MUTED)
        x += w
    d = stagger(450, 140)
    y = 1.8
    for r in rows:
        g = group(sl)
        box(sl, 0.55, y, 8.9, 0.42, fill=WHITE, line=LINE, radius=0.2, container=g)
        x = 0.55
        for i, (_, w) in enumerate(cols):
            style = {0: dict(bold=True, size=9), 1: dict(size=10, color=GREY), 2: dict(bold=True, size=11, color=RED), 3: dict(size=8, color=INK)}[i]
            text(sl, x + 0.12, y + 0.1, w - 0.15, 0.25, r[i], container=g, **style)
            x += w
        sl.anim(g, "rise", next(d), 450)
        y += 0.48
    cards = [("Micro retail pays back in ~2 months, not 8",
              "Today ₹20,007 to acquire a ₹2,470/month customer. Digital channels cost ₹4,000–6,400 per activation."),
             ("Zero rule-breaking sales",
              "Q2 sold 49 ineligible items and activated 22 customers on cancelled or suspended GSTINs. The rules engine and KYC block both.")]
    d = stagger(1250, 200)
    for i, (h, body) in enumerate(cards):
        b = box(sl, 0.55 + i * 4.5, 4.28, 4.4, 0.78, fill=RED_SOFT if i == 0 else GREEN_SOFT, radius=0.12)
        label_in(b, [[(h, {"bold": True, "size": 9.5, "color": RED if i == 0 else GREEN})], [(body, {"size": 7.5})]], align=PP_ALIGN.LEFT)
        b.text_frame.margin_left = Inches(0.16)
        sl.anim(b, "rise", next(d), 500)
    footer(sl, "Baselines from smb_leads.csv (368 activations, Apr–Jun 2026). Targets assume pilot results in two cities; all five are tracked live in the console.")
    sl.notes("Targets are deliberately conservative: doubling conversion still leaves room below the 11% professional offices already reach with field sales.")
    return sl


def rollout(prs, blob):
    sl = Slide(prs, blob)
    header(sl, "Rollout & risks", "An 8-week pilot, then scale city by city")
    phases = [("Weeks 0–8 · Pilot", "Pune + Kochi · professional offices and micro retail · web + WhatsApp · 2 partner networks"),
              ("Months 3–6 · Scale", "10 cities · voice in 6 languages · live GSTN, Udyam, DigiLocker, UPI AutoPay"),
              ("Months 6–12 · National", "All tier-1/2 cities · partner app · field-assisted multi-site and manufacturing")]
    d = stagger(450, 220)
    for i, (h, s) in enumerate(phases):
        b = box(sl, 0.55 + i * 2.98, 1.58, 2.9, 0.95, fill=RED if i == 0 else WHITE, line=None if i == 0 else LINE,
                radius=0.1)
        fg = WHITE if i == 0 else INK
        label_in(b, [[(h, {"bold": True, "size": 10, "color": fg})], [(s, {"size": 7.5, "color": WHITE if i == 0 else GREY})]], align=PP_ALIGN.LEFT)
        b.text_frame.margin_left = Inches(0.14)
        sl.anim(b, "rise", next(d), 500)
        if i < 2:
            sl.anim(arrow(sl, 3.47 + i * 2.98, 2.05, 3.51 + i * 2.98, 2.05, color=RED, width=2), "fade", 600 + i * 220, 200)
    risks = [("AI gives wrong advice", "AI only talks; rules decide eligibility and price; output guard; tested scenarios; rule-based fallback"),
             ("Forged or altered documents", "Registry checks on every number, cross-document matching, specialist review, Aadhaar e-sign"),
             ("Privacy (DPDP Act 2023)", "Purpose-wise consent, minimal data, photos deleted after decision, masked IDs, audit log"),
             ("Channel conflict", "Partners paid on activation and can complete the owner's own journey with consent"),
             ("Install delays, no fibre", "Feasibility before payment, automatic switch to 5G AirFiber, SLA alerts and escalation")]
    text(sl, 0.55, 2.72, 3, 0.2, "RISK", size=6.5, bold=True, color=MUTED)
    text(sl, 3.0, 2.72, 3, 0.2, "MITIGATION BUILT INTO THE PROTOTYPE", size=6.5, bold=True, color=MUTED)
    d = stagger(1100, 130)
    y = 2.95
    for r, m in risks:
        g = group(sl)
        box(sl, 0.55, y, 8.9, 0.38, fill=WHITE, line=LINE, radius=0.2, container=g)
        text(sl, 0.7, y + 0.1, 2.25, 0.22, r, size=8.5, bold=True, container=g)
        text(sl, 3.0, y + 0.1, 6.35, 0.22, m, size=8, color=GREY, container=g)
        sl.anim(g, "rise", next(d), 450)
        y += 0.43
    footer(sl, "Ask: approve an 8-week, two-city pilot with one inside-sales pod and two partner networks; success = the five metrics on the previous slide.")
    sl.notes("Close with the ask: a two-city pilot measured on the five metrics. Every risk listed has a mitigation that already runs in the prototype.")
    return sl


def main(template: str, out: str) -> None:
    prs = Presentation(template)
    blobs = []
    for s in prs.slides:
        pics = [sh for sh in s.shapes if sh.shape_type == 13]
        blobs.append(pics[0].image.blob if pics else None)
    cover_bg, content_bg = blobs[0], blobs[1]
    # remove the template's two example slides
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        prs.part.drop_rel(sldId.rId)
        sldIdLst.remove(sldId)
    builders = [cover, problem, segments, journey, advisor, kyc, partners, architecture, metrics, rollout]
    for i, b in enumerate(builders):
        sl = b(prs, cover_bg if i == 0 else content_bg)
        apply_motion(sl)
    prs.save(out)
    print(f"wrote {out} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(HERE.parents[2] / "Submission Template_Sync.pptx"),
         sys.argv[2] if len(sys.argv) > 2 else str(HERE / "UdyamSaathi_Business_Case.pptx"))
