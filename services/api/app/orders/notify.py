"""Owner notifications. Every message is stored in an outbox the tracker shows; if Twilio
WhatsApp credentials are configured it is also sent for real (optional, untested without creds)."""
from __future__ import annotations

import logging
import os
import time
import uuid

import httpx

from .. import store

log = logging.getLogger("notify")

TEMPLATES = {
    "en": {
        "KYCVerified": "✅ {name}: your business is verified. Next: set up UPI AutoPay to book installation. Track: {link}",
        "MandateSet": "💳 AutoPay set up. We're checking your address and booking a technician. Track: {link}",
        "Rerouted": "📡 {note} Track: {link}",
        "InstallScheduled": "📅 Technician visit {slot}, 10am–1pm. All services ready by {eta}. Track: {link}",
        "Delayed": "⚠️ Sorry, your installation is delayed. New date: {eta}. Your area lead is on it; no need to call. Track: {link}",
        "Installed": "🔧 Installation done and tested. Activation within a few hours. Track: {link}",
        "Activated": "🎉 Your Accel Business services are live! Refer a business owner and get one month free. {link}",
    },
    "hi": {
        "KYCVerified": "✅ {name}: आपका बिज़नेस वेरिफ़ाई हो गया। अगला कदम: इंस्टॉलेशन बुक करने के लिए UPI AutoPay चालू करें। ट्रैक: {link}",
        "MandateSet": "💳 AutoPay चालू हो गया। हम पता जाँचकर टेक्नीशियन बुक कर रहे हैं। ट्रैक: {link}",
        "Rerouted": "📡 {note} ट्रैक: {link}",
        "InstallScheduled": "📅 टेक्नीशियन {slot} को सुबह 10 से 1 बजे के बीच आएँगे। सभी सेवाएँ {eta} तक तैयार। ट्रैक: {link}",
        "Delayed": "⚠️ माफ़ कीजिए, इंस्टॉलेशन में देरी है। नई तारीख: {eta}। आपके क्षेत्र के लीड इस पर काम कर रहे हैं; कॉल करने की ज़रूरत नहीं। ट्रैक: {link}",
        "Installed": "🔧 इंस्टॉलेशन पूरा और टेस्ट हो गया। कुछ घंटों में सेवाएँ चालू। ट्रैक: {link}",
        "Activated": "🎉 आपकी Accel Business सेवाएँ चालू हैं! किसी बिज़नेस मालिक को रेफ़र करें और एक महीना मुफ़्त पाएँ। {link}",
    },
}


def send(order, event: str, lang: str = "en", **kw) -> dict | None:
    tpl = TEMPLATES.get(lang, TEMPLATES["en"]).get(event) or TEMPLATES["en"].get(event)
    if not tpl:
        return None
    name = (order.business or {}).get("trade_name") or (order.business or {}).get("business_type") or "Your business"
    link = f"{os.getenv('UDYAM_PUBLIC_URL', 'http://localhost:8000')}/#/track/{order.id}"
    text = tpl.format(name=name, link=link, **{k: v for k, v in kw.items() if v is not None})
    msg = {"id": uuid.uuid4().hex[:12], "order_id": order.id, "event": event, "channel": "whatsapp", "text": text,
           "at": store.now(), "seq": time.time_ns(), "delivery": "outbox"}
    msg["delivery"] = _twilio(text) or "outbox"
    store.put("notifications", msg["id"], msg)
    return msg


def for_order(order_id: str) -> list[dict]:
    return sorted((m for m in store.all("notifications") if m["order_id"] == order_id), key=lambda m: m.get("seq", 0))


def _twilio(text: str) -> str | None:
    sid, token = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN")
    frm, to = os.getenv("TWILIO_WHATSAPP_FROM"), os.getenv("UDYAM_DEMO_WHATSAPP_TO")
    if not (sid and token and frm and to):
        return None
    try:
        r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", auth=(sid, token),
                       data={"From": f"whatsapp:{frm}", "To": f"whatsapp:{to}", "Body": text}, timeout=10)
        return "whatsapp" if r.status_code < 300 else f"failed:{r.status_code}"
    except httpx.HTTPError as e:
        log.warning("WhatsApp send failed: %s", e)
        return "failed"
