"""HTTP surface for the recommendation and quote engine."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..data_store import catalogue
from ..mocks.registry import lookup_gstin
from .eligibility import validate_bundle
from .models import NEEDS, SEGMENT_LABELS, ContractChoice, LineItem, Product, Profile, Quote, Recommendation, Violation
from .pricing import enrich, quote
from .recommend import recommend
from .reference import cities, resolve_city, segment_for

router = APIRouter(tags=["engine"])


class QuoteRequest(BaseModel):
    profile: Profile
    items: list[LineItem]
    contract: ContractChoice = "12"


class ValidateRequest(BaseModel):
    profile: Profile
    items: list[LineItem]


@router.get("/catalogue", response_model=list[Product])
def get_catalogue() -> list[Product]:
    return list(catalogue().values())


@router.get("/reference")
def reference() -> dict:
    return {
        "needs": NEEDS,
        "segments": SEGMENT_LABELS,
        "cities": {c: {"tier": t, "state": s} for c, (t, s) in sorted(cities().items())},
    }


@router.get("/reference/city")
def city(name: str) -> dict:
    return resolve_city(name) or {}


@router.get("/reference/segment")
def segment(business_type: str, sites: int = 1, employees: int = 1) -> dict:
    s = segment_for(business_type, sites, employees)
    return {"segment": s, "label": SEGMENT_LABELS[s]}


@router.post("/engine/recommend", response_model=Recommendation)
def post_recommend(profile: Profile) -> Recommendation:
    return recommend(profile)


@router.post("/engine/quote", response_model=Quote)
def post_quote(req: QuoteRequest) -> Quote:
    if not req.items:
        raise HTTPException(422, "Add at least one product to get a quote")
    return quote(req.profile, req.items, req.contract)


@router.post("/engine/validate", response_model=list[Violation])
def post_validate(req: ValidateRequest) -> list[Violation]:
    return validate_bundle(enrich(req.profile), req.items)


@router.get("/profile/from-gstin/{gstin}")
def profile_from_gstin(gstin: str) -> dict:
    """Pre-fill the advisor profile from the GST registry (fewer questions, no typos)."""
    rec = lookup_gstin(gstin)
    c = resolve_city(rec.get("city"))
    return {
        "gstin": rec["gstin"],
        "gstin_status": rec["status"],
        "legal_name": rec["legal_name"],
        "trade_name": rec["trade_name"],
        "constitution": rec["constitution"],
        "state": rec["state"],
        "city": c["city"] if c else rec.get("city"),
        "city_tier": c["tier"] if c else None,
        "registration_date": rec["registration_date"],
    }
