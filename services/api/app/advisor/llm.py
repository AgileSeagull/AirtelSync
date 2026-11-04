"""Claude-powered advisor: a manual tool-use loop so we control state, the guard and fallbacks."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

from . import guard
from .prompts import LANG_NOTE, SYSTEM_PROMPT
from .session import LANGS, AdvisorSession
from .tools import TOOL_DEFS, ToolError, run_tool

log = logging.getLogger("advisor.llm")

MODEL = os.getenv("UDYAM_LLM_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("UDYAM_LLM_EFFORT", "low")  # chat turns: keep latency low
MAX_TOOL_ROUNDS = 6

_client: anthropic.AsyncAnthropic | None = None


def available() -> bool:
    if os.getenv("UDYAM_ADVISOR_MODE", "").lower() == "scripted":
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(timeout=60.0, max_retries=2)
    return _client


class LLMUnavailable(Exception):
    pass


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
    """Run one owner turn. History is append-only (thinking blocks stay valid)."""
    msgs = session.llm_messages
    if not msgs:
        msgs.append({"role": "user", "content": [{"type": "text", "text": f"[{LANG_NOTE.format(lang=LANGS.get(session.lang, 'English'))}]"},
                                                 {"type": "text", "text": user_text}]})
    else:
        msgs.append({"role": "user", "content": user_text})

    tool_results: list[Any] = []
    guard_retry_used = False
    for _ in range(MAX_TOOL_ROUNDS + 2):
        try:
            resp = await _create(msgs)
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError,
                anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise LLMUnavailable(str(e)) from e
        except anthropic.APIStatusError as e:
            log.error("advisor API error %s request_id=%s", e.status_code, getattr(e, "request_id", None))
            raise LLMUnavailable(str(e)) from e

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
