"""Back-office console for sales and channel partners (demo auth: X-Console-Role header).

- Leads the digital advisor did not close, ranked by propensity x expected value, routed to
  field sales / channel partner / inside sales
- Re-engagement list from Q2 leads that dropped before a needs assessment
- KYC review queue with audit-logged decisions
- Assisted mode: a partner continues the owner's own journey after the owner shares a code
"""
from __future__ import annotations

import random
import re
from collections import Counter
from statistics import median

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .. import store
from ..advisor import profile_slots
from ..advisor.session import AdvisorSession
from ..data_store import leads
from ..engine.models import SEGMENT_LABELS
from ..ids import gstin as gstin_ids
from ..kyc.consent import audit
from ..kyc.models import KycCase
from ..orders.models import Order
from . import propensity

router = APIRouter(prefix="/console", tags=["console"])
ROLES = {"sales", "partner"}
SEG_VALUE = {}  # median monthly bundle value per segment, from Q2 activations


_GSTIN_ANY = re.compile(r"\b\d{2}[A-Za-z]{5}\d{4}[A-Za-z][0-9A-Za-z][Zz][0-9A-Za-z]\b")
_LONG_DIGITS = re.compile(r"\b\d{8,}\b")  # phone, Aadhaar, account numbers
_UPI = re.compile(r"\b[\w.\-]{2,}@[a-zA-Z]{2,}\b")


def mask_free_text(text: str) -> str:
    """Owners type identifiers into chat; never show them raw to sales or partners."""
    text = _GSTIN_ANY.sub(lambda m: gstin_ids.mask(m.group(0)), text)
    text = _LONG_DIGITS.sub(lambda m: "•" * (len(m.group(0)) - 4) + m.group(0)[-4:], text)
    return _UPI.sub("•••@•••", text)


def _role(x_console_role: str | None) -> str:
    if x_console_role not in ROLES:
        raise HTTPException(401, "Sign in to the console (demo: send X-Console-Role: sales or partner)")
    return x_console_role


def _seg_value(seg_label: str) -> float:
    if not SEG_VALUE:
        by = {}
        for r in leads():
            if r["outcome"] == "Activated":
                by.setdefault(r["segment"], []).append(float(r["monthly_bundle_value_inr"]))
        SEG_VALUE.update({k: median(v) for k, v in by.items()})
    return SEG_VALUE.get(seg_label, 2500.0)


def _route(seg: str, value: float, tier: int | None) -> str:
    if seg in ("mfg", "multi") or value >= 25000:
        return "field_sales"
    if seg == "micro" and (tier or 2) == 2:
        return "channel_partner"
    return "inside_sales"


def _session_lead(s: AdvisorSession) -> dict:
    p = s.profile
    seg = p.get("segment") or "micro"
    rec_value = None
    if s.recommendation:
        t = next((t for t in s.recommendation["tiers"] if t["tier"] == "recommended"), None)
        rec_value = t["quote"]["monthly_total"] if t else None
    row = {"lead_source": "WhatsApp campaign" if s.channel == "whatsapp" else "Website form",
           "segment": SEGMENT_LABELS.get(seg, seg), "city_tier": p.get("city_tier") or 2,
           "has_gstin": "Y" if p.get("gstin") else "N", "gstin": p.get("gstin"), "has_udyam": "N",
           "current_internet": p.get("current_internet"), "annual_turnover_band": None, "contact_role": "Owner",
           "employee_count": p.get("employees") or 1, "num_sites": p.get("sites") or 1,
           "monthly_telecom_spend_inr": p.get("monthly_telecom_spend") or 0, "products_of_interest": ";".join(p.get("needs", []))}
    sc = propensity.score(row)
    value = rec_value or _seg_value(SEGMENT_LABELS.get(seg, ""))
    last_user = mask_free_text(next((t.text for t in reversed(s.transcript) if t.role == "user"), ""))
    reason = (s.handoff or {}).get("reason") or ("Saw a plan but did not accept" if s.recommendation else "Left during discovery")
    return {"session_id": s.id, "created_at": s.created_at, "status": s.status, "channel": s.channel,
            "business": p.get("trade_name") or p.get("business_type") or "Unknown business", "city": p.get("city"),
            "segment": seg, "profile": profile_slots.public_view(p), "monthly_value": value, "score": sc["score"],
            "drivers": sc["drivers"], "priority": round(sc["score"] * value, 1), "reason": reason,
            "last_message": last_user[:140], "route_to": _route(seg, value, p.get("city_tier")),
            "assisted_by": (s.profile.get("_assist") or {}).get("partner")}


@router.get("/summary")
def summary(x_console_role: str | None = Header(None)) -> dict:
    _role(x_console_role)
    sessions = [AdvisorSession(**d) for d in store.all("advisor_sessions")]
    orders = [Order(**d) for d in store.all("orders")]
    cases = [KycCase(**d) for d in store.all("kyc_cases")]
    states = Counter(o.state for o in orders)
    reached = lambda *ss: sum(states[s] for s in ss)  # noqa: E731
    funnel = [
        {"stage": "Conversations started", "count": len(sessions)},
        {"stage": "Plan recommended", "count": sum(1 for s in sessions if s.recommendation)},
        {"stage": "Quote accepted", "count": len(orders)},
        {"stage": "KYC verified", "count": reached("KYCVerified", "MandateSet", "InstallScheduled", "Installed", "Activated")},
        {"stage": "Activated", "count": states["Activated"]},
    ]
    q2 = Counter(r["stage_reached"] for r in leads())
    order_ = ["Lead", "Contacted", "Needs assessed", "Quote accepted", "KYC complete", "Activated"]
    cum, baseline = 0, []
    for st in reversed(order_):
        cum += q2[st]
        baseline.insert(0, {"stage": st, "count": cum})
    return {
        "digital_funnel": funnel,
        "q2_baseline_funnel": baseline,
        "kyc_verdicts": dict(Counter(c.verdict for c in cases)),
        "kyc_review_queue": sum(1 for c in cases if c.verdict == "review"),
        "sla_breaches": sum(1 for o in orders if o.sla_breach and o.state != "Activated"),
        "handoffs": sum(1 for s in sessions if s.handoff),
        "model": propensity.evaluation(),
    }


@router.get("/leads")
def open_leads(x_console_role: str | None = Header(None)) -> list[dict]:
    role = _role(x_console_role)
    out = []
    for d in store.all("advisor_sessions"):
        s = AdvisorSession(**d)
        if s.status == "converted" or not s.profile.get("business_type"):
            continue
        lead = _session_lead(s)
        if role == "partner" and lead["route_to"] != "channel_partner":
            continue
        out.append(lead)
    return sorted(out, key=lambda x: -x["priority"])


@router.get("/reengage")
def reengage(limit: int = 25, x_console_role: str | None = Header(None)) -> dict:
    """Q2 leads lost before a needs assessment (unreachable, no time for a visit...), best first."""
    _role(x_console_role)
    early = {"Lead", "Contacted"}
    rows = [r for r in leads() if r["outcome"] == "Dropped" and r["stage_reached"] in early]
    m = propensity.model()
    ps = m.predict(rows)
    ranked = sorted(zip(rows, ps), key=lambda t: -t[1])[: max(1, min(limit, 200))]
    reasons = Counter(r["drop_reason"] for r in rows)
    return {
        "pool": len(rows), "reasons": dict(reasons.most_common()),
        "leads": [{"lead_id": r["lead_id"], "business": r["business_name"], "segment": r["segment"], "city": r["city"],
                   "language": r["preferred_language"], "source": r["lead_source"], "drop_reason": r["drop_reason"],
                   "score": round(float(p), 4), "drivers": m.explain(r),
                   "suggested_channel": "WhatsApp link to self-serve advisor" if r["drop_reason"] in (
                       "Owner had no time for a visit", "Visit not scheduled by sales", "Unreachable after 3 attempts")
                   else "Call from inside sales"}
                  for r, p in ranked],
    }


@router.get("/model")
def model_card(x_console_role: str | None = Header(None)) -> dict:
    _role(x_console_role)
    return {"evaluation": propensity.evaluation(), "coefficients": propensity.coefficients(),
            "features": propensity.CATEGORICAL + propensity.NUMERIC,
            "excluded": "stage dates, drop reasons, outcomes, bundle values (all observed after the lead arrives)"}


# ------------------------------------------------------------------ KYC reviews
class Decision(BaseModel):
    decision: str  # approve | reject
    note: str


@router.get("/kyc-reviews")
def kyc_reviews(x_console_role: str | None = Header(None)) -> list[dict]:
    _role(x_console_role)
    out = []
    for d in store.all("kyc_cases"):
        c = KycCase(**d)
        if c.verdict == "review":
            out.append({"id": c.id, "order_id": c.order_id, "verified_at": c.verified_at,
                        "business": next((x.fields.get("trade_name") or x.fields.get("enterprise_name") for x in c.documents.values()
                                          if x.fields.get("trade_name") or x.fields.get("enterprise_name")), None),
                        "issues": [ch.model_dump() for ch in c.checks if ch.status in ("review", "block", "action")]})
    return out


@router.post("/kyc-reviews/{cid}")
def decide(cid: str, d: Decision, x_console_role: str | None = Header(None)) -> dict:
    role = _role(x_console_role)
    if role != "sales":
        raise HTTPException(403, "Only Accel staff can decide KYC reviews")
    c = KycCase.load(cid)
    if c is None or c.verdict != "review":
        raise HTTPException(404, "No pending review")
    if d.decision not in ("approve", "reject") or len(d.note.strip()) < 5:
        raise HTTPException(422, "Choose approve or reject and write a reason")
    c.verdict = "approved" if d.decision == "approve" else "blocked"
    c.reviewer_note = d.note.strip()
    from ..kyc import pipeline
    pipeline.purge_raw(c)
    c.save()
    audit(f"kyc.review_{d.decision}", c.id, {"note": c.reviewer_note}, actor=role)
    return {"id": c.id, "verdict": c.verdict}


# ------------------------------------------------------------------ assisted mode
class AssistConfirm(BaseModel):
    code: str
    partner: str = "Partner"


@router.post("/leads/{sid}/assist")
def assist_request(sid: str, x_console_role: str | None = Header(None)) -> dict:
    role = _role(x_console_role)
    s = AdvisorSession.load(sid)
    if s is None:
        raise HTTPException(404, "Lead not found")
    code = f"{random.randint(0, 9999):04d}"
    s.profile["_assist"] = {"code": code, "by_role": role, "granted": False}
    s.save()
    msg = {"id": f"assist-{sid}", "order_id": f"session:{sid}", "event": "AssistRequest", "channel": "whatsapp",
           "text": f"An Accel Business {'partner' if role == 'partner' else 'advisor'} wants to help you finish your plan. "
                   f"Share code {code} with them only if you agree.", "at": store.now(), "seq": 0, "delivery": "outbox"}
    store.put("notifications", msg["id"], msg)
    audit("assist.requested", sid, {"role": role}, actor=role)
    return {"sent": True, "demo_code": code}


@router.post("/leads/{sid}/assist/confirm")
def assist_confirm(sid: str, req: AssistConfirm, x_console_role: str | None = Header(None)) -> dict:
    role = _role(x_console_role)
    s = AdvisorSession.load(sid)
    a = (s.profile.get("_assist") if s else None) or {}
    if not s or a.get("code") != req.code:
        raise HTTPException(422, "Code does not match")
    a.update({"granted": True, "partner": req.partner, "at": store.now()})
    s.profile["_assist"] = a
    s.channel = "assisted"
    s.save()
    audit("assist.granted", sid, {"partner": req.partner}, actor=role)
    return {"session_id": sid, "continue_url": f"/#/chat/{sid}"}
