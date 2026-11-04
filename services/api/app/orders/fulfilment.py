"""Order fulfilment state machine, ETAs and owner notifications.

QuoteAccepted → KYCVerified → MandateSet → InstallScheduled → Installed → Activated
Fibre infeasibility (found at scheduling) reroutes fibre lines to 5G AirFiber (P04) before
the owner is asked to wait, which is the single biggest install-stage drop in the data."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..advisor import profile_slots
from ..advisor.session import AdvisorSession
from ..data_store import catalogue
from ..engine.models import LineItem
from ..engine.pricing import enrich, quote
from . import notify
from .models import Order, OrderEvent

STEPS = ["QuoteAccepted", "KYCVerified", "MandateSet", "InstallScheduled", "Installed", "Activated"]
STEP_LABELS = {
    "en": {"QuoteAccepted": "Quote accepted", "KYCVerified": "Business verified", "MandateSet": "AutoPay set up",
           "InstallScheduled": "Installation scheduled", "Installed": "Installed", "Activated": "Services active"},
    "hi": {"QuoteAccepted": "कोटेशन स्वीकार", "KYCVerified": "बिज़नेस वेरिफ़ाइड", "MandateSet": "AutoPay चालू",
           "InstallScheduled": "इंस्टॉलेशन तय", "Installed": "इंस्टॉल हो गया", "Activated": "सेवाएँ चालू"},
}
FIBRE = {"P01", "P02", "P03"}
UPI_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")


class FulfilmentError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat(timespec="seconds")


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _event(o: Order, state: str, note: str) -> None:
    o.events.append(OrderEvent(state=state, note=note))


def _lang(o: Order) -> str:
    s = AdvisorSession.load(o.session_id)
    return s.lang if s else "en"


def ensure_lines(o: Order) -> None:
    if o.lines:
        return
    cat = catalogue()
    for it in o.items:
        p = cat[it["product_id"]]
        o.lines.append({"product_id": p.id, "name": p.name, "qty": it["qty"], "install_days": p.install_days,
                        "state": "Pending", "eta": None})


def set_mandate(o: Order, upi_id: str) -> Order:
    if o.state != "KYCVerified":
        raise FulfilmentError("AutoPay can be set up after your business is verified")
    if not UPI_RE.match(upi_id or ""):
        raise FulfilmentError("Enter a UPI ID like name@bank")
    o.mandate = {"upi_id_masked": upi_id[:2] + "•••@" + upi_id.split("@")[1], "max_amount": o.quote["monthly_total"],
                 "frequency": "monthly", "set_at": _iso(_now())}
    o.state = "MandateSet"
    _event(o, "MandateSet", f"UPI AutoPay up to ₹{o.quote['monthly_total']}/month approved")
    notify.send(o, "MandateSet", _lang(o))
    o.save()
    return o


def schedule(o: Order, fibre_feasible: bool = True) -> Order:
    if o.state != "MandateSet":
        raise FulfilmentError("Installation is scheduled after AutoPay is set up")
    ensure_lines(o)
    if not fibre_feasible and any(l["product_id"] in FIBRE for l in o.lines):
        reroute_to_airfiber(o)
    start = _now() + timedelta(days=1)
    for line in o.lines:
        line["state"] = "Scheduled"
        line["eta"] = _iso(start + timedelta(days=line["install_days"]))
    o.eta = max(l["eta"] for l in o.lines)
    promised = _parse(next(e.at for e in o.events if e.state == "KYCVerified")) + timedelta(days=o.quote["earliest_activation_days"] + 1)
    o.promised_by = _iso(max(promised, _parse(o.eta)))
    o.state = "InstallScheduled"
    slot = start.replace(hour=10, minute=0, second=0, microsecond=0)
    o.install_slot = _iso(slot)
    _event(o, "InstallScheduled", f"Technician visit booked for {slot.strftime('%a %d %b')}, 10am–1pm")
    notify.send(o, "InstallScheduled", _lang(o), slot=slot.strftime("%a %d %b"), eta=_parse(o.eta).strftime("%a %d %b"))
    o.save()
    return o


def reroute_to_airfiber(o: Order) -> None:
    cat = catalogue()
    fibre_lines = [l for l in o.lines if l["product_id"] in FIBRE]
    sites = max(l["qty"] for l in fibre_lines)
    o.lines = [l for l in o.lines if l["product_id"] not in FIBRE]
    p = cat["P04"]
    o.lines.insert(0, {"product_id": "P04", "name": p.name, "qty": sites, "install_days": p.install_days,
                       "state": "Pending", "eta": None})
    o.items = [{"product_id": l["product_id"], "qty": l["qty"]} for l in o.lines]
    s = AdvisorSession.load(o.session_id)
    prof = enrich(profile_slots.to_profile(s.profile)) if s else None
    if prof is not None:
        q = quote(prof, [LineItem(**i) for i in o.items], o.contract)
        dropped: list[str] = []
        if q.violations:  # AirFiber cannot carry something in the bundle: drop it rather than sell a broken bundle
            bad = {v.product_id for v in q.violations}
            dropped = [l["name"] for l in o.lines if l["product_id"] in bad]
            o.lines = [l for l in o.lines if l["product_id"] not in bad]
            o.items = [i for i in o.items if i["product_id"] not in bad]
            q = quote(prof, [LineItem(**i) for i in o.items], o.contract)
        old_total = o.quote["monthly_total"]
        o.quote = q.model_dump()
        diff = q.monthly_total - old_total
        note = (f"Fibre isn't available at your address yet, so we switched to {p.name} (installs in {p.install_days} days). "
                f"New monthly price ₹{q.monthly_total} ({'−' if diff < 0 else '+'}₹{abs(diff)})."
                + (f" Removed (needs a fibre line): {', '.join(dropped)}." if dropped else ""))
    else:
        note = f"Fibre isn't available at your address yet, so we switched to {p.name}."
    o.rerouted = True
    _event(o, "Rerouted", note)
    notify.send(o, "Rerouted", _lang(o), note=note)


def install(o: Order) -> Order:
    if o.state != "InstallScheduled":
        raise FulfilmentError("Nothing scheduled yet")
    for line in o.lines:
        line["state"] = "Installed"
    o.state = "Installed"
    _event(o, "Installed", "Technician completed installation and tested every service")
    notify.send(o, "Installed", _lang(o))
    o.save()
    return o


def activate(o: Order) -> Order:
    if o.state != "Installed":
        raise FulfilmentError("Services are activated after installation")
    for line in o.lines:
        line["state"] = "Active"
    o.state = "Activated"
    o.activated_at = _iso(_now())
    _event(o, "Activated", "All services are live. First bill on your AutoPay date.")
    notify.send(o, "Activated", _lang(o))
    o.save()
    return o


def delay(o: Order, days: int = 5) -> Order:
    """Simulate an installation delay: pushes ETAs, flags SLA breach and escalates proactively."""
    if o.state != "InstallScheduled":
        raise FulfilmentError("Only a scheduled installation can be delayed")
    for line in o.lines:
        if line["eta"]:
            line["eta"] = _iso(_parse(line["eta"]) + timedelta(days=days))
    o.eta = max(l["eta"] for l in o.lines if l["eta"])
    o.sla_breach = bool(o.promised_by and _parse(o.eta) > _parse(o.promised_by))
    _event(o, "Delayed", f"Installation delayed by {days} days (equipment stock). Escalated to the area installation lead.")
    notify.send(o, "Delayed", _lang(o), eta=_parse(o.eta).strftime("%a %d %b"))
    o.save()
    return o


def advance(o: Order, fibre_feasible: bool = True) -> Order:
    """Demo simulator: perform the next step as the back office would."""
    if o.state == "QuoteAccepted":
        raise FulfilmentError("Complete business verification (KYC) first")
    if o.state == "KYCVerified":
        return set_mandate(o, "demo@upi")
    if o.state == "MandateSet":
        return schedule(o, fibre_feasible)
    if o.state == "InstallScheduled":
        return install(o)
    if o.state == "Installed":
        return activate(o)
    raise FulfilmentError("Order is already active")


def track(o: Order) -> dict:
    lang = _lang(o)
    labels = STEP_LABELS.get(lang, STEP_LABELS["en"])
    at = {}
    for e in o.events:
        at.setdefault(e.state, e.at)
    idx = STEPS.index(o.state)
    steps = [{"state": s, "label": labels[s], "status": "done" if i <= idx else ("current" if i == idx + 1 else "upcoming"),
              "at": at.get(s)} for i, s in enumerate(STEPS)]
    owner_action = None
    if o.state == "QuoteAccepted":
        owner_action = {"type": "kyc", "kyc_case_id": o.kyc_case_id}
    elif o.state == "KYCVerified":
        owner_action = {"type": "mandate", "amount": o.quote["monthly_total"]}
    ensure_lines(o)
    return {
        "order_id": o.id, "state": o.state, "label": labels[o.state], "steps": steps, "lines": o.lines,
        "eta": o.eta, "promised_by": o.promised_by, "install_slot": o.install_slot, "sla_breach": o.sla_breach,
        "rerouted": o.rerouted, "mandate": o.mandate, "quote": {k: o.quote[k] for k in ("monthly_total", "setup_total", "earliest_activation_days")},
        "contract": o.contract, "business": {k: o.business.get(k) for k in ("trade_name", "business_type", "city")},
        "events": [e.model_dump() for e in o.events], "notifications": notify.for_order(o.id),
        "owner_action": owner_action, "activated_at": o.activated_at, "lang": lang,
    }
