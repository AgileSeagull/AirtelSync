"""Advisor orchestration: picks LLM or scripted mode and falls back automatically."""
from __future__ import annotations

import logging

from . import llm, profile_slots, scripted
from .session import LANGS, AdvisorSession, Turn

log = logging.getLogger("advisor")


def start(lang: str = "en", channel: str = "web", prefill: dict | None = None) -> AdvisorSession:
    s = AdvisorSession(lang=lang if lang in LANGS else "en", channel=channel)
    if prefill:
        s.profile, _ = profile_slots.merge({}, prefill)
    greeting = scripted.greeting(s)
    s.transcript.append(Turn(role="assistant", text=greeting, mode="system"))
    s.save()
    return s


async def message(s: AdvisorSession, text: str) -> tuple[str, str]:
    text = (text or "").strip()[:2000]
    s.transcript.append(Turn(role="user", text=text))
    mode = "scripted"
    reply = None
    if llm.available() and not s.llm_disabled:
        try:
            reply = await llm.respond(s, text)
            mode = "llm"
        except llm.LLMUnavailable as e:
            log.warning("LLM unavailable for session %s, continuing scripted: %s", s.id, e)
            s.llm_disabled = True
    if reply is None:
        reply = scripted.respond(s, text)
    s.transcript.append(Turn(role="assistant", text=reply, mode=mode))
    s.save()
    return reply, mode


def view(s: AdvisorSession) -> dict:
    return {
        "session_id": s.id,
        "lang": s.lang,
        "status": s.status,
        "profile": profile_slots.public_view(s.profile),
        "missing": profile_slots.missing(s.profile),
        "recommendation": s.recommendation,
        "handoff": s.handoff,
        "transcript": [t.model_dump() for t in s.transcript],
        "llm_enabled": llm.available() and not s.llm_disabled,
    }
