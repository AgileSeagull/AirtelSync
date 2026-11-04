import pytest


def _session(client, msgs):
    sid = client.post("/advisor/sessions", json={"lang": "en"}).json()["session_id"]
    r = None
    for m in msgs:
        r = client.post(f"/advisor/sessions/{sid}/messages", json={"text": m}).json()
    return sid, r


@pytest.fixture
def clinic(client):
    sid, r = _session(client, ["dental clinic in Kochi", "12 staff", "cctv and email", "32TTNXB7384T1ZW"])
    tier = next(t for t in r["recommendation"]["tiers"] if t["tier"] == "recommended")
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in tier["items"]]
    return sid, items, tier


def test_quote_matches_recommendation(client, clinic):
    sid, items, tier = clinic
    r = client.post(f"/checkout/{sid}/quote", json={"items": items, "contract": "12"}).json()
    assert r["quote"]["monthly_total"] == tier["quote"]["monthly_total"]
    assert r["fixes"] == []
    assert any(a["product_id"] == "P12" for a in r["addons"])


def test_contract_changes_price(client, clinic):
    sid, items, _ = clinic
    p12 = client.post(f"/checkout/{sid}/quote", json={"items": items, "contract": "12"}).json()["quote"]["monthly_total"]
    p24 = client.post(f"/checkout/{sid}/quote", json={"items": items, "contract": "24"}).json()["quote"]["monthly_total"]
    assert p24 < p12


def test_removing_internet_offers_fix(client, clinic):
    sid, items, _ = clinic
    without = [i for i in items if i["product_id"] != "P02"]
    r = client.post(f"/checkout/{sid}/quote", json={"items": without}).json()
    fix = next(f for f in r["fixes"] if f["violation"]["product_id"] == "P23")
    assert fix["action"] == "add" and fix["product_id"] in {"P01", "P04"}


def test_accept_rejects_broken_bundle_and_accepts_valid(client, clinic):
    sid, items, _ = clinic
    bad = [i for i in items if i["product_id"] != "P02"]
    assert client.post(f"/checkout/{sid}/accept", json={"items": bad}).status_code == 422
    r = client.post(f"/checkout/{sid}/accept", json={"items": items, "contract": "24"}).json()
    assert r["order_id"].startswith("UD-") and r["state"] == "QuoteAccepted"
    order = client.get(f"/checkout/orders/{r['order_id']}").json()
    assert order["business"]["gstin"] == "32TTN•••••••1ZW"  # masked snapshot
    assert order["quote"]["contract"] == "24"


def test_client_cannot_override_eligibility(client):
    sid, _ = _session(client, ["kirana store in Patna", "2 people", "billing", "no"])
    r = client.post(f"/checkout/{sid}/quote", json={"items": [{"product_id": "P01"}, {"product_id": "P15"}]}).json()
    assert r["fixes"][0]["action"] == "remove" and r["fixes"][0]["product_id"] == "P15"
    locked = next(a for a in r["addons"] if a["product_id"] == "P14")
    assert locked["eligible"] is False and "GST" in locked["locked_reason"]


def test_checkout_requires_finished_profile(client):
    sid = client.post("/advisor/sessions", json={}).json()["session_id"]
    assert client.post(f"/checkout/{sid}/quote", json={"items": []}).status_code == 409
