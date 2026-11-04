import numpy as np

from app.console import propensity

SALES = {"X-Console-Role": "sales"}
PARTNER = {"X-Console-Role": "partner"}


def test_model_beats_chance_on_time_holdout():
    ev = propensity.evaluation()
    assert ev["test_auc"] >= 0.65 and ev["top_decile_lift"] >= 2.0


def test_model_has_no_leakage_features():
    for f in propensity.CATEGORICAL + propensity.NUMERIC:
        assert not any(w in f for w in ("date", "drop", "outcome", "stage", "bundle", "churn", "nps"))


def test_auc_helper():
    assert propensity.auc(np.array([0, 0, 1, 1.0]), np.array([.1, .2, .8, .9])) == 1.0


def test_console_requires_role(client):
    assert client.get("/console/summary").status_code == 401
    assert client.get("/console/summary", headers=SALES).status_code == 200


def test_unclosed_advisor_leads_are_scored_and_routed(client):
    sid = client.post("/advisor/sessions", json={}).json()["session_id"]
    for m in ["Restaurant chain in Pune", "60 staff, 6 outlets"]:
        client.post(f"/advisor/sessions/{sid}/messages", json={"text": m})
    sid2 = client.post("/advisor/sessions", json={}).json()["session_id"]
    for m in ["kirana store in Patna", "2 people", "billing", "no"]:
        client.post(f"/advisor/sessions/{sid2}/messages", json={"text": m})
    leads = client.get("/console/leads", headers=SALES).json()
    by = {l["session_id"]: l for l in leads}
    assert by[sid]["route_to"] == "field_sales" and by[sid]["reason"] == "Left during discovery"
    assert by[sid2]["route_to"] == "channel_partner" and by[sid2]["reason"] == "Saw a plan but did not accept"
    assert 0 < by[sid2]["score"] < 1 and by[sid2]["drivers"]
    assert [l["priority"] for l in leads] == sorted((l["priority"] for l in leads), reverse=True)
    partner_view = client.get("/console/leads", headers=PARTNER).json()
    assert all(l["route_to"] == "channel_partner" for l in partner_view)


def test_reengage_list(client):
    r = client.get("/console/reengage?limit=10", headers=SALES).json()
    assert r["pool"] > 2000 and len(r["leads"]) == 10
    assert r["leads"][0]["score"] >= r["leads"][-1]["score"]


def test_assisted_mode_needs_owner_code(client):
    sid = client.post("/advisor/sessions", json={}).json()["session_id"]
    client.post(f"/advisor/sessions/{sid}/messages", json={"text": "salon in Indore"})
    code = client.post(f"/console/leads/{sid}/assist", headers=PARTNER).json()["demo_code"]
    bad = "0000" if code != "0000" else "1111"
    assert client.post(f"/console/leads/{sid}/assist/confirm", headers=PARTNER, json={"code": bad}).status_code == 422
    r = client.post(f"/console/leads/{sid}/assist/confirm", headers=PARTNER, json={"code": code, "partner": "Sharma Telecom"}).json()
    assert r["continue_url"].endswith(sid)
    view = client.get(f"/advisor/sessions/{sid}").json()
    assert "_assist" not in view["profile"]


def test_kyc_review_decision_is_staff_only_and_audited(client):
    cid = client.post("/kyc/cases", json={}).json()["id"]
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification"]})
    client.post(f"/kyc/cases/{cid}/sample/K07")
    assert client.post(f"/kyc/cases/{cid}/verify").json()["verdict"] == "review"
    queue = client.get("/console/kyc-reviews", headers=SALES).json()
    assert any(q["id"] == cid for q in queue)
    assert client.post(f"/console/kyc-reviews/{cid}", headers=PARTNER, json={"decision": "approve", "note": "looks ok"}).status_code == 403
    assert client.post(f"/console/kyc-reviews/{cid}", headers=SALES, json={"decision": "approve", "note": ""}).status_code == 422
    r = client.post(f"/console/kyc-reviews/{cid}", headers=SALES,
                    json={"decision": "reject", "note": "Legal name altered vs GST records"}).json()
    assert r["verdict"] == "blocked"
    from app import store
    assert any(a["action"] == "kyc.review_reject" and a["entity"] == cid for a in store.all("audit"))


def test_console_masks_identifiers_typed_in_chat(client):
    from app.console.api import mask_free_text
    assert mask_free_text("my gst 32TTNXB7384T1ZW, call 9876543210, pay me at ravi@okbank") == \
        "my gst 32TTN•••••••1ZW, call ••••••3210, pay me at •••@•••"
    sid = client.post("/advisor/sessions", json={}).json()["session_id"]
    client.post(f"/advisor/sessions/{sid}/messages", json={"text": "dental clinic in Kochi"})
    client.post(f"/advisor/sessions/{sid}/messages", json={"text": "32TTNXB7384T1ZW"})
    lead = next(l for l in client.get("/console/leads", headers=SALES).json() if l["session_id"] == sid)
    assert "32TTNXB7384T1ZW" not in str(lead)
