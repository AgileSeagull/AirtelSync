"""Repairing OCR'd GSTIN / Udyam numbers using their structure, the checksum and the registry."""
from __future__ import annotations

import itertools
import re

from rapidfuzz.distance import Levenshtein

from ..data_store import gstin_registry, udyam_registry
from ..ids import gstin as gstin_ids
from ..ids import udyam as udyam_ids

# Position classes in a GSTIN: D=digit, L=letter, A=alphanumeric, Z=literal Z
_GSTIN_CLASSES = "DDLLLLLDDDDLAZA"
_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "T": "7", "/": "7", "A": "4"}
_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "7": "T", "4": "A"}


def _coerce(s: str) -> str | None:
    out = []
    for ch, cls in zip(s, _GSTIN_CLASSES):
        if cls == "D":
            ch = _TO_DIGIT.get(ch, ch)
            if not ch.isdigit():
                return None
        elif cls == "L":
            ch = _TO_LETTER.get(ch, ch)
            if not ch.isalpha():
                return None
        elif cls == "Z":
            if ch in ("2", "7"):
                ch = "Z"
            if ch != "Z":
                return None
        out.append(ch)
    return "".join(out)


def repair_gstin(raw: str | None, hint_names: list[str] | None = None) -> tuple[str | None, str]:
    """Returns (gstin, how) where how is 'exact', 'checksum', 'registry' or 'unreadable'."""
    if not raw:
        return None, "unreadable"
    s = re.sub(r"[^0-9A-Z/|]", "", raw.upper())
    if gstin_ids.validate(s).valid:
        return s, "exact"
    candidates: set[str] = set()
    extra = len(s) - 15
    if 0 <= extra <= 3:
        for drop in itertools.combinations(range(len(s)), extra):
            t = "".join(c for i, c in enumerate(s) if i not in drop)
            c = _coerce(t)
            if c and gstin_ids.validate(c).valid:
                candidates.add(c)
    reg = gstin_registry()
    in_reg = [c for c in candidates if c in reg]
    if len(in_reg) == 1:
        return in_reg[0], "checksum"
    # A checksum-valid string that is not registered may be a collision: prefer the nearest
    # registered GSTIN, accepted only when the business name on the document agrees.
    target = (_coerce(s[:15]) or s[:15]) if len(s) >= 15 else s
    best = sorted(reg, key=lambda g: Levenshtein.distance(g, target))[:5]
    for g in best:
        if Levenshtein.distance(g, target) <= 3 and hint_names:
            names = (reg[g]["legal_name"] + " " + reg[g]["trade_name"]).lower()
            if any(h and h.lower()[:12] in names for h in hint_names):
                return g, "registry"
    if len(candidates) == 1:
        return next(iter(candidates)), "checksum"  # will fail the registry check and go to review
    return None, "unreadable"


def repair_udyam(raw: str | None) -> str | None:
    if not raw:
        return None
    s = raw.upper().replace("@", "0").replace(" ", "")
    m = re.search(r"UDYAM-?([A-Z]{2})-?([0-9O]{2})-?([0-9O]{7})", s)
    if not m:
        return None
    n = f"UDYAM-{m.group(1)}-{m.group(2).replace('O', '0')}-{m.group(3).replace('O', '0')}"
    return n if udyam_ids.validate(n).valid else None


def find_udyam(name: str | None, city: str | None) -> dict | None:
    """Registry search used when the Udyam certificate is missing or blank."""
    if not name:
        return None
    from rapidfuzz import fuzz
    best, score = None, 0
    for rec in udyam_registry().values():
        if city and rec["city"].lower() != city.lower():
            continue
        s = fuzz.token_sort_ratio(rec["enterprise_name"].lower(), name.lower())
        if s > score:
            best, score = rec, s
    return best if score >= 95 else None
