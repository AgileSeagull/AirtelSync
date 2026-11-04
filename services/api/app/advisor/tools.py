"""Advisor tools. Both the LLM advisor and the scripted advisor act only through these,
so every product, price and eligibility statement comes from the deterministic engine."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .. import store
from ..data_store import catalogue
from ..engine.eligibility import product_violations
from ..engine.models import NEEDS, LineItem
from ..engine.pricing import quote
from ..engine.recommend import NEED_PRODUCT, recommend
from ..ids import gstin as gstin_ids
from ..mocks.registry import lookup_gstin
from . import profile_slots
from .session import AdvisorSession

# ---------------------------------------------------------------- schemas (Claude tool definitions)
TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "lookup_gstin",
        "description": "Look up a GSTIN in the GST registry. Use it as soon as the owner shares a GSTIN. "
                       "Fills legal name, state, city and registration status into the profile automatically. "
                       "Returns an error if the format or checksum is wrong (ask the owner to re-check it).",
        "input_schema": {"type": "object", "properties": {"gstin": {"type": "string", "description": "15-character GSTIN"}},
                         "required": ["gstin"], "additionalProperties": False},
    },
    {
        "name": "update_profile",
        "description": "Record facts the owner told you about their business. Call it every time you learn something new, "
                       "before replying. Only include fields you actually learned. Returns the full profile and which "
                       "required fields are still missing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "business_type": {"type": "string", "description": "Kind of business in plain English, e.g. 'Dental clinic', 'Kirana store', 'Restaurant chain', 'Textile unit'"},
                "city": {"type": "string", "description": "City in English, e.g. 'Pune'"},
                "employees": {"type": "integer", "description": "People working in the business including the owner"},
                "sites": {"type": "integer", "description": "Number of shops/branches/locations"},
                "has_gstin": {"type": "boolean", "description": "false if the owner says they have no GST registration"},
                "current_internet": {"type": "string", "enum": ["Mobile hotspot", "Home broadband", "Business broadband", "Leased line", "Mixed per site", "None"]},
                "monthly_telecom_spend": {"type": "integer", "description": "What they pay today per month for internet + phones, in rupees"},
                "needs": {"type": "array", "items": {"type": "string", "enum": list(NEEDS)},
                          "description": "Needs to ADD. " + "; ".join(f"{k}: {v}" for k, v in NEEDS.items())},
                "remove_needs": {"type": "array", "items": {"type": "string", "enum": list(NEEDS)}, "description": "Needs the owner no longer wants"},
                "mobile_users": {"type": "integer", "description": "How many business mobile numbers they want"},
                "desk_users": {"type": "integer", "description": "How many people need email/computers"},
                "cameras": {"type": "integer"}, "counters": {"type": "integer", "description": "Billing counters"},
                "machines": {"type": "integer"}, "vehicles": {"type": "integer"},
                "fibre_feasible": {"type": "boolean", "description": "false only if the owner says fibre is not available at their address"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "recommend_bundle",
        "description": "Get eligible bundles for the current profile: three tiers (essential, recommended, complete) with "
                       "items, reasons, exact monthly price incl. GST, setup fee and activation time. Requires business_type, "
                       "city and employees in the profile. The app shows the tiers as cards automatically.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "check_product",
        "description": "Check whether this business can buy a specific product or need (e.g. when the owner asks "
                       "'can I get WhatsApp?' or 'I want a leased line'). Returns eligibility, the rule that blocks it, and price range.",
        "input_schema": {"type": "object", "properties": {
            "product_id": {"type": "string", "description": "Catalogue id P01-P25, if known"},
            "need": {"type": "string", "enum": list(NEEDS), "description": "Or the need, if the product id is unknown"}},
            "additionalProperties": False},
    },
    {
        "name": "handoff_to_human",
        "description": "Pass the conversation to an Accel Business expert who will call back. Use when the owner asks for a "
                       "person, needs something the catalogue cannot do, wants a site survey, or the bundle is above Rs 25,000/month.",
        "input_schema": {"type": "object", "properties": {
            "reason": {"type": "string", "description": "One line on why, for the sales team"},
            "preferred_time": {"type": "string", "description": "When the owner prefers a call, if they said"}},
            "required": ["reason"], "additionalProperties": False},
    },
]


# ---------------------------------------------------------------- executors
class ToolError(Exception):
    pass


def run_tool(session: AdvisorSession, name: str, args: dict[str, Any]) -> dict[str, Any]:
    fn = {"lookup_gstin": t_lookup_gstin, "update_profile": t_update_profile, "recommend_bundle": t_recommend,
          "check_product": t_check_product, "handoff_to_human": t_handoff}.get(name)
    if fn is None:
        raise ToolError(f"Unknown tool {name}")
    return fn(session, args or {})


def t_lookup_gstin(session: AdvisorSession, args: dict) -> dict:
    g = gstin_ids.normalise(str(args.get("gstin", "")))
    try:
        rec = lookup_gstin(g)
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"errors": [str(e.detail)]}
        raise ToolError("; ".join(detail.get("errors", ["lookup failed"])))
    # The registry city only fills a gap: the owner's stated city is where we install.
    stated_city = session.profile.get("city")
    p = dict(session.profile)
    if not stated_city and rec.get("city"):
        p, _ = profile_slots.merge(p, {"city": rec["city"]})
    p.update({"has_gstin": True, "gstin": rec["gstin"], "gstin_status": rec["status"],
              "trade_name": rec["trade_name"], "constitution": rec["constitution"]})
    if not stated_city:
        p["state"] = rec["state"]
    session.profile = p
    out = {"gstin": gstin_ids.mask(rec["gstin"]), "trade_name": rec["trade_name"], "constitution": rec["constitution"],
           "city": rec.get("city"), "state": rec["state"], "status": rec["status"],
           "missing": profile_slots.missing(p)}
    if stated_city and rec.get("city") and rec["city"].lower() != stated_city.lower():
        out["note"] = (f"The GST registration address is in {rec['city']}, but the owner said the business is in "
                       f"{stated_city}. Keep {stated_city} for installation; KYC will ask for an address proof there.")
    if rec["status"] != "Active":
        out["warning"] = (f"This GSTIN is {rec['status'].upper()} in the GST registry. Products that need GST "
                          "registration cannot be offered, and KYC will not pass with it. Tell the owner politely.")
    return out


def t_update_profile(session: AdvisorSession, args: dict) -> dict:
    p, errors = profile_slots.merge(session.profile, args)
    session.profile = p
    out = {"profile": profile_slots.public_view(p), "missing": profile_slots.missing(p)}
    if errors:
        out["ignored"] = errors
    return out


def _quote_summary(profile, items) -> dict:
    q = quote(profile, [LineItem(product_id=i.product_id, qty=i.qty) for i in items], "12")
    return q.model_dump()


def t_recommend(session: AdvisorSession, args: dict) -> dict:
    miss = profile_slots.missing(session.profile)
    if miss:
        raise ToolError("Cannot recommend yet. Missing: " + ", ".join(miss))
    rec = recommend(profile_slots.to_profile(session.profile))
    tiers = []
    for t in rec.tiers:
        q = _quote_summary(rec.profile, t.items)
        tiers.append({"tier": t.tier, "items": [i.model_dump() for i in t.items], "quote": q})
    session.recommendation = {"segment": rec.segment, "tiers": tiers, "excluded": [e.model_dump() for e in rec.excluded],
                              "notes": rec.notes, "profile": rec.profile.model_dump()}
    session.status = "recommended"
    # Compact view for the model: enough to explain, nothing it could misquote.
    compact = []
    for t in tiers:
        q = t["quote"]
        compact.append({
            "tier": t["tier"],
            "items": [{"id": i["product_id"], "name": i["name"], "qty": i["qty"], "why": i["why"]} for i in t["items"]],
            "monthly_total_incl_gst": q["monthly_total"], "setup_total_incl_gst": q["setup_total"],
            "ready_in_days": q["earliest_activation_days"],
            "difference_vs_current_spend": q["monthly_difference"],
            "notes": q["notes"],
        })
    return {"segment": rec.segment, "tiers": compact,
            "not_available": [{"id": e.product_id, "name": catalogue()[e.product_id].name, "why": e.message} for e in rec.excluded],
            "notes": rec.notes, "contract_assumed_months": 12}


def t_check_product(session: AdvisorSession, args: dict) -> dict:
    pid = args.get("product_id")
    if not pid and args.get("need"):
        pid = NEED_PRODUCT.get(args["need"])
        if pid is None:
            return {"need": args["need"], "answer": "This need is served by the internet line or mobile plan in the bundle."}
    p = catalogue().get(str(pid or "").upper())
    if p is None:
        raise ToolError("Unknown product. Valid ids are P01-P25.")
    prof = profile_slots.to_profile(session.profile)
    from ..engine.pricing import enrich
    prof = enrich(prof)
    v = product_violations(prof, p)
    out = {"id": p.id, "name": p.name, "description": p.description, "eligible": not v,
           "blocked_by": [x.message for x in v], "price_range_per_month_ex_gst": [p.price_min, p.price_max],
           "unit": p.unit, "setup_fee_ex_gst": p.setup_fee, "min_contract_months": p.min_contract_months,
           "install_days": p.install_days}
    if p.requires_one_of:
        out["needs_one_of"] = [catalogue()[d].name for d in p.requires_one_of]
    return out


def t_handoff(session: AdvisorSession, args: dict) -> dict:
    session.handoff = {"reason": str(args.get("reason", ""))[:300], "preferred_time": args.get("preferred_time"),
                       "at": store.now()}
    session.status = "handoff"
    return {"ok": True, "message": "An Accel Business expert will call the owner within 4 working hours."}
