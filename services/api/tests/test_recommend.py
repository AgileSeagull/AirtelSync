import pytest

from app.data_store import catalogue, gstin_registry, leads
from app.engine.eligibility import validate_bundle
from app.engine.models import NEEDS, LineItem, Profile
from app.engine.recommend import NEED_PRODUCT, recommend

INTEREST_TO_NEED = {pid: need for need, pid in NEED_PRODUCT.items()}


def ids(tier):
    return [i.product_id for i in tier.items]


def lead_profile(r) -> Profile:
    needs = sorted({INTEREST_TO_NEED[p] for p in r["products_of_interest"].split(";") if p in INTEREST_TO_NEED})
    status = gstin_registry()[r["gstin"]]["status"] if r["has_gstin"] == "Y" else None
    return Profile(business_type=r["business_type"], city=r["city"], employees=int(r["employee_count"]),
                   sites=int(r["num_sites"]), has_gstin=r["has_gstin"] == "Y", gstin=r["gstin"] or None,
                   gstin_status=status, current_internet=r["current_internet"] or None, needs=needs)


def test_every_lead_gets_a_valid_bundle_in_every_tier():
    """Property test over all 5,000 real-looking profiles: no tier may ever break a rule."""
    for r in leads():
        rec = recommend(lead_profile(r))
        assert [t.tier for t in rec.tiers] == ["essential", "recommended", "complete"]
        for t in rec.tiers:
            assert t.items, r["lead_id"]
            assert validate_bundle(rec.profile, [LineItem(product_id=i.product_id, qty=i.qty) for i in t.items]) == []
            assert len(set(ids(t))) == len(ids(t))


def test_tiers_are_nested():
    rec = recommend(Profile(business_type="Dental clinic", city="Kochi", employees=12, has_gstin=True))
    e, r, c = (set(ids(t)) for t in rec.tiers)
    assert e <= r <= c


def test_segment_inference():
    assert recommend(Profile(business_type="Kirana store")).segment == "micro"
    assert recommend(Profile(business_type="Dental clinic")).segment == "prof"
    assert recommend(Profile(business_type="Auto-parts unit", employees=40)).segment == "mfg"
    assert recommend(Profile(business_type="Bakery", sites=4)).segment == "multi"
    assert recommend(Profile(business_type="Yoga studio")).segment == "prof"
    assert recommend(Profile(business_type="Tea stall")).segment == "micro"


def test_no_gstin_means_no_gst_products_and_a_nudge():
    rec = recommend(Profile(business_type="Kirana store", city="Patna", employees=2, needs=["whatsapp", "billing_pos"]))
    gst_only = {p.id for p in catalogue().values() if p.requires_gstin}
    for t in rec.tiers:
        assert not gst_only.intersection(ids(t))
    assert any(e.product_id == "P15" and e.rule == "gstin" for e in rec.excluded)
    assert any("Register for GST" in n for n in rec.notes)


def test_cancelled_gstin_note():
    rec = recommend(Profile(business_type="CA firm", city="Pune", employees=8, has_gstin=True, gstin_status="Cancelled"))
    assert any("cancelled" in n for n in rec.notes)


def test_tier2_city_never_gets_tier1_only_fibre():
    rec = recommend(Profile(business_type="Diagnostic lab", city="Nagpur", employees=20, has_gstin=True, needs=["high_speed"]))
    for t in rec.tiers:
        assert "P03" not in ids(t)
    rec1 = recommend(Profile(business_type="Diagnostic lab", city="Mumbai", employees=20, has_gstin=True, needs=["high_speed"]))
    assert ids(rec1.tiers[0])[0] == "P03"


def test_small_factory_asking_for_leased_line_gets_fibre_and_explanation():
    rec = recommend(Profile(business_type="Textile unit", city="Surat", employees=8, has_gstin=True, needs=["dedicated_line"]))
    assert ids(rec.tiers[0])[0] == "P02"
    assert any("leased line is not possible" in n for n in rec.notes)


def test_big_factory_gets_leased_line():
    rec = recommend(Profile(business_type="Auto-parts unit", city="Pune", employees=120, has_gstin=True))
    assert ids(rec.tiers[0])[0] == "P06"
    rec = recommend(Profile(business_type="Auto-parts unit", city="Pune", employees=40, has_gstin=True))
    assert ids(rec.tiers[0])[0] == "P05"


def test_fibre_not_feasible_switches_to_airfiber_and_keeps_cctv():
    rec = recommend(Profile(business_type="Salon", city="Indore", employees=3, fibre_feasible=False, needs=["cctv"]))
    assert ids(rec.tiers[0])[:1] == ["P04"]
    assert "P23" in ids(rec.tiers[0])


def test_mobile_only_request():
    rec = recommend(Profile(business_type="Boutique", city="Jaipur", employees=2, needs=["mobile_lines"]))
    assert ids(rec.tiers[0]) == ["P07"]


def test_multi_site_quantities_scale_with_sites():
    rec = recommend(Profile(business_type="Pharmacy chain", city="Delhi", employees=50, sites=7, has_gstin=True))
    first = rec.tiers[0].items[0]
    assert first.product_id == "P02" and first.qty == 7


def test_explicit_quantities_respected():
    rec = recommend(Profile(business_type="Hardware store", city="Lucknow", employees=4, needs=["cctv"], cameras=4))
    cctv = next(i for i in rec.tiers[0].items if i.product_id == "P23")
    assert cctv.qty == 4


def test_every_item_has_a_reason():
    rec = recommend(Profile(business_type="Coaching centre", city="Kolkata", employees=10, has_gstin=True,
                            needs=list(NEEDS)))
    for t in rec.tiers:
        for i in t.items:
            assert i.reasons and i.why


@pytest.mark.parametrize("bt", ["Kirana store", "Law office", "Gym chain", "Printing press"])
def test_deterministic(bt):
    p = Profile(business_type=bt, city="Bhopal", employees=12, sites=1, has_gstin=True)
    assert recommend(p) == recommend(p)
