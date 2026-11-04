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
from .prompts import LANG_NOTE, SYSTEM_PROMPT
from .session import LANGS, AdvisorSession
from .tools import TOOL_DEFS, ToolError, run_tool

log = logging.getLogger("advisor.gemini")

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
MAX_ROUNDS = 8

_client: genai.Client | None = None


class GeminiUnavailable(Exception):
    pass


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _config() -> types.GenerateContentConfig:
    decls = [types.FunctionDeclaration(name=t["name"], description=t["description"], parameters_json_schema=t["input_schema"])
             for t in TOOL_DEFS]
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=decls)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


async def _generate(contents: list[types.Content]) -> types.GenerateContentResponse:
    return await client().aio.models.generate_content(model=MODEL, contents=contents, config=_config())


def _tool_results(contents: list[dict]) -> list[Any]:
    out = []
    for c in contents:
        for p in c.get("parts", []):
            fr = p.get("function_response")
            if fr and not (fr.get("response") or {}).get("error"):
                out.append(fr.get("response"))
    return out


async def respond(session: AdvisorSession, user_text: str) -> str:
    hist = session.gemini_contents
    if not hist:
        note = LANG_NOTE.format(lang=LANGS.get(session.lang, "English"))
        hist.append({"role": "user", "parts": [{"text": f"[{note}]"}, {"text": user_text}]})
    else:
        hist.append({"role": "user", "parts": [{"text": user_text}]})

    guard_retry_used = False
    for _ in range(MAX_ROUNDS):
        try:
            resp = await _generate([types.Content.model_validate(c) for c in hist])
        except (genai_errors.APIError, httpx.HTTPError) as e:
            log.error("Gemini error: %s", e)
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
