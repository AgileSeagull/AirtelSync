"""Advisor orchestration: picks LLM or scripted mode and falls back automatically."""
from __future__ import annotations

import logging
import re

from . import llm, profile_slots, scripted
from .nlu import detect_lang
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
    # The app's language follows the owner: cards, buttons and voice input switch with them.
    new_lang = detect_lang(text, s.lang)
    s.lang_switched, s.lang = new_lang != s.lang, new_lang
    mode = "scripted"
    reply = None
    use_llm = llm.available() and not s.llm_disabled
    if use_llm:
        try:
            reply = _plain(await llm.respond(s, redact_for_llm(text)))
            mode = f"llm:{llm.provider()}"
        except llm.LLMUnavailable as e:
            # A busy or rate-limited model only costs this one turn; a bad key ends LLM use.
            log.warning("LLM unavailable for session %s (transient=%s), answering this turn scripted: %s",
                        s.id, e.transient, e)
            if not e.transient:
                s.llm_disabled = True
    if reply is None:
        reply = scripted.respond(s, text)
        if use_llm and not s.llm_disabled:
            llm.record_scripted_turn(s, text, reply)
    s.transcript.append(Turn(role="assistant", text=reply, mode=mode))
    s.save()
    return reply, mode


_AADHAAR = re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)")
_PAN = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{9,18}(?!\d)")  # bank accounts, phone numbers
_UPI = re.compile(r"\b[\w.\-]{2,}@[a-zA-Z]{2,}\b")


def redact_for_llm(text: str) -> str:
    """Personal identifiers never leave for the LLM provider. GSTIN (a public business
    registration the advisor needs for lookup) is kept; Aadhaar, PAN, account or phone
    numbers and UPI IDs are replaced, and the model is told what was removed."""
    text = _AADHAAR.sub("[Aadhaar-like number removed]", text)
    text = _PAN.sub("[PAN removed]", text)
    text = _LONG_DIGITS.sub("[number removed]", text)
    return _UPI.sub("[UPI ID removed]", text)


def _plain(text: str) -> str:
    """The chat shows plain text: drop markdown emphasis and heading markers models sometimes add."""
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    return re.sub(r"(?m)^#{1,6}\s+", "", text)


def view(s: AdvisorSession) -> dict:
    return {
        "session_id": s.id,
        "lang": s.lang,
        "status": s.status,
        "last_asked": s.last_asked,
        "profile": profile_slots.public_view(s.profile),
        "missing": profile_slots.missing(s.profile),
        "recommendation": s.recommendation,
        "handoff": s.handoff,
        "transcript": [t.model_dump() for t in s.transcript],
        "llm_enabled": llm.available() and not s.llm_disabled,
    }
