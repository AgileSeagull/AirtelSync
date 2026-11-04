def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_catalogue(client):
    data = client.get("/catalogue").json()
    assert len(data) == 25 and data[0]["id"] == "P01"


def test_gstin_lookup_found(client):
    r = client.get("/mock/gstin/32TTNXB7384T1ZW")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "Active" and body["city"] == "Kochi" and body["pincode"] == "289398"


def test_gstin_lookup_cancelled_is_reported(client):
    assert client.get("/mock/gstin/37IHKXV5167L1ZS").json()["status"] == "Cancelled"


def test_gstin_lookup_errors(client):
    assert client.get("/mock/gstin/32TTNXB7384T1ZX").status_code == 422
    assert client.get("/mock/gstin/ABC").status_code == 422


def test_gstin_valid_but_unregistered(client):
    from app.ids.gstin import checksum_char
    base = "27ABCXE1234F1Z"  # PAN 4th char X (synthetic)
    r = client.get(f"/mock/gstin/{base}{checksum_char(base)}")
    assert r.status_code == 404


def test_udyam_lookup(client):
    assert client.get("/mock/udyam/UDYAM-KL-00-3078801").json()["enterprise_name"] == "Balaji Dental Care LLP"
    assert client.get("/mock/udyam/UDYAM-KL-00-0000000").status_code == 404
    assert client.get("/mock/udyam/garbage").status_code == 422


def test_profile_prefill_from_gstin(client):
    p = client.get("/profile/from-gstin/03PJNXS4821G1ZB").json()
    assert p["trade_name"] == "Saffron Bakers" and p["city"] == "Ludhiana" and p["city_tier"] == 2


def test_recommend_and_quote_round_trip(client):
    profile = {"business_type": "Dental clinic", "city": "Kochi", "employees": 12, "has_gstin": True, "needs": ["cctv"]}
    rec = client.post("/engine/recommend", json=profile).json()
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in rec["tiers"][1]["items"]]
    q = client.post("/engine/quote", json={"profile": profile, "items": items, "contract": "24"}).json()
    assert q["violations"] == [] and q["monthly_total"] > 0


def test_validate_endpoint(client):
    v = client.post("/engine/validate", json={"profile": {"business_type": "Salon"}, "items": [{"product_id": "P23"}]}).json()
    assert v[0]["rule"] == "dependency"


def test_city_reference(client):
    assert client.get("/reference/city", params={"name": "bangalore"}).json()["city"] == "Bengaluru"
    assert client.get("/reference/city", params={"name": "Shimla"}).json()["known"] is False
