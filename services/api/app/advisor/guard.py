"""Output guard: the advisor may only state prices and product ids that came from a tool
result in this conversation. Catches hallucinated numbers before the owner sees them."""
from __future__ import annotations

import json
import re

_DEV = str.maketrans("०१२३४५६७८९", "0123456789")
# A rupee amount: ₹/Rs/INR/रु before the number, or rupees/₹/month words after it.
_MONEY = re.compile(
    r"(?:₹|rs\.?|inr|रु\.?|रुपये)\s*([\d][\d,]*(?:\.\d+)?)"
    r"|([\d][\d,]*(?:\.\d+)?)\s*(?:rupees|रुपये|रुपए|/-|\s*(?:per|a|/)\s*month)",
    re.IGNORECASE,
)
_PID = re.compile(r"\bP(0[1-9]|1\d|2[0-5])\b")


def _numbers_in(obj) -> set[int]:
    nums: set[int] = set()
    text = json.dumps(obj, ensure_ascii=False)
    for m in re.finditer(r"-?\d+(?:\.\d+)?", text):
        try:
            v = abs(float(m.group()))
        except ValueError:
            continue
        nums.add(int(round(v)))
    return nums


def allowed_from(tool_results: list) -> tuple[set[int], set[str]]:
    nums: set[int] = set()
    pids: set[str] = set()
    for r in tool_results:
        nums |= _numbers_in(r)
        pids |= {"P" + m for m in _PID.findall(json.dumps(r))}
    return nums, pids


def check(reply: str, allowed_numbers: set[int], allowed_pids: set[str]) -> list[str]:
    problems = []
    text = reply.translate(_DEV)
    for m in _MONEY.finditer(text):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        if not raw:
            continue
        v = int(round(float(raw)))
        if v not in allowed_numbers:
            problems.append(f"amount ₹{raw} does not come from a tool result")
    for m in _PID.finditer(text):
        if "P" + m.group(1) not in allowed_pids:
            problems.append(f"product P{m.group(1)} was not returned by a tool")
    return problems
