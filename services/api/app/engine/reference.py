"""Business-type → segment and city → tier/state lookups, built from the leads data."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from functools import lru_cache

from ..data_store import leads
from .models import Segment

_SEGMENT_FROM_LABEL: dict[str, Segment] = {
    "Micro retail & services": "micro",
    "Professional offices": "prof",
    "Small multi-site businesses": "multi",
    "Small manufacturers": "mfg",
}

CITY_ALIASES = {
    "bangalore": "Bengaluru", "bengalooru": "Bengaluru", "bombay": "Mumbai", "new delhi": "Delhi",
    "madras": "Chennai", "calcutta": "Kolkata", "vizag": "Visakhapatnam", "mysore": "Mysuru",
    "baroda": "Vadodara", "poona": "Pune", "cochin": "Kochi",
    # common Hindi / regional spellings
    "दिल्ली": "Delhi", "मुंबई": "Mumbai", "पुणे": "Pune", "जयपुर": "Jaipur", "लखनऊ": "Lucknow",
    "पटना": "Patna", "इंदौर": "Indore", "भोपाल": "Bhopal", "नागपुर": "Nagpur", "नासिक": "Nashik",
    "बेंगलुरु": "Bengaluru", "चेन्नई": "Chennai", "कोलकाता": "Kolkata", "हैदराबाद": "Hyderabad",
    "अहमदाबाद": "Ahmedabad", "सूरत": "Surat", "लुधियाना": "Ludhiana",
    "कोच्चि": "Kochi", "कोचीन": "Kochi", "कोयंबटूर": "Coimbatore", "कोयम्बटूर": "Coimbatore", "मैसूर": "Mysuru",
    "मैसूरु": "Mysuru", "वडोदरा": "Vadodara", "बड़ौदा": "Vadodara", "विशाखापत्तनम": "Visakhapatnam", "विज़ाग": "Visakhapatnam",
    "बेंगलुरू": "Bengaluru", "बैंगलोर": "Bengaluru", "नई दिल्ली": "Delhi", "बंबई": "Mumbai",
}

# Tier-1 metros not in the data still resolve sensibly.
EXTRA_TIER1 = {"Gurugram": "Haryana", "Noida": "Uttar Pradesh", "Thane": "Maharashtra", "Navi Mumbai": "Maharashtra"}

_KEYWORDS: list[tuple[str, Segment]] = [
    (r"\bchain\b|\bbranches\b|\boutlets\b|\bgroup\b|\bfranchise", "multi"),
    (r"\bunit\b|factory|manufactur|workshop|press|mill|plant|fabricat|moulding|processing", "mfg"),
    (r"clinic|hospital|dental|doctor|lab\b|diagnostic|physio|\bca\b|chartered|account|law|legal|advocate|"
     r"coaching|tuition|school|academy|architect|consult|agency|insurance|real estate|travel|studio|office", "prof"),
]


@lru_cache
def business_types() -> dict[str, Segment]:
    votes: dict[str, Counter] = defaultdict(Counter)
    for r in leads():
        votes[r["business_type"].strip().lower()][_SEGMENT_FROM_LABEL[r["segment"]]] += 1
    return {bt: c.most_common(1)[0][0] for bt, c in votes.items()}


def segment_for(business_type: str, sites: int = 1, employees: int = 1) -> Segment:
    bt = (business_type or "").strip().lower()
    seg = business_types().get(bt)
    if seg is None:
        for pattern, s in _KEYWORDS:
            if re.search(pattern, bt):
                seg = s
                break
    if seg is None:
        seg = "micro"
    # Size overrides: three or more sites is a multi-site business whatever the trade.
    if sites >= 3 and seg != "mfg":
        seg = "multi"
    return seg


@lru_cache
def cities() -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for r in leads():
        out[r["city"]] = (int(r["city_tier"]), r["state"])
    for c, st in EXTRA_TIER1.items():
        out.setdefault(c, (1, st))
    return out


def resolve_city(name: str | None) -> dict | None:
    """Returns {city, tier, state, known}. Unknown cities default to tier 2, which only
    hides tier-1-only products (P03), so we never promise something we cannot install."""
    if not name:
        return None
    raw = name.strip()
    canon = CITY_ALIASES.get(raw.lower(), CITY_ALIASES.get(raw, raw))
    table = cities()
    for c, (tier, state) in table.items():
        if c.lower() == canon.lower():
            return {"city": c, "tier": tier, "state": state, "known": True}
    return {"city": raw.title(), "tier": 2, "state": None, "known": False}
