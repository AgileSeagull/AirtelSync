import os
from pathlib import Path

import pytest

from app.kyc import checks, consent, parse, pipeline
from app.kyc.identifiers import repair_gstin, repair_udyam
from app.kyc.models import Document, KycCase


# ------------------------------------------------------------------ parsing & identifier repair
def test_repair_gstin_variants():
    assert repair_gstin("37ITHKXV5167L12ZS", ["Vindhya"]) == ("37IHKXV5167L1ZS", "checksum")
    assert repair_gstin("O8YKZXS8189L12Z0", ["Saffron Unisex Salon"])[0] == "08YKZXS5189L1ZO"
    assert repair_gstin("37LDYXK0296F1ZB")[1] == "exact"
    assert repair_gstin("garbage", ["x"]) == (None, "unreadable")
    assert repair_gstin(None) == (None, "unreadable")


def test_repair_udyam_and_pincode():
    assert repair_udyam("UDYAM- AP-@0-9751562") == "UDYAM-AP-00-9751562"
    assert repair_udyam("") is None
    assert parse.pincode("Civil Lines, Kochi, Kerala - 75 2083") == "752083"
    assert parse.proprietor("Neha Kaur (Prop. Vindhya Tours & Travels)") == ("Neha Kaur", "Vindhya Tours & Travels")
    assert parse.proprietor("Balaji Realty LLP") == (None, None)


def test_address_lines_are_glued():
    lines = ["Specimen: Electricity Bill", "Billed to Star Electronics", "Supply address Shop/Unit 216, Nehru Nagar, Visakhapatnam, An",
             "dhra Pradesh - 762071", "Bill date 2026-07-06"]
    f = parse.parse("address_proof", lines)
    assert f["address"].endswith("Andhra Pradesh - 762071") and f["bill_date"] == "2026-07-06"


# ------------------------------------------------------------------ rules on synthetic cases (no OCR)
def _clean_case(**over) -> KycCase:
    c = KycCase()
    c.documents = {
        "gst_certificate": Document(doc_type="gst_certificate", source="digilocker", fields={
            "gstin": "37NBLXS1145E1ZU", "legal_name": "Pooja Agarwal (Prop. Star Electronics)", "trade_name": "Star Electronics",
            "constitution": "Proprietorship", "address": "Shop/Unit 216, Nehru Nagar, Visakhapatnam, Andhra Pradesh - 762071"}),
        "udyam_certificate": Document(doc_type="udyam_certificate", source="digilocker", fields={
            "udyam_number": "UDYAM-AP-00-5186772", "enterprise_name": "Star Electronics", "city": "Visakhapatnam"}),
        "signatory_id": Document(doc_type="signatory_id", source="sample", quality={"blur_score": 900}, fields={
            "name": "Pooja Agarwal", "designation": "Owner", "business": "Star Electronics", "valid_till": "2029-03-03"}),
        "address_proof": Document(doc_type="address_proof", source="sample", quality={"blur_score": 900}, fields={
            "billed_to": "Star Electronics", "address": "Shop/Unit 216, Nehru Nagar, Visakhapatnam, Andhra Pradesh - 762071",
            "bill_date": "2026-07-06"}),
    }
    for path, value in over.items():
        doc, field = path.split("__")
        c.documents[doc].fields[field] = value
    return c


def _codes(c):
    out = checks.run(c)
    return checks.verdict(out), {x.code: x.status for x in out}


def test_clean_case_is_approved():
    v, codes = _codes(_clean_case())
    assert v == "approved", codes


@pytest.mark.parametrize("override,code,status", [
    ({"signatory_id__valid_till": "2026-01-01"}, "D_ID_VALIDITY", "action"),
    ({"address_proof__bill_date": "2026-09-01"}, "D_ADDRESS_DATE", "review"),
    ({"address_proof__bill_date": "2026-03-01"}, "D_ADDRESS_DATE", "action"),
    ({"signatory_id__name": "Rahul Mehta"}, "X_SIGNATORY", "action"),
    ({"address_proof__address": "Shop 9, MG Road, Pune, Maharashtra - 411001"}, "X_ADDRESS", "action"),
    ({"address_proof__billed_to": "Moon Traders"}, "X_BUSINESS_NAME", "review"),
])
def test_rule_violations(override, code, status):
    _, codes = _codes(_clean_case(**override))
    assert codes.get(code) == status


def test_application_gstin_mismatch_goes_to_review():
    c = _clean_case()
    c.application = {"gstin": "32TTNXB7384T1ZW"}
    v, codes = _codes(c)
    assert codes["R_APPLICATION_GSTIN"] == "review" and v == "review"


def test_cancelled_gstin_blocks():
    c = _clean_case()
    c.documents["gst_certificate"].fields["gstin"] = "37IHKXV5167L1ZS"
    v, codes = _codes(c)
    assert v == "blocked" and codes["R_GST_STATUS"] == "block"


def test_consent_requires_kyc_purpose():
    with pytest.raises(ValueError):
        consent.record("x", ["marketing"], "en")


# ------------------------------------------------------------------ API flows with real specimen documents (OCR)
def _new_case(client, order_id=None):
    c = client.post("/kyc/cases", json={"order_id": order_id, "lang": "en"}).json()
    return c["id"]


def test_upload_requires_consent(client):
    cid = _new_case(client)
    img = Path("../../data/kyc_documents/K03_signatory_id.png").read_bytes()
    r = client.post(f"/kyc/cases/{cid}/documents", files={"file": ("id.png", img, "image/png")})
    assert r.status_code == 422 and "Consent" in r.json()["detail"]
    assert client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["marketing"]}).status_code == 422


def test_upload_detects_type_and_masks_ids(client):
    cid = _new_case(client)
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification", "service_updates_whatsapp"]})
    img = Path("../../data/kyc_documents/K03_signatory_id.png").read_bytes()
    r = client.post(f"/kyc/cases/{cid}/documents", files={"file": ("photo.png", img, "image/png")}, data={"doc_type": "address_proof"}).json()
    assert r["document_type"] == "signatory_id"  # detected from content, not the slot
    assert r["case"]["documents"]["signatory_id"]["fields"]["id_number"].endswith("7889")
    assert "447889" not in str(r["case"]["documents"]["signatory_id"]["fields"]["id_number"])


def test_blurry_gst_fixed_by_digilocker_then_esign(client):
    cid = _new_case(client)
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification"]})
    client.post(f"/kyc/cases/{cid}/sample/K04")
    r = client.post(f"/kyc/cases/{cid}/verify").json()
    assert r["verdict"] == "needs_action"
    assert any(c["code"] == "Q_BLUR" and c["action"] == "retake" for c in r["checks"])
    assert client.post(f"/kyc/cases/{cid}/esign", json={"otp": "123456"}).status_code == 422
    r = client.post(f"/kyc/cases/{cid}/digilocker", json={"gstin": "27PZSXS1936O1ZH"}).json()
    assert r["documents"]["gst_certificate"]["source"] == "digilocker"
    r = client.post(f"/kyc/cases/{cid}/verify").json()
    assert r["verdict"] == "approved", [c for c in r["checks"] if c["status"] not in ("pass", "info")]
    assert all(d["raw_deleted"] for d in r["documents"].values())  # raw images purged after decision
    assert client.post(f"/kyc/cases/{cid}/esign", json={"otp": "000000"}).status_code == 422
    assert client.post(f"/kyc/cases/{cid}/esign", json={"otp": "123456"}).json()["esigned_at"]


def test_missing_udyam_confirmed_from_registry(client):
    cid = _new_case(client)
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification"]})
    client.post(f"/kyc/cases/{cid}/sample/K05")
    r = client.post(f"/kyc/cases/{cid}/verify").json()
    assert r["verdict"] == "needs_action"
    client.post(f"/kyc/cases/{cid}/confirm-udyam")
    r = client.post(f"/kyc/cases/{cid}/verify").json()
    assert r["verdict"] == "approved"
    assert r["documents"]["udyam_certificate"]["fields"]["udyam_number"] == "UDYAM-KL-00-5521886"


def test_withdrawing_consent_deletes_documents(client):
    cid = _new_case(client)
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification"]})
    client.post(f"/kyc/cases/{cid}/sample/K07")
    vault_dir = Path(os.environ["UDYAM_VAULT_DIR"]) / cid
    assert len(list(vault_dir.glob("*.bin"))) == 4
    r = client.delete(f"/kyc/cases/{cid}/consent").json()
    assert r["documents"] == {} and r["consent_id"] is None
    assert list(vault_dir.glob("*.bin")) == []


def test_order_moves_to_kyc_verified_after_esign(client):
    sid = client.post("/advisor/sessions", json={}).json()["session_id"]
    for m in ["37NBLXS1145E1ZU", "electronics shop", "3 people", "billing", "no"]:
        r = client.post(f"/advisor/sessions/{sid}/messages", json={"text": m}).json()
    tier = r["recommendation"]["tiers"][0]
    oid = client.post(f"/checkout/{sid}/accept", json={"items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in tier["items"]]}).json()["order_id"]
    cid = _new_case(client, oid)
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification"]})
    client.post(f"/kyc/cases/{cid}/sample/K12")
    assert client.post(f"/kyc/cases/{cid}/verify").json()["verdict"] == "approved"
    client.post(f"/kyc/cases/{cid}/esign", json={"otp": "123456"})
    order = client.get(f"/checkout/orders/{oid}").json()
    assert order["state"] == "KYCVerified" and order["kyc_case_id"] == cid


def test_documents_for_another_business_go_to_review(client):
    sid = client.post("/advisor/sessions", json={}).json()["session_id"]
    for m in ["32TTNXB7384T1ZW", "dental clinic", "12 staff", "email", ]:
        r = client.post(f"/advisor/sessions/{sid}/messages", json={"text": m}).json()
    tier = r["recommendation"]["tiers"][0]
    oid = client.post(f"/checkout/{sid}/accept", json={"items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in tier["items"]]}).json()["order_id"]
    cid = _new_case(client, oid)
    client.post(f"/kyc/cases/{cid}/consent", json={"purposes": ["kyc_verification"]})
    client.post(f"/kyc/cases/{cid}/sample/K12")
    r = client.post(f"/kyc/cases/{cid}/verify").json()
    assert r["verdict"] == "review" and any(c["code"] == "R_APPLICATION_GSTIN" for c in r["checks"])


def test_answer_key_all_twelve_applicants():
    from evals.run_kyc_evals import run
    assert run() == 0
