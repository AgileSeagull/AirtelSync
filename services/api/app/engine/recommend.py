"""Bundle recommendation: candidate selection → hard eligibility → dependencies →
quantities → three tiers. Pure functions; no LLM involved."""
from __future__ import annotations

import math

from ..data_store import catalogue
from .eligibility import is_eligible, product_violations, validate_bundle
from .models import (NEEDS, SEGMENT_LABELS, BundleTier, LineItem, Profile, Recommendation,
                     RecommendedItem, Violation)
from .pricing import enrich

# Need tag → product that serves it (connectivity and mobile lines are handled separately).
NEED_PRODUCT = {
    "billing_pos": "P19", "whatsapp": "P15", "sms": "P14", "website": "P18", "cctv": "P23",
    "email_office": "P16", "backup": "P17", "device_security": "P20", "firewall": "P21",
    "guest_wifi": "P22", "failover": "P09", "telephony": "P12", "toll_free": "P13",
    "static_ip": "P11", "machine_monitoring": "P24", "fleet_tracking": "P25", "multi_site_network": "P10",
}

# Add-ons each segment most often bought (ordered by frequency in Q2 activations).
SEGMENT_ADDONS = {
    "micro": ["P19", "P22", "P23", "P15", "P18"],
    "prof": ["P16", "P20", "P17", "P12", "P11", "P14"],
    "multi": ["P09", "P19", "P23", "P10", "P13", "P22", "P15"],
    "mfg": ["P16", "P20", "P21", "P23", "P24", "P11", "P25"],
}
PROTECTION = ["P09", "P20", "P17", "P21"]
WIRED = {"P01", "P02", "P03", "P05", "P06"}
CONNECTIVITY = WIRED | {"P04"}

REASON_TEXT = {
    "CONN_BASE": "Fast, unlimited business internet for your premises",
    "CONN_UPGRADE_HOTSPOT": "Replaces the mobile hotspot with a stable fixed line for UPI and billing",
    "CONN_STAFF_SIZE": "Sized for the number of people using the internet",
    "CONN_HIGH_SPEED": "You need very high bandwidth",
    "CONN_DEDICATED": "Dedicated 1:1 line with an uptime SLA, as factories need",
    "CONN_FIBRE_NOT_FEASIBLE": "Fibre is not available at your address; 5G AirFiber installs in 2 days",
    "CONN_PER_SITE": "One line at each branch",
    "LINES_STAFF": "Business numbers for you and your staff",
    "PROTECT": "Keeps your business online and your data safe",
}


def _qty(profile: Profile, pid: str, desk_users: int) -> int:
    seg, emp, sites = profile.segment, profile.employees, profile.sites
    p = catalogue()[pid]
    if pid in ("P07", "P08"):
        if profile.mobile_users:
            return profile.mobile_users
        if seg == "micro":
            return min(2, emp)
        if seg == "prof":
            return min(max(1, math.ceil(emp / 6)), 4)
        if seg == "mfg":
            return min(max(3, math.ceil(emp / 25)), 6)
        return min(max(3, math.ceil(sites / 2)), 6)
    if pid == "P16":
        return desk_users
    if pid == "P20":
        return desk_users if seg != "mfg" else max(10, desk_users)
    if pid == "P23":
        if profile.cameras:
            return profile.cameras
        return {"micro": 1, "multi": 2 * sites, "mfg": 5}.get(seg, 2)
    if pid == "P19":
        return profile.counters or sites
    if pid == "P24":
        return profile.machines or 8
    if pid == "P25":
        return profile.vehicles or 3
    if pid == "P12":
        return max(2, min(4, math.ceil(emp / 5)))
    if p.unit == "per site":
        return sites
    return 1


def _desk_users(profile: Profile) -> int:
    if profile.desk_users:
        return profile.desk_users
    emp = profile.employees
    return {
        "prof": max(2, round(emp * 0.6)),
        "mfg": max(5, math.ceil(emp * 0.1)),
        "multi": max(3, profile.sites),
    }.get(profile.segment, min(emp, 2))


def choose_connectivity(profile: Profile, needs: set[str]) -> tuple[str, list[str], list[str]]:
    """Returns (product_id, reason codes, notes)."""
    notes: list[str] = []
    seg, emp = profile.segment, profile.employees
    if profile.fibre_feasible is False:
        return "P04", ["CONN_FIBRE_NOT_FEASIBLE"], notes

    wants_dedicated = "dedicated_line" in needs or (seg == "mfg" and emp >= 10)
    if wants_dedicated:
        prefs = (["P06", "P05"] if emp >= 25 and ("high_speed" in needs or emp >= 100) else ["P05"])
        for pid in prefs:
            if is_eligible(profile, pid):
                return pid, ["CONN_DEDICATED"], notes
        if "dedicated_line" in needs:
            v = product_violations(profile, catalogue()["P05"])
            notes.append("A leased line is not possible yet (" + "; ".join(x.message for x in v) +
                         "). We recommend business fibre instead.")

    high = "high_speed" in needs
    if seg == "multi":
        if high and is_eligible(profile, "P03"):
            return "P03", ["CONN_PER_SITE", "CONN_HIGH_SPEED"], notes
        return "P02", ["CONN_PER_SITE"], notes
    if seg in ("prof", "mfg"):
        if (high or emp >= 15) and is_eligible(profile, "P03"):
            return "P03", ["CONN_STAFF_SIZE"] + (["CONN_HIGH_SPEED"] if high else []), notes
        if emp >= 5 or high or seg == "mfg":
            return "P02", ["CONN_STAFF_SIZE"], notes
        return "P01", ["CONN_BASE"], notes
    reasons = ["CONN_BASE"]
    if (profile.current_internet or "").lower().startswith("mobile hotspot"):
        reasons.append("CONN_UPGRADE_HOTSPOT")
    return "P01", reasons, notes


def _why(codes: list[str], segment: str) -> str:
    parts = []
    cat = catalogue()
    for c in codes:
        if c in REASON_TEXT:
            parts.append(REASON_TEXT[c])
        elif c.startswith("NEED_"):
            tag = c[5:].lower()
            parts.append("You asked for: " + NEEDS.get(tag, tag).lower())
        elif c.startswith("SEG_"):
            parts.append(f"Popular with {SEGMENT_LABELS[segment].lower()}")
        elif c.startswith("DEP_FOR_"):
            pid = c[8:]
            parts.append(f"Required for {cat[pid].name}" if pid in cat else "Required by another item")
    return "; ".join(parts)


def recommend(profile: Profile) -> Recommendation:
    profile = enrich(profile)
    seg = profile.segment
    cat = catalogue()
    needs = {n for n in profile.needs if n in NEEDS}
    desk = _desk_users(profile)
    notes: list[str] = []
    excluded: dict[str, Violation] = {}

    def make(pid: str, codes: list[str], optional: bool = True) -> RecommendedItem:
        p = cat[pid]
        return RecommendedItem(product_id=pid, name=p.name, category=p.category, qty=_qty(profile, pid, desk),
                               unit=p.unit, reasons=codes, why=_why(codes, seg), optional=optional)

    def try_add(items: list[RecommendedItem], pid: str, codes: list[str], record_exclusion: bool) -> bool:
        if any(i.product_id == pid for i in items):
            return False
        v = product_violations(profile, cat[pid])
        if v:
            if record_exclusion:
                excluded.setdefault(pid, v[0])
            return False
        items.append(make(pid, codes))
        return True

    # --- Essential: connectivity + mobile lines + everything the owner explicitly asked for.
    essential: list[RecommendedItem] = []
    mobile_only = bool(needs) and needs <= {"mobile_lines"}
    if not mobile_only:
        conn, codes, conn_notes = choose_connectivity(profile, needs)
        notes += conn_notes
        essential.append(make(conn, codes, optional=False))
    line_pid = "P07" if seg == "micro" else "P08"
    if mobile_only or "mobile_lines" in needs or seg != "micro" or (profile.current_internet or "").lower() == "mobile hotspot":
        essential.append(make(line_pid, ["LINES_STAFF"] + (["NEED_MOBILE_LINES"] if "mobile_lines" in needs else []),
                              optional=not mobile_only))
    for need in sorted(needs):
        pid = NEED_PRODUCT.get(need)
        if pid:
            try_add(essential, pid, [f"NEED_{need.upper()}"], record_exclusion=True)

    # --- Recommended: add the two most popular eligible add-ons for the segment.
    recommended = [i.model_copy() for i in essential]
    added = 0
    for pid in SEGMENT_ADDONS[seg]:
        if added >= 2:
            break
        if try_add(recommended, pid, [f"SEG_{seg.upper()}"], record_exclusion=False):
            added += 1

    # --- Complete: two more segment add-ons plus protection.
    complete = [i.model_copy() for i in recommended]
    added = 0
    for pid in SEGMENT_ADDONS[seg]:
        if added >= 2:
            break
        if try_add(complete, pid, [f"SEG_{seg.upper()}"], record_exclusion=False):
            added += 1
    has_wired = any(i.product_id in WIRED for i in complete)
    for pid in PROTECTION:
        if pid == "P09" and not has_wired:
            continue
        if pid == "P21" and seg == "micro":
            continue
        if pid == "P17" and seg in ("micro", "multi"):
            continue
        try_add(complete, pid, ["PROTECT"], record_exclusion=False)

    tiers = []
    for name, title, items in (("essential", "Essential", essential), ("recommended", "Recommended", recommended),
                               ("complete", "Complete", complete)):
        items = _resolve_dependencies(profile, items)
        tiers.append(BundleTier(tier=name, title=title, items=items))

    if not profile.gstin_active:
        locked = [cat[pid].name for pid, v in excluded.items() if v.rule == "gstin"]
        if profile.gstin_status in ("Cancelled", "Suspended"):
            notes.append(f"Your GSTIN is {profile.gstin_status.lower()}, so products that need GST registration are not offered.")
        elif locked:
            notes.append("Register for GST to unlock: " + ", ".join(locked) + ".")
    return Recommendation(profile=profile, segment=seg, tiers=tiers, excluded=list(excluded.values()), notes=notes)


def _resolve_dependencies(profile: Profile, items: list[RecommendedItem]) -> list[RecommendedItem]:
    """Make sure every item's requires_one_of is satisfied: add the cheapest eligible
    dependency, or drop the item if nothing eligible can satisfy it."""
    cat = catalogue()
    items = list(items)
    for item in list(items):
        p = cat[item.product_id]
        if not p.requires_one_of:
            continue
        present = {i.product_id for i in items}
        if present.intersection(p.requires_one_of):
            continue
        options = sorted((d for d in p.requires_one_of if is_eligible(profile, d)), key=lambda d: cat[d].price_min)
        if not options:
            items.remove(item)
            continue
        dep = options[0]
        dep_item = RecommendedItem(product_id=dep, name=cat[dep].name, category=cat[dep].category,
                                   qty=_qty(profile, dep, _desk_users(profile)), unit=cat[dep].unit,
                                   reasons=[f"DEP_FOR_{p.id}"], why=_why([f"DEP_FOR_{p.id}"], profile.segment),
                                   optional=False)
        items.insert(0, dep_item)
    # Final guard: the engine must never emit a bundle that breaks a rule.
    assert not validate_bundle(profile, [LineItem(product_id=i.product_id, qty=i.qty) for i in items]), items
    return items
