"""The engine must reject every rule-breaking bundle that was sold in Q2 2026."""
from app.data_store import catalogue, gstin_registry, leads
from app.engine.eligibility import validate_bundle
from app.engine.models import LineItem, Profile


def _profile(r, use_registry: bool) -> Profile:
    status = gstin_registry()[r["gstin"]]["status"] if (use_registry and r["has_gstin"] == "Y") else None
    return Profile(business_type=r["business_type"], city=r["city"], city_tier=int(r["city_tier"]), state=r["state"],
                   employees=int(r["employee_count"]), sites=int(r["num_sites"]), has_gstin=r["has_gstin"] == "Y",
                   gstin=r["gstin"] or None, gstin_status=status)


def _items(bundle: str) -> list[LineItem]:
    out = []
    for part in bundle.split(";"):
        pid, qty = part.split("x")
        out.append(LineItem(product_id=pid, qty=int(qty)))
    return out


def _activated():
    return [r for r in leads() if r["outcome"] == "Activated"]


def test_historical_rule_breaks_are_rejected():
    flagged = {r["lead_id"]: validate_bundle(_profile(r, False), _items(r["bundle_products"])) for r in _activated()}
    bad = {k: v for k, v in flagged.items() if v}
    assert len(_activated()) == 368
    assert len(bad) == 48  # 48 leads carrying 49 rule-breaking line items
    assert sum(len({x.product_id for x in v}) for v in bad.values()) == 49
    rules = sorted({x.rule for v in bad.values() for x in v})
    assert rules == ["city_tier", "dependency", "gstin", "min_employees"]


def test_registry_status_catches_more_bad_sales():
    with_registry = [r for r in _activated() if validate_bundle(_profile(r, True), _items(r["bundle_products"]))]
    without = [r for r in _activated() if validate_bundle(_profile(r, False), _items(r["bundle_products"]))]
    assert len(with_registry) > len(without)


def test_dependency_rule():
    prof = Profile(business_type="Salon", city_tier=1, employees=3)
    v = validate_bundle(prof, [LineItem(product_id="P23", qty=2)])
    assert [x.rule for x in v] == ["dependency"]
    assert validate_bundle(prof, [LineItem(product_id="P23", qty=2), LineItem(product_id="P04")]) == []


def test_unknown_product():
    v = validate_bundle(Profile(business_type="Salon"), [LineItem(product_id="P99")])
    assert v[0].rule == "unknown_product"


def test_cancelled_gstin_blocks_gst_products():
    prof = Profile(business_type="CA firm", city_tier=1, employees=30, has_gstin=True, gstin_status="Cancelled")
    gst_products = [p.id for p in catalogue().values() if p.requires_gstin]
    for pid in gst_products:
        assert any(x.rule == "gstin" for x in validate_bundle(prof, [LineItem(product_id=pid)]))
