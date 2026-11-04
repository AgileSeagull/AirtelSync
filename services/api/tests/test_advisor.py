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
    ("मेरा डेंटल क्लिनिक है कोच्चि में", "city", "Kochi"),
    ("मेरा डेंटल क्लिनिक है कोच्चि में", "business_type", "Dental clinic"),
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
    monkeypatch.setenv("UDYAM_LLM_PROVIDER", "anthropic")
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
    assert mode == "llm:anthropic"
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
    assert mode == "llm:anthropic" and "99/month" not in reply
    assert any("Automated check" in str(m["content"]) for m in sent[-1] if m["role"] == "user")


def test_llm_failure_falls_back_to_scripted(fake_llm, monkeypatch):
    async def boom(messages):
        raise llm.LLMUnavailable("network down")

    monkeypatch.setattr(llm, "_create", boom)
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "kirana store in Patna"))
    # a transient failure costs one turn only: the LLM is tried again next turn, with the
    # scripted exchange in its history
    assert mode == "scripted" and not s.llm_disabled
    assert s.profile["business_type"] == "Kirana store"
    assert [m["role"] for m in s.llm_messages] == ["user", "assistant"]
    assert s.llm_messages[1]["content"][0]["text"] == reply

    sent = []

    async def ok(messages):
        sent.append(json.loads(json.dumps(messages)))
        return text("Got it.")

    monkeypatch.setattr(llm, "_create", ok)
    reply, mode = asyncio.run(service.message(s, "5 people"))
    assert mode == "llm:anthropic" and "kirana" in json.dumps(sent[-1]).lower()


def test_llm_bad_key_disables_llm_for_session(fake_llm, monkeypatch):
    async def denied(messages):
        raise llm.LLMUnavailable("invalid x-api-key", transient=False)

    monkeypatch.setattr(llm, "_create", denied)
    s = service.start("en")
    _, mode = asyncio.run(service.message(s, "kirana store in Patna"))
    assert mode == "scripted" and s.llm_disabled and s.llm_messages == []


@pytest.mark.parametrize("text, current, expected", [
    ("नमस्ते, मेरा क्लिनिक है", "en", "hi"),
    ("We have 6 staff, one location", "hi", "en"),
    ("mera clinic Pune mein hai", "en", "en"),
    ("mera clinic Pune mein hai", "hi", "hi"),
    ("27AAPFU0939F1ZV", "hi", "hi"),
    ("CCTV WiFi", "hi", "hi"),
    ("எனக்கு கடை உள்ளது", "en", "ta"),
])
def test_detect_lang(text, current, expected):
    assert nlu.detect_lang(text, current) == expected


def test_session_language_follows_owner_both_ways():
    s = service.start("en")
    asyncio.run(service.message(s, "नमस्ते, मेरा पुणे में एक डेंटल क्लिनिक है"))
    assert s.lang == "hi"
    reply, _ = asyncio.run(service.message(s, "We have 6 staff and one location"))
    assert s.lang == "en" and not any("ऀ" <= ch <= "ॿ" for ch in reply)


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


# ------------------------------------------------------------------ fake Gemini (real SDK response types)
from google.genai import types as gtypes  # noqa: E402

from app.advisor import llm_gemini  # noqa: E402


def g_call(name, args, i):
    return gtypes.GenerateContentResponse(candidates=[gtypes.Candidate(content=gtypes.Content(role="model", parts=[
        gtypes.Part(function_call=gtypes.FunctionCall(name=name, args=args, id=f"c{i}"), thought_signature=b"sig")]))])


def g_text(t):
    return gtypes.GenerateContentResponse(candidates=[gtypes.Candidate(content=gtypes.Content(role="model", parts=[gtypes.Part(text=t)]))])


@pytest.fixture
def fake_gemini(monkeypatch):
    monkeypatch.setenv("UDYAM_ADVISOR_MODE", "llm")
    monkeypatch.setenv("UDYAM_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    script, sent = [], []

    async def fake_generate(contents, model=llm_gemini.MODEL):
        sent.append([c.model_dump(mode="json", exclude_none=True) for c in contents])
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(sent[-1]) if callable(step) else step

    monkeypatch.setattr(llm_gemini, "_generate", fake_generate)
    return script, sent


def _gemini_price(contents):
    for c in reversed(contents):
        for p in c.get("parts", []):
            fr = p.get("function_response")
            if fr and "tiers" in (fr.get("response") or {}).get("result", {}):
                return fr["response"]["result"]["tiers"][1]["monthly_total_incl_gst"]
    raise AssertionError("no recommendation")


def test_gemini_tool_loop_and_signature_round_trip(fake_gemini):
    script, sent = fake_gemini
    script += [
        g_call("update_profile", {"business_type": "Dental clinic", "city": "Kochi", "employees": 12}, 1),
        g_call("recommend_bundle", {}, 2),
        lambda c: g_text(f"Recommended plan: ₹{_gemini_price(c):,}/month incl. GST."),
    ]
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "dental clinic in kochi, 12 staff"))
    assert mode == "llm:gemini" and s.recommendation and "₹" in reply
    # the model's thought signature is sent back unchanged, and history is append-only
    assert sent[1][1]["parts"][0]["thought_signature"] == sent[2][1]["parts"][0]["thought_signature"]
    for a, b in zip(sent, sent[1:]):
        assert b[: len(a)] == a
    fr = sent[1][2]["parts"][0]["function_response"]
    assert fr["id"] == "c1" and fr["name"] == "update_profile"


def test_gemini_guard_and_tool_error(fake_gemini):
    script, sent = fake_gemini
    script += [
        g_call("recommend_bundle", {}, 1),  # fails: profile incomplete → error returned to model
        g_call("update_profile", {"business_type": "Salon", "city": "Pune", "employees": 3}, 2),
        g_call("recommend_bundle", {}, 3),
        g_text("Only ₹99/month!"),
        lambda c: g_text(f"It is ₹{_gemini_price(c):,}/month."),
    ]
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "salon pune 3 people"))
    assert "error" in sent[1][-1]["parts"][0]["function_response"]["response"]
    assert mode == "llm:gemini" and "99/month" not in reply


def test_gemini_failure_falls_back(fake_gemini, monkeypatch):
    async def boom(contents, model=None):
        raise llm_gemini.GeminiUnavailable("quota")

    monkeypatch.setattr(llm_gemini, "_generate", boom)
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "kirana store in Patna"))
    assert mode == "scripted" and not s.llm_disabled
    assert [c["role"] for c in s.gemini_contents] == ["user", "model"]


def _busy():
    from google.genai import errors as gerr
    return gerr.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})


def test_gemini_busy_model_moves_to_next_in_chain(fake_gemini, monkeypatch):
    script, sent = fake_gemini
    monkeypatch.setattr(llm_gemini, "MODEL", "model-a")
    monkeypatch.setattr(llm_gemini, "FALLBACK_MODELS", ["model-b"])
    used = []
    real = llm_gemini._generate

    async def spy(contents, model=None):
        used.append(model)
        return await real(contents, model)

    monkeypatch.setattr(llm_gemini, "_generate", spy)
    script += [
        g_call("update_profile", {"business_type": "Salon", "city": "Pune", "employees": 3}, 1),
        _busy(),  # model-a fails mid-turn → turn rolled back and replayed on model-b
        g_call("update_profile", {"business_type": "Salon", "city": "Pune", "employees": 3}, 2),
        g_text("How many locations do you have?"),
    ]
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "salon pune 3 people"))
    assert mode == "llm:gemini" and used == ["model-a", "model-a", "model-b", "model-b"]
    assert s.gemini_model == "model-b"
    # model-b's request starts the turn from scratch (no half-finished model-a turn) and
    # carries no thought signatures from model-a
    assert len(sent[2]) == 1 and "thought_signature" not in json.dumps(sent[2])
    assert llm_gemini.model_chain(s) == ["model-b", "model-a"]


def test_gemini_bad_request_is_not_retried(fake_gemini, monkeypatch):
    from google.genai import errors as gerr
    script, sent = fake_gemini
    script += [gerr.ClientError(400, {"error": {"code": 400, "message": "API key not valid", "status": "INVALID_ARGUMENT"}})]
    s = service.start("en")
    _, mode = asyncio.run(service.message(s, "salon pune 3 people"))
    assert mode == "scripted" and s.llm_disabled and len(sent) == 1


def test_llm_reply_markdown_is_flattened(fake_llm):
    script, _ = fake_llm
    script += [text("## Plan\nOur **Recommended bundle** suits you.")]
    s = service.start("en")
    reply, _ = asyncio.run(service.message(s, "hello"))
    assert reply == "Plan\nOur Recommended bundle suits you."


def test_slow_llm_turn_times_out_to_scripted(fake_llm, monkeypatch):
    async def slow(messages):
        await asyncio.sleep(5)

    monkeypatch.setattr(llm, "_create", slow)
    monkeypatch.setattr(llm, "TURN_TIMEOUT", 0.2)
    s = service.start("en")
    reply, mode = asyncio.run(service.message(s, "kirana store in Patna"))
    assert mode == "scripted" and not s.llm_disabled
    # only the completed (scripted) exchange is in the LLM history
    assert [m["role"] for m in s.llm_messages] == ["user", "assistant"]


def test_personal_ids_are_removed_before_the_llm(fake_llm):
    script, sent = fake_llm
    script += [text("Please don't share those here.")]
    s = service.start("en")
    asyncio.run(service.message(s, "GSTIN 27AAPFU0939F1ZV, my aadhaar 1234 5678 9012, PAN ABCDE1234F, a/c 123456789012345, upi ravi@okbank"))
    sent_text = json.dumps(sent[-1])
    assert "27AAPFU0939F1ZV" in sent_text  # business registration kept for lookup
    for secret in ("1234 5678 9012", "ABCDE1234F", "123456789012345", "ravi@okbank"):
        assert secret not in sent_text
