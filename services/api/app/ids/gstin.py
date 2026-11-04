"""GSTIN format and checksum validation.

Structure: 2-digit state code + 10-char PAN + entity number + 'Z' + check character.
The case data puts 'X' as the PAN's 4th character (not a real entity type) so no
synthetic GSTIN can match a real taxpayer; we accept it deliberately.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .states import GST_STATE_CODES

_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# PAN 4th char: real entity types are C,P,H,F,A,T,B,L,J,G; 'X' is allowed for the synthetic data.
_PAN_ENTITY = "CPHFATBLJGX"
_PATTERN = re.compile(r"^(\d{2})([A-Z]{3})([A-Z])([A-Z])(\d{4})([A-Z])([1-9A-Z])Z([0-9A-Z])$")
# groups: 1 state, 2 PAN chars 1-3, 3 PAN entity type, 4 PAN name initial, 5 PAN digits, 6 PAN check, 7 entity no., 8 checksum


def checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        value = _CHARS.index(ch) * (2 if i % 2 else 1)
        total += value // 36 + value % 36
    return _CHARS[(36 - total % 36) % 36]


@dataclass
class GstinCheck:
    gstin: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    state_code: str | None = None
    state: str | None = None
    pan: str | None = None


def normalise(gstin: str) -> str:
    return re.sub(r"\s+", "", gstin or "").upper()


def validate(gstin: str) -> GstinCheck:
    g = normalise(gstin)
    result = GstinCheck(gstin=g, valid=False)
    if len(g) != 15:
        result.errors.append(f"GSTIN must be 15 characters, got {len(g)}")
        return result
    m = _PATTERN.match(g)
    if not m:
        result.errors.append("GSTIN does not follow the 15-character format (e.g. 27ABCXE1234F1Z5)")
        return result
    state_code = m.group(1)
    result.state_code = state_code
    result.state = GST_STATE_CODES.get(state_code)
    result.pan = g[2:12]
    if result.state is None:
        result.errors.append(f"Unknown GST state code {state_code}")
    # PAN = characters 3-12; its 4th character is the entity type (regex group 3).
    if m.group(3) not in _PAN_ENTITY:
        result.errors.append(f"PAN entity type '{m.group(3)}' is not valid")
    expected = checksum_char(g[:14])
    if g[14] != expected:
        result.errors.append("Check character does not match; the GSTIN may be mistyped")
    result.valid = not result.errors
    return result


def mask(gstin: str | None) -> str | None:
    """Show state code + first 3 PAN letters + last 3 characters: 27ABC•••••••1Z5."""
    if not gstin:
        return gstin
    g = normalise(gstin)
    if len(g) < 8:
        return "•" * len(g)
    return g[:5] + "•" * (len(g) - 8) + g[-3:]
