"""Udyam Registration Number validation: UDYAM-<state>-<district>-<7 digits>.

The synthetic data always uses district code 00 (which does not exist in reality).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .states import UDYAM_STATE_CODES

_PATTERN = re.compile(r"^UDYAM-([A-Z]{2})-(\d{2})-(\d{7})$")


@dataclass
class UdyamCheck:
    number: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    state: str | None = None


def normalise(number: str) -> str:
    return re.sub(r"\s+", "", number or "").upper()


def validate(number: str) -> UdyamCheck:
    n = normalise(number)
    result = UdyamCheck(number=n, valid=False)
    m = _PATTERN.match(n)
    if not m:
        result.errors.append("Udyam number must look like UDYAM-MH-00-1234567")
        return result
    result.state = UDYAM_STATE_CODES.get(m.group(1))
    if result.state is None:
        result.errors.append(f"Unknown state code {m.group(1)} in Udyam number")
    result.valid = not result.errors
    return result


def mask(number: str | None) -> str | None:
    if not number:
        return number
    n = normalise(number)
    return n[:9] + "•••" + n[-4:] if len(n) > 13 else "•" * len(n)
