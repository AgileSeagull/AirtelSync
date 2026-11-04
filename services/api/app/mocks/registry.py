"""Mock GSTIN and Udyam lookup APIs backed by the case CSVs.

They behave like a government API would: format errors → 422, unknown → 404,
found → the registry record including status (Active / Cancelled / Suspended).
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException

from ..data_store import gstin_registry, udyam_registry
from ..ids import gstin as gstin_ids
from ..ids import udyam as udyam_ids

router = APIRouter(prefix="/mock", tags=["mock government APIs"])


def lookup_gstin(gstin: str) -> dict:
    check = gstin_ids.validate(gstin)
    if not check.valid:
        raise HTTPException(422, detail={"code": "INVALID_FORMAT", "errors": check.errors})
    rec = gstin_registry().get(check.gstin)
    if rec is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "errors": ["No GST registration found for this GSTIN"]})
    return {**rec, "city": city_from_address(rec["principal_place_of_business"]),
            "pincode": pincode_from_address(rec["principal_place_of_business"])}


def lookup_udyam(number: str) -> dict:
    check = udyam_ids.validate(number)
    if not check.valid:
        raise HTTPException(422, detail={"code": "INVALID_FORMAT", "errors": check.errors})
    rec = udyam_registry().get(check.number)
    if rec is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "errors": ["No Udyam registration found for this number"]})
    return rec


def city_from_address(address: str) -> str | None:
    # "Shop/Unit 164, Station Road, Kochi, Kerala - 289398" → "Kochi"
    parts = [p.strip() for p in re.sub(r"-\s*\d{6}\s*$", "", address).split(",")]
    return parts[-2] if len(parts) >= 3 else None


def pincode_from_address(address: str) -> str | None:
    m = re.search(r"(\d{6})\s*$", address)
    return m.group(1) if m else None


@router.get("/gstin/{gstin}")
def gstin_endpoint(gstin: str) -> dict:
    return lookup_gstin(gstin)


@router.get("/udyam/{number}")
def udyam_endpoint(number: str) -> dict:
    return lookup_udyam(number)
