"""Quote builder and checkout for an advisor session.

The profile always comes from the server-side session (never from the client), so the
owner can toggle items and quantities but cannot talk the engine into an ineligible sale."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..advisor import profile_slots
from ..advisor.session import AdvisorSession
from ..data_store import catalogue
from ..engine.eligibility import is_eligible, product_violations
from ..engine.models import ContractChoice, LineItem
from ..engine.pricing import enrich, quote
from ..engine.recommend import _desk_users, _qty
from ..orders.models import Order, OrderEvent

router = APIRouter(prefix="/checkout", tags=["checkout"])


class Selection(BaseModel):
    items: list[LineItem] = Field(default_factory=list)
    contract: ContractChoice = "12"


def _session(sid: str) -> AdvisorSession:
    s = AdvisorSession.load(sid)
    if s is None:
        raise HTTPException(404, "Session not found")
    if profile_slots.missing(s.profile):
        raise HTTPException(409, "Finish the conversation with the advisor first")
    return s


def _profile(s: AdvisorSession):
    return enrich(profile_slots.to_profile(s.profile))


def _fixes(profile, items: list[LineItem], violations) -> list[dict]:
    cat = catalogue()
    ids = {i.product_id for i in items}
    fixes = []
    for v in violations:
        if v.rule == "dependency":
            p = cat[v.product_id]
            options = sorted((d for d in p.requires_one_of if is_eligible(profile, d) and d not in ids),
                             key=lambda d: cat[d].price_min)
            if options:
                d = options[0]
                fixes.append({"violation": v.model_dump(), "action": "add", "product_id": d, "name": cat[d].name,
                              "qty": _qty(profile, d, _desk_users(profile))})
                continue
        fixes.append({"violation": v.model_dump(), "action": "remove", "product_id": v.product_id,
                      "name": cat[v.product_id].name if v.product_id in cat else v.product_id})
    return fixes


def _addons(profile, items: list[LineItem]) -> list[dict]:
    ids = {i.product_id for i in items}
    out = []
    for p in catalogue().values():
        if p.id in ids:
            continue
        v = product_violations(profile, p)
        out.append({"product_id": p.id, "name": p.name, "category": p.category, "description": p.description,
                    "unit": p.unit, "price_from": p.price_min, "price_to": p.price_max, "setup_fee": p.setup_fee,
                    "eligible": not v, "locked_reason": v[0].message if v else None,
                    "locked_rule": v[0].rule if v else None,
                    "default_qty": _qty(profile, p.id, _desk_users(profile)),
                    "needs_one_of": [catalogue()[d].name for d in p.requires_one_of]})
    out.sort(key=lambda a: (not a["eligible"], a["category"], a["price_from"]))
    return out


@router.post("/{sid}/quote")
def build_quote(sid: str, sel: Selection) -> dict:
    s = _session(sid)
    prof = _profile(s)
    if not sel.items:
        return {"quote": None, "fixes": [], "addons": _addons(prof, [])}
    q = quote(prof, sel.items, sel.contract)
    return {"quote": q.model_dump(), "fixes": _fixes(prof, sel.items, q.violations), "addons": _addons(prof, sel.items)}


@router.post("/{sid}/accept")
def accept(sid: str, sel: Selection) -> dict:
    s = _session(sid)
    if not sel.items:
        raise HTTPException(422, "Choose at least one product")
    prof = _profile(s)
    q = quote(prof, sel.items, sel.contract)
    if q.violations:
        raise HTTPException(422, {"message": "This bundle cannot be sold as selected", "violations": [v.model_dump() for v in q.violations]})
    order = Order(session_id=s.id, business=profile_slots.public_view(s.profile),
                  items=[i.model_dump() for i in sel.items], contract=sel.contract, quote=q.model_dump(),
                  events=[OrderEvent(state="QuoteAccepted", note=f"₹{q.monthly_total}/month accepted online")])
    order.save()
    s.status = "converted"
    s.save()
    return {"order_id": order.id, "state": order.state, "quote": q.model_dump()}


@router.get("/orders/{oid}")
def get_order(oid: str) -> dict:
    o = Order.load(oid)
    if o is None:
        raise HTTPException(404, "Order not found")
    return o.model_dump()
