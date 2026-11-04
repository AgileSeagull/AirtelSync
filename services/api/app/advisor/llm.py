"""Claude-powered advisor: a manual tool-use loop so we control state, the guard and fallbacks."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import anthropic

from . import guard
from .prompts import SYSTEM_PROMPT, turn_notes
from .session import LANGS, AdvisorSession
from .tools import TOOL_DEFS, ToolError, run_tool

log = logging.getLogger("advisor.llm")

MODEL = os.getenv("UDYAM_LLM_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("UDYAM_LLM_EFFORT", "low")  # chat turns: keep latency low
MAX_TOOL_ROUNDS = 6
TURN_TIMEOUT = float(os.getenv("UDYAM_LLM_TURN_TIMEOUT", "35"))  # then the scripted advisor answers this turn

_client: anthropic.AsyncAnthropic | None = None


def provider() -> str | None:
    """Which LLM backs the advisor: UDYAM_LLM_PROVIDER if set, else whichever key is present
    (Gemini first). None means scripted mode."""
    if os.getenv("UDYAM_ADVISOR_MODE", "").lower() == "scripted":
        return None
    wanted = os.getenv("UDYAM_LLM_PROVIDER", "").lower()
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_claude = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    if wanted == "gemini":
        return "gemini" if has_gemini else None
    if wanted in ("anthropic", "claude"):
        return "anthropic" if has_claude else None
    return "gemini" if has_gemini else ("anthropic" if has_claude else None)


def available() -> bool:
    return provider() is not None


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(timeout=60.0, max_retries=2)
    return _client


class LLMUnavailable(Exception):
    def __init__(self, msg: str, transient: bool = True):
        super().__init__(msg)
        self.transient = transient  # False: bad key / bad request; stop trying for this session


def _system_blocks() -> list[dict]:
    return [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]


async def _create(messages: list[dict]) -> Any:
    return await client().beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=_system_blocks(),
        tools=TOOL_DEFS,
        messages=messages,
        output_config={"effort": EFFORT},
        # Server-side fallback: if the model declines (refusal), the API retries on a suitable model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )


def _dump(content) -> list[dict]:
    return [b.model_dump(mode="json", exclude_none=True) for b in content]


async def respond(session: AdvisorSession, user_text: str) -> str:
    """One owner turn on the configured LLM, within TURN_TIMEOUT seconds. On any failure the
    turn is removed from the stored history, so it only ever holds completed turns."""
    hist = session.gemini_contents if provider() == "gemini" else session.llm_messages
    turn_start = len(hist)
    try:
        return await asyncio.wait_for(_respond(session, user_text), TURN_TIMEOUT)
    except TimeoutError as e:
        del hist[turn_start:]
        raise LLMUnavailable(f"no reply within {TURN_TIMEOUT:.0f}s") from e
    except LLMUnavailable:
        del hist[turn_start:]
        raise


async def _respond(session: AdvisorSession, user_text: str) -> str:
    if provider() == "gemini":
        from . import llm_gemini
        try:
            return await llm_gemini.respond(session, user_text)
        except llm_gemini.GeminiUnavailable as e:
            raise LLMUnavailable(str(e), transient=e.transient) from e
    return await respond_claude(session, user_text)


def record_scripted_turn(session: AdvisorSession, user_text: str, reply: str) -> None:
    """When a turn was answered by the scripted advisor, add it to the LLM history so the model
    has the full conversation when it answers the next turn."""
    lang = LANGS.get(session.lang, "English")
    if provider() == "gemini":
        hist = session.gemini_contents
        notes = turn_notes(lang, first=not hist, switched=session.lang_switched)
        hist.append({"role": "user", "parts": [{"text": n} for n in notes] + [{"text": user_text}]})
        hist.append({"role": "model", "parts": [{"text": reply}]})
    elif provider() == "anthropic":
        msgs = session.llm_messages
        notes = turn_notes(lang, first=not msgs, switched=session.lang_switched)
        msgs.append({"role": "user", "content": [{"type": "text", "text": n} for n in notes] + [{"type": "text", "text": user_text}]})
        msgs.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})


async def respond_claude(session: AdvisorSession, user_text: str) -> str:
    """Run one owner turn on Claude. History is append-only (thinking blocks stay valid)."""
    msgs = session.llm_messages
    notes = turn_notes(LANGS.get(session.lang, "English"), first=not msgs, switched=session.lang_switched)
    if notes:
        msgs.append({"role": "user", "content": [{"type": "text", "text": n} for n in notes] + [{"type": "text", "text": user_text}]})
    else:
        msgs.append({"role": "user", "content": user_text})

    tool_results: list[Any] = []
    guard_retry_used = False
    for _ in range(MAX_TOOL_ROUNDS + 2):
        try:
            resp = await _create(msgs)
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
            raise LLMUnavailable(str(e)) from e
        except anthropic.APIStatusError as e:
            log.error("advisor API error %s request_id=%s", e.status_code, getattr(e, "request_id", None))
            raise LLMUnavailable(str(e), transient=e.status_code in (408, 409, 429) or e.status_code >= 500) from e

        msgs.append({"role": "assistant", "content": _dump(resp.content)})
        if resp.stop_reason == "refusal":
            raise LLMUnavailable("model declined")
        if resp.stop_reason == "pause_turn":
            continue
        uses = [b for b in resp.content if b.type == "tool_use"]
        if uses:
            results = []
            for b in uses:
                try:
                    out = run_tool(session, b.name, b.input if isinstance(b.input, dict) else {})
                    tool_results.append(out)
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, ensure_ascii=False)})
                except ToolError as e:
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": f"Error: {e}", "is_error": True})
            msgs.append({"role": "user", "content": results})
            continue

        text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
        # Guard against any number/product not grounded in this conversation's tool results.
        history_results = _all_tool_results(msgs)
        nums, pids = guard.allowed_from(history_results)
        problems = guard.check(text, nums, pids)
        if problems and not guard_retry_used:
            guard_retry_used = True
            log.warning("guard rejected draft: %s", problems)
            # A system message cannot follow an assistant turn, so the correction goes in as an
            # automated (non-owner) user note; history stays append-only.
            msgs.append({"role": "user", "content": "[Automated check, not from the owner] Your last reply mentioned values "
                         "that do not appear in any tool result (" + "; ".join(problems) + "). Rewrite the reply using only "
                         "numbers and products returned by tools; call recommend_bundle or check_product if you need them."})
            continue
        if problems:
            raise LLMUnavailable("guard failed twice: " + "; ".join(problems))
        return text
    raise LLMUnavailable("too many tool rounds")


def _all_tool_results(msgs: list[dict]) -> list[Any]:
    out = []
    for m in msgs:
        if m["role"] == "user" and isinstance(m["content"], list):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result" and not b.get("is_error"):
                    try:
                        out.append(json.loads(b["content"]))
                    except (TypeError, ValueError):
                        pass
    return out
