"""Deterministic advisor: slot filling with templates in English and Hindi."""
from __future__ import annotations

from ..engine.models import NEEDS, SEGMENT_LABELS
from . import nlu, profile_slots
from .session import AdvisorSession
from .tools import ToolError, run_tool

T = {
    "en": {
        "greet": "Namaste! I'm Udyam Saathi from Accel Business. I'll suggest the right internet, phone and digital plan "
                 "for your business in a few questions. If you have a GSTIN, share it and I'll fill in your details. "
                 "Otherwise just tell me what your business does and in which city.",
        "ask_gstin": "Do you have a GSTIN? Share it and I'll fill your details automatically, or say 'no'.",
        "ask_business_type": "What kind of business do you run? For example a kirana store, clinic, coaching centre or restaurant chain.",
        "ask_city": "Which city is your business in?",
        "ask_employees": "How many people work in the business, including you? And how many shops or branches do you have?",
        "ask_needs": "What do you need help with? For example billing/UPI, CCTV, WhatsApp for customers, business email, "
                     "Wi-Fi for customers. Also, what internet do you use today and roughly what do you pay per month?",
        "gstin_ok": "Found {name} ({city}). GST status: {status}.",
        "gstin_bad_status": "Note: this GSTIN shows as {status} in the GST registry, so I can only suggest products that don't need GST registration.",
        "gstin_error": "That GSTIN doesn't look right ({error}). Please check it, or say 'no' to continue without it.",
        "recommend": "For your {business} in {city}, I recommend the Recommended plan: {items}. "
                     "It costs ₹{total}/month including GST{setup}, and can be ready in about {days} days.{diff} "
                     "Use the cards below to switch items on or off or choose another plan.",
        "setup": " plus ₹{setup} one-time setup",
        "setup_free": " with no setup charge",
        "more": " That is ₹{diff}/month more than you pay today, for a lot more.",
        "less": " That saves you ₹{diff}/month compared to today.",
        "cheaper": "The Essential plan keeps just the basics: {items}, at ₹{total}/month including GST.",
        "handoff": "Sure. An Accel Business expert will call you within 4 working hours.",
        "followup": "Anything else you'd like to add or change? You can also tap 'Continue' on a plan to move to checkout.",
        "added": "Added {need} to your plan.",
        "blocked": "{name} isn't available for you yet: {why}",
        "notes": "{note}",
    },
    "hi": {
        "greet": "नमस्ते! मैं Accel Business का Udyam Saathi हूँ। कुछ सवालों में मैं आपके बिज़नेस के लिए सही इंटरनेट, फ़ोन और डिजिटल प्लान "
                 "बताऊँगा। अगर आपके पास GSTIN है तो बताइए, मैं आपकी जानकारी अपने आप भर दूँगा। नहीं तो बताइए आपका बिज़नेस क्या है और किस शहर में है।",
        "ask_gstin": "क्या आपके पास GSTIN है? बताइए, मैं जानकारी अपने आप भर दूँगा। नहीं है तो 'नहीं' लिखिए।",
        "ask_business_type": "आपका बिज़नेस किस तरह का है? जैसे किराना दुकान, क्लिनिक, कोचिंग सेंटर या रेस्टोरेंट।",
        "ask_city": "आपका बिज़नेस किस शहर में है?",
        "ask_employees": "आपके बिज़नेस में आपको मिलाकर कितने लोग काम करते हैं? और कितनी दुकानें या ब्रांच हैं?",
        "ask_needs": "आपको किस चीज़ की ज़रूरत है? जैसे बिलिंग/UPI, CCTV कैमरा, ग्राहकों के लिए WhatsApp, बिज़नेस ईमेल, ग्राहकों के लिए Wi-Fi। "
                     "और अभी आप कौन सा इंटरनेट इस्तेमाल करते हैं, महीने का लगभग कितना खर्च है?",
        "gstin_ok": "{name} ({city}) मिल गया। GST स्थिति: {status}।",
        "gstin_bad_status": "ध्यान दें: GST रजिस्ट्री में यह GSTIN {status} है, इसलिए मैं सिर्फ़ वही प्रोडक्ट सुझा सकता हूँ जिनके लिए GST ज़रूरी नहीं है।",
        "gstin_error": "यह GSTIN सही नहीं लग रहा ({error})। कृपया जाँच लें, या GSTIN के बिना आगे बढ़ने के लिए 'नहीं' लिखें।",
        "recommend": "{city} में आपके {business} के लिए मेरा सुझाव Recommended प्लान है: {items}। "
                     "इसकी कीमत GST सहित ₹{total}/महीना है{setup}, और लगभग {days} दिन में चालू हो सकता है।{diff} "
                     "नीचे के कार्ड में आप चीज़ें जोड़-हटा सकते हैं या दूसरा प्लान चुन सकते हैं।",
        "setup": ", साथ में ₹{setup} एक बार का सेटअप",
        "setup_free": ", कोई सेटअप चार्ज नहीं",
        "more": " यह अभी के खर्च से ₹{diff}/महीना ज़्यादा है, पर बहुत ज़्यादा सुविधाओं के साथ।",
        "less": " इससे अभी के मुकाबले ₹{diff}/महीना की बचत होगी।",
        "cheaper": "Essential प्लान में सिर्फ़ ज़रूरी चीज़ें हैं: {items}, GST सहित ₹{total}/महीना।",
        "handoff": "ज़रूर। Accel Business के विशेषज्ञ 4 कामकाजी घंटों में आपको कॉल करेंगे।",
        "followup": "कुछ और जोड़ना या बदलना है? चेकआउट के लिए किसी प्लान पर 'Continue' दबाइए।",
        "added": "{need} आपके प्लान में जोड़ दिया।",
        "blocked": "{name} अभी आपके लिए उपलब्ध नहीं है: {why}",
        "notes": "{note}",
    },
}


def _t(session: AdvisorSession, key: str, **kw) -> str:
    table = T.get(session.lang, T["en"])
    return table.get(key, T["en"][key]).format(**kw)


def greeting(session: AdvisorSession) -> str:
    return _t(session, "greet")


def _detect_lang(text: str, current: str) -> str:
    if any("ऀ" <= ch <= "ॿ" for ch in text):
        return "hi"
    return current


def respond(session: AdvisorSession, text: str) -> str:
    session.lang = _detect_lang(text, session.lang)
    facts = nlu.extract(text, session.last_asked)
    parts: list[str] = []

    if facts.get("human"):
        run_tool(session, "handoff_to_human", {"reason": "Owner asked to speak to a person"})
        return _t(session, "handoff")

    if facts.get("gstin"):
        try:
            r = run_tool(session, "lookup_gstin", {"gstin": facts["gstin"]})
            parts.append(_t(session, "gstin_ok", name=r["trade_name"], city=r.get("city") or r["state"], status=r["status"]))
            if r["status"] != "Active":
                parts.append(_t(session, "gstin_bad_status", status=r["status"]))
        except ToolError as e:
            session.last_asked = "gstin"
            return _t(session, "gstin_error", error=str(e))

    # Once known, business type and city only change when we are asking for them (avoids
    # "one clinic" overwriting "Dental clinic").
    for key in ("business_type", "city"):
        if session.profile.get(key) and session.last_asked != key and key in facts:
            facts.pop(key)
    updates = {k: v for k, v in facts.items() if k in ("business_type", "city", "employees", "sites", "has_gstin",
                                                       "current_internet", "monthly_telecom_spend", "needs", "fibre_feasible")}
    if updates:
        run_tool(session, "update_profile", updates)
    if session.last_asked == "needs" and (facts.get("needs") or facts.get("done") or facts.get("current_internet")
                                          or facts.get("monthly_telecom_spend") is not None or updates == {}):
        if "needs" not in session.asked:
            session.asked.append("needs")

    # Already recommended: handle follow-ups.
    if session.recommendation:
        if facts.get("cheaper"):
            t = session.recommendation["tiers"][0]
            return _t(session, "cheaper", items=_items(t), total=_fmt(t["quote"]["monthly_total"]))
        if facts.get("needs") or updates:
            return " ".join(parts + [_recommend(session)])
        return _t(session, "followup")

    nxt = _next_question(session)
    if nxt:
        session.last_asked = nxt
        if nxt not in session.asked:
            session.asked.append(nxt)
        parts.append(_t(session, f"ask_{nxt}"))
        return " ".join(parts)
    return " ".join(parts + [_recommend(session)])


def _next_question(session: AdvisorSession) -> str | None:
    p = session.profile
    if not p.get("business_type"):
        return "business_type"
    if not p.get("city"):
        return "city"
    if not p.get("employees"):
        return "employees"
    if "needs" not in session.asked and not p.get("needs"):
        return "needs"
    if "gstin" not in session.asked and not p.get("gstin") and "has_gstin" not in p:
        return "gstin"
    return None


def _fmt(n: int) -> str:
    s = str(abs(int(n)))
    if len(s) > 3:  # Indian digit grouping: 1,23,456
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return s


def _items(tier: dict) -> str:
    return ", ".join(f"{i['name']}" + (f" ×{i['qty']}" if i["qty"] > 1 else "") for i in tier["items"])


def _recommend(session: AdvisorSession) -> str:
    out = run_tool(session, "recommend_bundle", {})
    rec = session.recommendation
    tier = next(t for t in rec["tiers"] if t["tier"] == "recommended")
    q = tier["quote"]
    setup = _t(session, "setup", setup=_fmt(q["setup_total"])) if q["setup_total"] else _t(session, "setup_free")
    diff = ""
    if q["monthly_difference"] is not None:
        d = q["monthly_difference"]
        diff = _t(session, "more" if d > 0 else "less", diff=_fmt(abs(d))) if d else ""
    p = session.profile
    msg = _t(session, "recommend", business=p.get("business_type", "business").lower(), city=p.get("city", ""),
             items=_items(tier), total=_fmt(q["monthly_total"]), setup=setup, days=q["earliest_activation_days"], diff=diff)
    notes = [_localise_note(session, n) for n in (out.get("notes") or [])]
    if notes:
        msg += " " + " ".join(notes)
    session.last_asked = None
    return msg


def _localise_note(session: AdvisorSession, note: str) -> str:
    if session.lang != "hi":
        return note
    if note.startswith("Register for GST to unlock:"):
        return "GST रजिस्ट्रेशन करवाने पर ये भी मिल सकते हैं:" + note.split(":", 1)[1]
    if note.startswith("Your GSTIN is"):
        status = "रद्द" if "cancelled" in note else "निलंबित"
        return f"आपका GSTIN {status} है, इसलिए GST रजिस्ट्रेशन वाली सेवाएँ नहीं दी जा सकतीं।"
    if note.startswith("A leased line is not possible"):
        return "अभी लीज़्ड लाइन संभव नहीं है, इसलिए हम बिज़नेस फ़ाइबर सुझा रहे हैं।"
    return note


def describe_need(need: str) -> str:
    return NEEDS.get(need, need)


__all__ = ["respond", "greeting", "SEGMENT_LABELS"]
