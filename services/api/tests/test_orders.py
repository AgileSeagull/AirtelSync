import pytest


def _verified_order(client, msgs, applicant):
    sid = client.post("/advisor/sessions", json={}).json()["session_id"]
    r = None
    for m in msgs:
        r = client.post(f"/advisor/sessions/{sid}/messages", json={"text": m}).json()
    tier = next(t for t in r["recommendation"]["tiers"] if t["tier"] == "complete")
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in tier["items"]]
    oid = client.post(f"/checkout/{sid}/accept", json={"items": items}).json()["order_id"]
    return oid, items


@pytest.fixture
def star_order(client):
    oid, items = _verified_order(client, ["37NBLXS1145E1ZU", "electronics shop", "3 people", "billing and cctv", "no"], "K12")
    cid = client.post("/kyc/cases", json={"order_id": oid}).json()["id"]
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification", "service_updates_whatsapp"]})
    client.post(f"/kyc/cases/{cid}/sample/K12")
    assert client.post(f"/kyc/cases/{cid}/verify").json()["verdict"] == "approved"
    client.post(f"/kyc/cases/{cid}/esign", json={"otp": "123456"})
    return oid, items


def test_cannot_skip_kyc(client):
    oid, _ = _verified_order(client, ["kirana store in Patna", "2 people", "billing", "no"], None)
    t = client.get(f"/orders/{oid}/track").json()
    assert t["state"] == "QuoteAccepted" and t["owner_action"]["type"] == "kyc"
    assert client.post(f"/orders/{oid}/advance", json={}).status_code == 409
    assert client.post(f"/orders/{oid}/mandate", json={"upi_id": "a@b"}).status_code == 409


def test_full_happy_path_with_notifications(client, star_order):
    oid, _ = star_order
    t = client.get(f"/orders/{oid}/track").json()
    assert t["state"] == "KYCVerified" and t["owner_action"]["type"] == "mandate"
    assert client.post(f"/orders/{oid}/mandate", json={"upi_id": "not a upi"}).status_code == 422
    t = client.post(f"/orders/{oid}/mandate", json={"upi_id": "pooja.agarwal@okbank"}).json()
    assert t["state"] == "MandateSet" and t["mandate"]["upi_id_masked"].startswith("po•••@")
    t = client.post(f"/orders/{oid}/advance", json={}).json()
    assert t["state"] == "InstallScheduled" and t["eta"] and all(l["state"] == "Scheduled" for l in t["lines"])
    assert not t["sla_breach"]
    for expected in ("Installed", "Activated"):
        t = client.post(f"/orders/{oid}/advance", json={}).json()
        assert t["state"] == expected
    assert [s["status"] for s in t["steps"]] == ["done"] * 6
    events = [n["event"] for n in t["notifications"]]
    assert events == ["KYCVerified", "MandateSet", "InstallScheduled", "Installed", "Activated"]
    assert "track/" + oid in t["notifications"][0]["text"]
    assert client.post(f"/orders/{oid}/advance", json={}).status_code == 409


def test_fibre_not_feasible_reroutes_to_airfiber(client, star_order):
    oid, items = star_order
    assert any(i["product_id"] == "P01" for i in items)
    client.post(f"/orders/{oid}/advance", json={})  # mandate (demo UPI)
    t = client.post(f"/orders/{oid}/advance", json={"fibre_feasible": False}).json()
    ids = [l["product_id"] for l in t["lines"]]
    assert "P04" in ids and not {"P01", "P02", "P03"} & set(ids)
    assert "P09" not in ids  # failover needs a fibre line; dropped and told
    assert t["rerouted"] and any(e["state"] == "Rerouted" and "Removed" in e["note"] for e in t["events"])
    assert any(n["event"] == "Rerouted" for n in t["notifications"])


def test_delay_flags_sla_and_notifies(client, star_order):
    oid, _ = star_order
    client.post(f"/orders/{oid}/advance", json={})
    client.post(f"/orders/{oid}/advance", json={})
    t = client.post(f"/orders/{oid}/delay").json()
    assert t["sla_breach"] is True
    assert t["notifications"][-1]["event"] == "Delayed"


def test_whatsapp_only_with_optional_consent(client):
    oid, _ = _verified_order(client, ["37NBLXS1145E1ZU", "electronics shop", "3 people", "billing and cctv", "no"], "K12")
    cid = client.post("/kyc/cases", json={"order_id": oid}).json()["id"]
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification"]})  # no WhatsApp opt-in
    client.post(f"/kyc/cases/{cid}/sample/K12")
    client.post(f"/kyc/cases/{cid}/verify")
    client.post(f"/kyc/cases/{cid}/esign", json={"otp": "123456"})
    from app.orders import notify
    msgs = notify.for_order(oid)
    assert msgs and all(m["channel"] == "in_app" for m in msgs)


def test_whatsapp_used_when_opted_in(star_order):
    from app.orders import notify
    oid, _ = star_order
    assert all(m["channel"] == "whatsapp" for m in notify.for_order(oid))
