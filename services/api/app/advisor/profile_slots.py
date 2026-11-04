"""Merging partial profile updates and deciding what is still missing."""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..engine.models import NEEDS, Profile
from ..engine.reference import resolve_city, segment_for
from ..ids import gstin as gstin_ids

REQUIRED = ["business_type", "city", "employees"]
INT_FIELDS = ["employees", "sites", "monthly_telecom_spend", "mobile_users", "desk_users", "cameras", "counters",
              "machines", "vehicles"]
STR_FIELDS = ["business_type", "city", "current_internet"]


def merge(profile: dict[str, Any], updates: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply validated updates. Returns (profile, list of rejected-field messages)."""
    p = dict(profile)
    errors: list[str] = []
    for k in STR_FIELDS:
        v = updates.get(k)
        if isinstance(v, str) and v.strip():
            p[k] = v.strip()
    for k in INT_FIELDS:
        v = updates.get(k)
        if v is None:
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            errors.append(f"{k} must be a whole number")
            continue
        if iv < (1 if k in ("employees", "sites") else 0) or iv > 100000:
            errors.append(f"{k}={iv} is out of range")
            continue
        p[k] = iv
    if "has_gstin" in updates and isinstance(updates["has_gstin"], bool):
        p["has_gstin"] = updates["has_gstin"]
        if not updates["has_gstin"]:
            p.pop("gstin", None)
            p.pop("gstin_status", None)
    if "fibre_feasible" in updates and isinstance(updates["fibre_feasible"], bool):
        p["fibre_feasible"] = updates["fibre_feasible"]
    if isinstance(updates.get("needs"), list):
        unknown = [n for n in updates["needs"] if n not in NEEDS]
        if unknown:
            errors.append("unknown needs ignored: " + ", ".join(map(str, unknown)))
        known = [n for n in updates["needs"] if n in NEEDS]
        p["needs"] = sorted(set(p.get("needs", [])) | set(known))
    if isinstance(updates.get("remove_needs"), list):
        p["needs"] = [n for n in p.get("needs", []) if n not in updates["remove_needs"]]
    if "city" in updates and p.get("city"):
        c = resolve_city(p["city"])
        if c:
            p["city"], p["city_tier"] = c["city"], c["tier"]
            if c["state"]:
                p["state"] = c["state"]
    if p.get("business_type"):
        p["segment"] = segment_for(p["business_type"], p.get("sites", 1), p.get("employees", 1))
    return p, errors


def missing(profile: dict[str, Any]) -> list[str]:
    return [k for k in REQUIRED if not profile.get(k)]


def to_profile(profile: dict[str, Any]) -> Profile:
    data = {k: v for k, v in profile.items() if k in Profile.model_fields}
    data.setdefault("employees", 1)
    try:
        return Profile(**data)
    except ValidationError:
        # Drop anything invalid rather than failing the conversation.
        clean = {}
        for k, v in data.items():
            try:
                Profile(**{**clean, k: v, "business_type": data.get("business_type", "Shop")})
                clean[k] = v
            except ValidationError:
                pass
        return Profile(**{"business_type": "Shop", **clean})


def public_view(profile: dict[str, Any]) -> dict[str, Any]:
    """Profile as shown in the UI/console: identifiers masked."""
    out = dict(profile)
    if out.get("gstin"):
        out["gstin"] = gstin_ids.mask(out["gstin"])
    return out
