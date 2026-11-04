"""Deterministic quote calculation.

Price rule (published on the quote so the owner can see why):
  unit price = price_max − (price_max − price_min) × f
  f = 0 for commitments under 12 months, 0.5 for 12 months, 1.0 for 24 months or more
Each line runs for max(chosen contract, the product's minimum contract).
"""
from __future__ import annotations

import math

from ..config import GST_RATE
from ..data_store import catalogue
from .eligibility import validate_bundle
from .models import ContractChoice, LineItem, Profile, Quote, QuoteLine
from .reference import resolve_city, segment_for

BUNDLE_DISCOUNT_PCT = 5
BUNDLE_DISCOUNT_MIN_CATEGORIES = 3


def commitment_factor(months: int) -> float:
    if months >= 24:
        return 1.0
    if months >= 12:
        return 0.5
    return 0.0


def line_contract(choice: ContractChoice, product_min: int) -> int:
    chosen = 0 if choice == "flexible" else int(choice)
    return max(chosen, product_min)


def unit_price(price_min: int, price_max: int, months: int) -> int:
    return int(round(price_max - (price_max - price_min) * commitment_factor(months)))


def enrich(profile: Profile) -> Profile:
    """Fill segment and city tier/state when the caller did not supply them."""
    p = profile.model_copy()
    if p.city and (p.city_tier is None or p.state is None):
        c = resolve_city(p.city)
        if c:
            p.city_tier = p.city_tier or c["tier"]
            p.state = p.state or c["state"]
    if p.segment is None:
        p.segment = segment_for(p.business_type, p.sites, p.employees)
    if p.gstin and not p.has_gstin:
        p.has_gstin = True
    return p


def quote(profile: Profile, items: list[LineItem], contract: ContractChoice = "12") -> Quote:
    profile = enrich(profile)
    cat = catalogue()
    violations = validate_bundle(profile, items)
    lines: list[QuoteLine] = []
    for item in items:
        p = cat.get(item.product_id)
        if p is None:
            continue
        months = line_contract(contract, p.min_contract_months)
        up = unit_price(p.price_min, p.price_max, months)
        lines.append(QuoteLine(
            product_id=p.id, name=p.name, qty=item.qty, unit=p.unit, contract_months=months,
            unit_price=up, monthly=up * item.qty, setup=p.setup_fee * item.qty, install_days=p.install_days,
        ))

    notes: list[str] = []
    subtotal = sum(l.monthly for l in lines)
    categories = {cat[l.product_id].category for l in lines}
    disc_pct = BUNDLE_DISCOUNT_PCT if len(categories) >= BUNDLE_DISCOUNT_MIN_CATEGORIES else 0
    discount = int(round(subtotal * disc_pct / 100))
    if disc_pct:
        notes.append(f"{disc_pct}% bundle discount for combining {len(categories)} product categories")
    monthly_ex = subtotal - discount
    gst = int(round(monthly_ex * GST_RATE))

    setup = sum(l.setup for l in lines)
    waived = 0
    min_months = min((l.contract_months for l in lines), default=0)
    if profile.segment == "micro" and setup and min_months >= 12:
        waived = setup
        notes.append("Setup fees waived for small shops on a 12-month or longer plan")
    setup_ex = setup - waived
    setup_total = int(round(setup_ex * (1 + GST_RATE)))

    longer = sorted({l.name for l in lines if l.contract_months > (0 if contract == "flexible" else int(contract))})
    if longer:
        notes.append("Minimum contract applies to: " + ", ".join(longer))

    spend = profile.monthly_telecom_spend
    diff = (monthly_ex + gst - spend) if spend is not None else None
    return Quote(
        lines=lines, contract=contract, subtotal_monthly=subtotal, bundle_discount_pct=disc_pct,
        bundle_discount=discount, monthly_ex_gst=monthly_ex, gst=gst, monthly_total=monthly_ex + gst,
        setup_ex_gst=setup, setup_waived=waived, setup_total=setup_total,
        earliest_activation_days=max((l.install_days for l in lines), default=0),
        current_spend=spend, monthly_difference=diff, violations=violations, notes=notes,
    )


def ceil_div(a: int, b: int) -> int:
    return math.ceil(a / b)
