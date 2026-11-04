"""Consent notice and ledger (DPDP Act 2023: notice, specific purpose, withdrawal)."""
from __future__ import annotations

import uuid

from .. import store

NOTICE_VERSION = "2026-07-01"

PURPOSES = {
    "kyc_verification": {"required": True},
    "service_updates_whatsapp": {"required": False},
    "marketing": {"required": False},
}

NOTICE = {
    "en": {
        "title": "Before you share documents",
        "intro": "Accel Business needs to verify your business to activate the services you chose. Here is exactly what we collect and why.",
        "collect": ["GST or Udyam certificate", "ID of the person who signs for the business", "One utility bill as address proof"],
        "use": "Only to verify your business and activate this order, as required for telecom services.",
        "how": "Documents are read automatically on our servers. Registration numbers are checked against GST and Udyam records. A specialist sees them only if something needs a manual check.",
        "keep": "Photos are encrypted and deleted as soon as verification finishes (at most 7 days if a manual check is needed). We keep only the verified details and a fingerprint of each file, for the length of your contract plus what the law requires.",
        "rights": "You can withdraw consent before activation from your order page; we then delete your documents. Questions: grievance officer, privacy@accel.example.",
        "purposes": {
            "kyc_verification": "Verify my business for this order (required)",
            "service_updates_whatsapp": "Send installation updates on WhatsApp",
            "marketing": "Tell me about other Accel Business offers",
        },
        "agree": "I agree",
    },
    "hi": {
        "title": "दस्तावेज़ देने से पहले",
        "intro": "आपकी चुनी हुई सेवाएँ चालू करने के लिए Accel Business को आपके बिज़नेस की पुष्टि करनी है। हम क्या लेते हैं और क्यों, यह रहा।",
        "collect": ["GST या Udyam सर्टिफ़िकेट", "बिज़नेस की ओर से साइन करने वाले व्यक्ति का ID", "पते के प्रमाण के लिए एक बिजली/पानी का बिल"],
        "use": "सिर्फ़ आपके बिज़नेस की पुष्टि और इस ऑर्डर को चालू करने के लिए, जैसा टेलीकॉम सेवाओं के लिए ज़रूरी है।",
        "how": "दस्तावेज़ हमारे सर्वर पर अपने आप पढ़े जाते हैं। रजिस्ट्रेशन नंबर GST और Udyam रिकॉर्ड से मिलाए जाते हैं। कोई विशेषज्ञ उन्हें तभी देखता है जब मैनुअल जाँच ज़रूरी हो।",
        "keep": "फ़ोटो एन्क्रिप्ट रहती हैं और जाँच पूरी होते ही मिटा दी जाती हैं (मैनुअल जाँच हो तो अधिकतम 7 दिन)। हम सिर्फ़ पुष्टि किए गए विवरण रखते हैं।",
        "rights": "एक्टिवेशन से पहले आप ऑर्डर पेज से सहमति वापस ले सकते हैं; तब हम आपके दस्तावेज़ मिटा देंगे।",
        "purposes": {
            "kyc_verification": "इस ऑर्डर के लिए मेरे बिज़नेस की पुष्टि करें (ज़रूरी)",
            "service_updates_whatsapp": "इंस्टॉलेशन की जानकारी WhatsApp पर भेजें",
            "marketing": "Accel Business के दूसरे ऑफ़र के बारे में बताएँ",
        },
        "agree": "मैं सहमत हूँ",
    },
}


def notice(lang: str) -> dict:
    return {"version": NOTICE_VERSION, **NOTICE.get(lang, NOTICE["en"])}


def record(subject: str, purposes: list[str], lang: str, channel: str = "web") -> dict:
    if "kyc_verification" not in purposes:
        raise ValueError("KYC verification consent is required to continue")
    unknown = [p for p in purposes if p not in PURPOSES]
    if unknown:
        raise ValueError(f"Unknown purposes: {unknown}")
    c = {"id": "C" + uuid.uuid4().hex[:10], "subject": subject, "purposes": sorted(set(purposes)), "lang": lang,
         "channel": channel, "notice_version": NOTICE_VERSION, "granted_at": store.now(), "withdrawn_at": None}
    store.put("consents", c["id"], c)
    audit("consent.granted", subject, {"consent_id": c["id"], "purposes": c["purposes"]})
    return c


def withdraw(consent_id: str) -> dict | None:
    c = store.get("consents", consent_id)
    if c and not c["withdrawn_at"]:
        c["withdrawn_at"] = store.now()
        store.put("consents", consent_id, c)
        audit("consent.withdrawn", c["subject"], {"consent_id": consent_id})
    return c


def audit(action: str, entity: str, detail: dict | None = None, actor: str = "system") -> None:
    e = {"id": uuid.uuid4().hex, "at": store.now(), "actor": actor, "action": action, "entity": entity, "detail": detail or {}}
    store.put("audit", e["id"], e)
