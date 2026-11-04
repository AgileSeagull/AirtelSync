"""Rule-based understanding for the scripted advisor (English, Hindi, Hinglish).

Not meant to rival the LLM, but it keeps the journey working offline, in tests and
whenever the LLM is unavailable. Extracted facts flow through the same tools."""
from __future__ import annotations

import re
from typing import Any

from ..engine.reference import CITY_ALIASES, business_types, cities

_DEV = str.maketrans("०१२३४५६७८९", "0123456789")
GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")

BUSINESS_SYNONYMS = {
    "kirana": "Kirana store", "grocery": "Kirana store", "general store": "Kirana store", "किराना": "Kirana store",
    "medical store": "Pharmacy", "chemist": "Pharmacy", "दवा": "Pharmacy", "मेडिकल": "Pharmacy",
    "salon": "Salon", "parlour": "Salon", "parlor": "Salon", "सैलून": "Salon", "पार्लर": "Salon",
    "bakery": "Bakery", "बेकरी": "Bakery", "sweet": "Sweet shop", "mithai": "Sweet shop", "मिठाई": "Sweet shop",
    "clinic": "Clinic", "क्लिनिक": "Clinic", "dentist": "Dental clinic", "hospital": "Clinic",
    "डेंटल क्लिनिक": "Dental clinic", "फिज़ियो क्लिनिक": "Physiotherapy clinic", "डेंटल": "Dental clinic", "दाँतों": "Dental clinic", "दांतों": "Dental clinic", "फिज़ियो": "Physiotherapy clinic",
    "फिजियो": "Physiotherapy clinic", "लैब": "Diagnostic lab", "पैथोलॉजी": "Diagnostic lab", "फार्मेसी": "Pharmacy",
    "सीए": "CA firm", "वकील": "Law office", "जिम": "Gym", "स्कूल": "Pre-school", "प्रिंटिंग": "Printing press",
    "ट्रैवल": "Travel agency", "इलेक्ट्रॉनिक्स": "Electronics shop", "हार्डवेयर": "Hardware store", "स्टेशनरी": "Stationery shop",
    "coaching": "Coaching centre", "tuition": "Coaching centre", "कोचिंग": "Coaching centre",
    "ca firm": "CA firm", "chartered accountant": "CA firm", "lawyer": "Law office", "advocate": "Law office",
    "restaurant": "Restaurant", "cafe": "Restaurant", "रेस्टोरेंट": "Restaurant", "ढाबा": "Restaurant", "dhaba": "Restaurant",
    "hotel": "Budget hotel group", "होटल": "Budget hotel group",
    "factory": "Manufacturing unit", "फैक्ट्री": "Manufacturing unit", "कारखाना": "Manufacturing unit",
    "boutique": "Boutique", "बुटीक": "Boutique", "mobile shop": "Mobile repair shop", "mobile repair": "Mobile repair shop",
    "hardware": "Hardware store", "stationery": "Stationery shop", "optical": "Optician", "gym": "Gym",
    "real estate": "Real estate agency", "travel": "Travel agency", "insurance": "Insurance agency",
    "shop": "Retail shop", "दुकान": "Retail shop", "store": "Retail shop",
}

NEED_KEYWORDS = {
    "cctv": ["cctv", "camera", "कैमरा", "सीसीटीवी", "surveillance"],
    "billing_pos": ["billing", "pos", "upi", "inventory", "बिलिंग", "बिल ", "invoice", "card payment"],
    "whatsapp": ["whatsapp", "व्हाट्सएप", "व्हाट्सऐप"],
    "sms": ["sms", "एसएमएस", "bulk message"],
    "website": ["website", "वेबसाइट", "online presence", "domain"],
    "email_office": ["email", "e-mail", "ईमेल", "office suite", "gmail", "video meeting"],
    "backup": ["backup of", "data backup", "cloud backup", "बैकअप", "backup"],
    "device_security": ["antivirus", "virus", "ransomware", "malware"],
    "firewall": ["firewall"],
    "guest_wifi": ["wifi", "wi-fi", "वाईफाई", "वाई-फाई", "guest"],
    "failover": ["failover", "internet down", "always online", "backup internet", "never go down"],
    "telephony": ["ivr", "call recording", "landline", "office phone", "telephony"],
    "toll_free": ["toll free", "toll-free", "1800"],
    "static_ip": ["static ip", "fixed ip", "remote access"],
    "machine_monitoring": ["machine", "iot", "energy monitoring", "मशीन"],
    "fleet_tracking": ["vehicle", "gps", "fleet", "truck", "delivery bike", "गाड़ी", "गाड़ियों"],
    "multi_site_network": ["sd-wan", "sdwan", "central management", "all branches connected"],
    "dedicated_line": ["leased line", "dedicated line", "dedicated internet", "sla"],
    "high_speed": ["high speed", "1 gbps", "1gbps", "very fast", "heavy usage", "large files"],
    "mobile_lines": ["sim", "postpaid", "mobile number", "mobile connection", "सिम", "मोबाइल नंबर"],
}

NO_WORDS = ["no", "nope", "nahi", "nahin", "नहीं", "नही", "don't have", "dont have", "not registered", "na "]
DONE_WORDS = ["that's all", "thats all", "nothing else", "bas", "बस", "no more", "only internet", "just internet"]
HUMAN_WORDS = ["human", "person", "agent", "call me", "callback", "call back", "talk to someone", "executive",
               "बात कराओ", "कॉल करें", "कॉल करो", "किसी से बात"]

INTERNET_KEYWORDS = [("hotspot", "Mobile hotspot"), ("हॉटस्पॉट", "Mobile hotspot"), ("mobile data", "Mobile hotspot"),
                     ("leased line", "Leased line"), ("home broadband", "Home broadband"), ("broadband", "Business broadband"),
                     ("no internet", "None"), ("इंटरनेट नहीं", "None")]


def _norm(text: str) -> str:
    return " " + text.translate(_DEV).lower() + " "


def extract(text: str, last_asked: str | None) -> dict[str, Any]:
    t = _norm(text)
    out: dict[str, Any] = {}

    m = GSTIN_RE.search(text.translate(_DEV).upper())
    if m:
        out["gstin"] = m.group(0)

    # business type: exact known types first (longest match), then synonyms
    known = sorted(business_types(), key=len, reverse=True)
    for bt in known:
        if f" {bt} " in t or f" {bt}," in t or f" {bt}." in t:
            out["business_type"] = bt.capitalize() if bt.islower() else bt
            break
    if "business_type" not in out:
        for k in sorted(BUSINESS_SYNONYMS, key=len, reverse=True):
            if k in t:
                bt = BUSINESS_SYNONYMS[k]
                if re.search(r"\b(chain|branches|outlets)\b|शाखा|ब्रांच", t) and "chain" not in bt.lower():
                    bt = f"{bt} chain"
                out["business_type"] = bt
                break
    if "business_type" in out:
        out["business_type"] = out["business_type"][0].upper() + out["business_type"][1:]

    for alias, canon in CITY_ALIASES.items():
        if alias in t:
            out["city"] = canon
            break
    if "city" not in out:
        for c in cities():
            if f" {c.lower()}" in t:
                out["city"] = c
                break
    if "city" not in out and last_asked == "city" and len(text.split()) <= 3 and not re.search(r"\d", text):
        out["city"] = text.strip().strip(".").title()

    emp = re.search(r"(\d+)\s*(?:staff|employees|employee|people|persons|workers|members|log|लोग|कर्मचारी|स्टाफ|आदमी)", t)
    if emp:
        out["employees"] = int(emp.group(1))
    elif re.search(r"\b(alone|just me|only me|myself)\b|अकेले|मैं ही", t):
        out["employees"] = 1
    sites = re.search(r"(\d+)\s*(?:branches|branch|sites|site|locations|location|outlets|outlet|stores|shops|दुकानें|दुकान|शाखा\w*|ब्रांच)", t)
    if sites:
        out["sites"] = int(sites.group(1))
    if "employees" not in out and last_asked == "employees":
        nums = re.findall(r"\d+", t)
        if nums:
            out["employees"] = int(nums[0])
            if len(nums) > 1 and "sites" not in out:
                out["sites"] = int(nums[1])

    spend = re.search(r"(?:₹|rs\.?|inr|रु\.?)\s*([\d,]+)|([\d,]+)\s*(?:rupees|रुपये|रुपए|/-|per month|a month|/month|महीना|महीने)", t)
    if spend:
        out["monthly_telecom_spend"] = int((spend.group(1) or spend.group(2)).replace(",", ""))

    for kw, val in INTERNET_KEYWORDS:
        if kw in t:
            out["current_internet"] = val
            break

    needs = []
    for need, kws in NEED_KEYWORDS.items():
        if any(k in t for k in kws):
            needs.append(need)
    if "dedicated_line" in needs and "failover" in needs and "backup internet" not in t:
        needs.remove("failover")
    if "backup" in needs and ("backup internet" in t or "failover" in needs):
        needs.remove("backup")
    if needs:
        out["needs"] = needs
    if re.search(r"fibre (?:is )?not available|no fibre|fiber not available", t):
        out["fibre_feasible"] = False

    # Split on whitespace/punctuation (not \w: it drops Devanagari vowel signs such as ं and ी).
    words = set(re.split(r"[\s,.!?।]+", t)) - {""}
    if last_asked == "gstin" and "gstin" not in out and (words & {"no", "nope", "nahi", "nahin", "नहीं", "नही", "na"} or
                                                          any(w in t for w in ["don't have", "dont have", "not registered"])):
        out["has_gstin"] = False
    if any(w in t for w in DONE_WORDS):
        out["done"] = True
    if any(w in t for w in HUMAN_WORDS):
        out["human"] = True
    if re.search(r"cheap|budget|kam|सस्ता|कम ", t):
        out["cheaper"] = True
    return out


# ------------------------------------------------------------------ language of a message
_SCRIPTS = [("ऀ", "ॿ", "hi"), ("ঀ", "৿", "bn"), ("਀", "੿", "pa"), ("઀", "૿", "gu"),
            ("஀", "௿", "ta"), ("ఀ", "౿", "te"), ("ಀ", "೿", "kn"), ("ഀ", "ൿ", "ml")]
_HINGLISH = set("""hai hain mera meri mere hamara humara hamari hamare mujhe humein chahiye kitna kitne kitni nahi nahin
haan ji mein aur kya hoon hun hu karte karta karti wala wali wale dukaan dukan log accha acha theek thik abhi kaise
kyun lagta chalega mahina mahine paise bhi tha thi hoga hogi kuch sab""".split())
_ENGLISH = set("""i we my our you your is are am was the a an and or have has had need needs want wants please
yes no not it this that there do does how what which who for with to of in on at can could would will should staff
people employees shop store office clinic business branch branches location locations about current currently pay
monthly month internet use using""".split())


def detect_lang(text: str, current: str) -> str:
    """Language the owner just wrote in. An Indic script decides it outright; Latin text switches
    to English only when it clearly reads as English (Hinglish keeps the current language);
    numbers, names, a GSTIN or a one-word answer never switch it."""
    counts: dict[str, int] = {}
    for ch in text:
        for lo, hi, code in _SCRIPTS:
            if lo <= ch <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts:
        return max(counts, key=counts.get)
    words = re.findall(r"[a-z']+", text.lower())
    if any(w in _HINGLISH for w in words):
        return current
    en = sum(w in _ENGLISH for w in words)
    if en >= 2 or (en >= 1 and len(words) >= 3):
        return "en"
    return current
