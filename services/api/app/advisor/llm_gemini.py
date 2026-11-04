"""Gemini-powered advisor (google-genai SDK). Same tools, prompt and output guard as the
Claude path; manual function-calling loop so we keep control of state and fallbacks."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from . import guard
from .prompts import SYSTEM_PROMPT, turn_notes
from .session import LANGS, AdvisorSession
from .tools import TOOL_DEFS, ToolError, run_tool

log = logging.getLogger("advisor.gemini")

# gemini-2.5-flash is the default: fast and rarely overloaded. When a model is busy (503/429)
# the turn moves to the next one in the chain.
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-flash-lite-latest,gemini-flash-latest").split(",") if m.strip()]
MAX_ROUNDS = 8
TRANSIENT_CODES = {408, 429, 500, 502, 503, 504}

_client: genai.Client | None = None


class GeminiUnavailable(Exception):
    def __init__(self, msg: str, transient: bool = True):
        super().__init__(msg)
        self.transient = transient  # False: bad key / bad request, no point retrying this session


def client() -> genai.Client:
    global _client
    if _client is None:
        retry = types.HttpRetryOptions(attempts=2, initial_delay=0.8, max_delay=4, http_status_codes=sorted(TRANSIENT_CODES))
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                               http_options=types.HttpOptions(timeout=20_000, retry_options=retry))
    return _client


def model_chain(session: AdvisorSession) -> list[str]:
    chain = [MODEL] + [m for m in FALLBACK_MODELS if m != MODEL]
    if session.gemini_model in chain:  # stay on the model that last answered this session
        chain.remove(session.gemini_model)
        chain.insert(0, session.gemini_model)
    return chain


def _strip_signatures(contents: list[dict]) -> list[dict]:
    """Thought signatures are only valid for the model that made them; drop them (and thought
    text) when a different model continues the conversation. Gemini only validates signatures
    on the current turn's calls, which the new model produces itself."""
    out = []
    for c in contents:
        parts = [{k: v for k, v in p.items() if k != "thought_signature"} for p in c.get("parts", []) if not p.get("thought")]
        if parts:
            out.append({**c, "parts": parts})
    return out


def _config() -> types.GenerateContentConfig:
    decls = [types.FunctionDeclaration(name=t["name"], description=t["description"], parameters_json_schema=t["input_schema"])
             for t in TOOL_DEFS]
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=decls)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


async def _generate(contents: list[types.Content], model: str = MODEL) -> types.GenerateContentResponse:
    return await client().aio.models.generate_content(model=model, contents=contents, config=_config())


def _tool_results(contents: list[dict]) -> list[Any]:
    out = []
    for c in contents:
        for p in c.get("parts", []):
            fr = p.get("function_response")
            if fr and not (fr.get("response") or {}).get("error"):
                out.append(fr.get("response"))
    return out


async def respond(session: AdvisorSession, user_text: str) -> str:
    """One owner turn. Tries each model in the chain; a failed attempt is rolled back so the
    stored history only ever holds completed turns."""
    hist = session.gemini_contents
    turn_start = len(hist)
    errors = []
    for model in model_chain(session):
        if session.gemini_model and model != session.gemini_model:
            hist[:turn_start] = _strip_signatures(hist[:turn_start])
        notes = turn_notes(LANGS.get(session.lang, "English"), first=not hist, switched=session.lang_switched)
        hist.append({"role": "user", "parts": [{"text": n} for n in notes] + [{"text": user_text}]})
        try:
            text = await _run_turn(session, hist, model)
            session.gemini_model = model
            return text
        except GeminiUnavailable as e:
            del hist[turn_start:]
            errors.append(f"{model}: {e}")
            if not e.transient:
                raise
            log.warning("Gemini %s unavailable, trying next model: %s", model, e)
    raise GeminiUnavailable(" | ".join(errors))


async def _run_turn(session: AdvisorSession, hist: list[dict], model: str) -> str:
    guard_retry_used = False
    for _ in range(MAX_ROUNDS):
        try:
            resp = await _generate([types.Content.model_validate(c) for c in hist], model)
        except genai_errors.APIError as e:
            log.error("Gemini %s error: %s", model, e)
            raise GeminiUnavailable(str(e), transient=e.code in TRANSIENT_CODES) from e
        except httpx.HTTPError as e:
            raise GeminiUnavailable(str(e)) from e
        cand = (resp.candidates or [None])[0]
        if cand is None or cand.content is None:
            raise GeminiUnavailable(f"no candidate (finish={getattr(cand, 'finish_reason', None)}, feedback={resp.prompt_feedback})")
        hist.append(cand.content.model_dump(mode="json", exclude_none=True))
        calls = resp.function_calls or []
        if calls:
            parts = []
            for fc in calls:
                try:
                    out = run_tool(session, fc.name, dict(fc.args or {}))
                    payload = {"result": out}
                except ToolError as e:
                    payload = {"error": str(e)}
                part = types.Part.from_function_response(name=fc.name, response=json.loads(json.dumps(payload, ensure_ascii=False)))
                if fc.id:
                    part.function_response.id = fc.id
                parts.append(part.model_dump(mode="json", exclude_none=True))
            hist.append({"role": "user", "parts": parts})
            continue

        text = "".join(p.text for p in (cand.content.parts or []) if p.text and not p.thought).strip()
        if not text:
            raise GeminiUnavailable("empty reply")
        results = [r.get("result", r) for r in _tool_results(hist)]
        nums, pids = guard.allowed_from(results)
        problems = guard.check(text, nums, pids)
        if problems and not guard_retry_used:
            guard_retry_used = True
            log.warning("guard rejected draft: %s", problems)
            hist.append({"role": "user", "parts": [{"text": "[Automated check, not from the owner] Your last reply mentioned values "
                         "that do not appear in any tool result (" + "; ".join(problems) + "). Rewrite the reply using only "
                         "numbers and products returned by tools; call recommend_bundle or check_product if you need them."}]})
            continue
        if problems:
            raise GeminiUnavailable("guard failed twice: " + "; ".join(problems))
        return text
    raise GeminiUnavailable("too many tool rounds")
