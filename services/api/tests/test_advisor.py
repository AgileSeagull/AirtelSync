import asyncio
import json
from typing import Any

import pytest
from pydantic import BaseModel

from app.advisor import guard, llm, nlu, service
from app.advisor.session import AdvisorSession


# ------------------------------------------------------------------ guard
def test_guard_allows_tool_numbers_and_blocks_invented_ones():
    nums, pids = guard.allowed_from([{"monthly_total": 6701, "items": [{"id": "P02"}]}])
    assert guard.check("It costs ₹6,701/month for P02.", nums, pids) == []
    assert guard.check("Only ₹5,999 per month!", nums, pids)
    assert guard.check("Add P15 too", nums, pids)
    assert guard.check("कीमत ₹६,७०१ है", nums, pids) == []  # Devanagari digits
    assert guard.check("कीमत 7000 रुपये है", nums, pids)
    assert guard.check("We have 12 staff and 3 sites", nums, pids) == []  # plain counts are not money


# ------------------------------------------------------------------ NLU
@pytest.mark.parametrize("text,key,value", [
    ("I run a dental clinic in Kochi", "business_type", "Dental clinic"),
    ("I run a dental clinic in Kochi", "city", "Kochi"),
    ("मेरी किराना दुकान है पटना में", "business_type", "Kirana store"),
    ("मेरी किराना दुकान है पटना में", "city", "Patna"),
    ("we are 12 staff with 3 branches", "employees", 12),
    ("we are 12 staff with 3 branches", "sites", 3),
    ("२ लोग", "employees", 2),
    ("we pay Rs 2,500 a month on mobile hotspot", "monthly_telecom_spend", 2500),
    ("we pay Rs 2,500 a month on mobile hotspot", "current_internet", "Mobile hotspot"),
    ("my gst is 32ttnxb7384t1zw", "gstin", "32TTNXB7384T1ZW"),
    ("in bombay", "city", "Mumbai"),
])
def test_nlu_extracts(text, key, value):
    assert nlu.extract(text, None)[key] == value


def test_nlu_needs_and_negation():
    f = nlu.extract("need CCTV, billing and WhatsApp", None)
    assert set(f["needs"]) == {"cctv", "billing_pos", "whatsapp"}
    assert nlu.extract("no", "gstin")["has_gstin"] is False
    assert nlu.extract("नहीं", "gstin")["has_gstin"] is False
    assert "has_gstin" not in nlu.extract("no", "needs")
    assert nlu.extract("5", "employees")["employees"] == 5


# ------------------------------------------------------------------ fake Claude
class FakeBlock(BaseModel):
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None


class FakeResp(BaseModel):
    content: list[FakeBlock]
    stop_reason: str


def tool(name, args, i):
    return FakeResp(content=[FakeBlock(type="tool_use", id=f"tu{i}", name=name, input=args)], stop_reason="tool_use")


def text(t):
    return FakeResp(content=[FakeBlock(type="text", text=t)], stop_reason="end_turn")


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setenv("UDYAM_ADVISOR_MODE", "llm")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    script: list = []
    sent: list = []

    async def fake_create(messages):
        sent.append(json.loads(json.dumps(messages)))
        step = script.pop(0)
        return step(messages) if callable(step) else step

    monkeypatch.setattr(llm, "_create", fake_create)
    return script, sent


def _price_from_history(messages):
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    data = json.loads(b["content"])
                    if "tiers" in data:
                        return data["tiers"][1]["monthly_total_incl_gst"]
    raise AssertionError("no recommendation in history")


def test_llm_tool_loop_records_profile_and_recommends(fake_llm):
    script, sent = fake_llm
    script += [
        tool("update_profile", {"business_type": "Dental clinic", "city": "Kochi", "employees": 12, "needs": ["cctv"]}, 1),
        tool("recommend_bundle", {}, 2),
        lambda msgs: text(f"I recommend the Recommended plan at ₹{_price_from_history(msgs):,}/month incl. GST."),
    ]
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "Dental clinic in Kochi, 12 staff, need CCTV"))
    assert mode == "llm"
    assert s.recommendation and s.profile["city"] == "Kochi"
    assert "₹" in reply
    # History is append-only: each request's messages extend the previous one.
    for a, b in zip(sent, sent[1:]):
        assert b[: len(a)] == a


def test_llm_guard_retries_then_accepts(fake_llm):
    script, sent = fake_llm
    script += [
        tool("update_profile", {"business_type": "Salon", "city": "Pune", "employees": 3}, 1),
        tool("recommend_bundle", {}, 2),
        text("Just ₹99/month!"),  # invented price → guard rejects
        lambda msgs: text(f"It is ₹{_price_from_history(msgs):,}/month incl. GST."),
    ]
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "salon in pune, 3 people"))
    assert mode == "llm" and "99/month" not in reply
    assert any("Automated check" in str(m["content"]) for m in sent[-1] if m["role"] == "user")


def test_llm_failure_falls_back_to_scripted(fake_llm, monkeypatch):
    async def boom(messages):
        raise llm.LLMUnavailable("network down")

    monkeypatch.setattr(llm, "_create", boom)
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "kirana store in Patna"))
    assert mode == "scripted" and s.llm_disabled
    assert s.profile["business_type"] == "Kirana store"


def test_tool_error_is_returned_to_model(fake_llm):
    script, sent = fake_llm
    script += [tool("recommend_bundle", {}, 1), text("Could you tell me your city?")]
    s = service.start("en")
    asyncio.run(service.message(s, "hello"))
    last_user = [m for m in sent[-1] if m["role"] == "user"][-1]
    assert last_user["content"][0]["is_error"] is True


# ------------------------------------------------------------------ API + evals
def test_advisor_api_round_trip(client):
    sid = client.post("/advisor/sessions", json={"lang": "hi"}).json()["session_id"]
    r = client.post(f"/advisor/sessions/{sid}/messages", json={"text": "मेरी बेकरी है मुंबई में"}).json()
    assert r["mode"] == "scripted" and r["profile"]["business_type"] == "Bakery"
    for msg in ["4 लोग", "CCTV चाहिए", "नहीं"]:
        r = client.post(f"/advisor/sessions/{sid}/messages", json={"text": msg}).json()
    assert r["recommendation"]["segment"] == "micro"
    assert client.get(f"/advisor/sessions/{sid}").json()["status"] == "recommended"
    assert client.get("/advisor/sessions/nope").status_code == 404


def test_gstin_is_masked_in_session_view(client):
    sid = client.post("/advisor/sessions", json={}).json()["session_id"]
    r = client.post(f"/advisor/sessions/{sid}/messages", json={"text": "32TTNXB7384T1ZW"}).json()
    assert r["profile"]["gstin"] == "32TTN•••••••1ZW"


def test_all_eval_scenarios_pass_in_scripted_mode():
    from evals.run_advisor_evals import main
    assert asyncio.run(main([])) == 0
