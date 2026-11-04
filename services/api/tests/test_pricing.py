from app.engine.models import LineItem, Profile
from app.engine.pricing import commitment_factor, quote, unit_price

PROF = Profile(business_type="Dental clinic", city="Kochi", employees=12, has_gstin=True, monthly_telecom_spend=3000)
MICRO = Profile(business_type="Salon", city="Patna", employees=3)


def test_commitment_factor_and_unit_price():
    assert [commitment_factor(m) for m in (1, 6, 12, 24, 36)] == [0, 0, 0.5, 1.0, 1.0]
    assert unit_price(999, 1199, 12) == 1099
    assert unit_price(999, 1199, 24) == 999
    assert unit_price(299, 399, 1) == 399


def test_line_contract_respects_product_minimum():
    q = quote(PROF, [LineItem(product_id="P07"), LineItem(product_id="P21")], contract="12")
    by = {l.product_id: l for l in q.lines}
    assert by["P07"].contract_months == 12 and by["P21"].contract_months == 24
    assert any("Minimum contract" in n for n in q.notes)
    flex = quote(PROF, [LineItem(product_id="P07")], contract="flexible")
    assert flex.lines[0].contract_months == 1 and flex.lines[0].unit_price == 399


def test_totals_add_up():
    q = quote(PROF, [LineItem(product_id="P02"), LineItem(product_id="P16", qty=7), LineItem(product_id="P20", qty=7)])
    assert q.subtotal_monthly == sum(l.monthly for l in q.lines)
    assert q.bundle_discount_pct == 5  # connectivity, cloud, security
    assert q.monthly_ex_gst == q.subtotal_monthly - q.bundle_discount
    assert q.monthly_total == q.monthly_ex_gst + q.gst
    assert q.gst == round(q.monthly_ex_gst * 0.18)
    assert q.monthly_difference == q.monthly_total - 3000


def test_no_discount_below_three_categories():
    q = quote(PROF, [LineItem(product_id="P02"), LineItem(product_id="P08", qty=2)])
    assert q.bundle_discount_pct == 0


def test_setup_waived_for_micro_on_12_months_only():
    items = [LineItem(product_id="P01"), LineItem(product_id="P23", qty=2)]
    q12 = quote(MICRO, items, "12")
    assert q12.setup_ex_gst == 3600 and q12.setup_waived == 3600 and q12.setup_total == 0
    qp = quote(PROF, items, "12")
    assert qp.setup_waived == 0 and qp.setup_total == round(3600 * 1.18)


def test_earliest_activation_is_slowest_item():
    q = quote(PROF, [LineItem(product_id="P02"), LineItem(product_id="P12", qty=2), LineItem(product_id="P21")])
    assert q.earliest_activation_days == 10


def test_quote_reports_violations():
    q = quote(MICRO, [LineItem(product_id="P15")])
    assert q.violations and q.violations[0].rule == "gstin"
