"""Smart KYC HTTP API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..ids import gstin as gstin_ids
from ..orders.models import Order, OrderEvent
from . import consent, pipeline
from .models import KycCase
from .parse import DOC_TYPES

router = APIRouter(prefix="/kyc", tags=["kyc"])


class CreateCase(BaseModel):
    order_id: str | None = None
    lang: str = "en"


class ConsentReq(BaseModel):
    purposes: list[str] = Field(default_factory=lambda: ["kyc_verification"])
    lang: str = "en"


class DigiLockerReq(BaseModel):
    gstin: str | None = None


class OtpReq(BaseModel):
    otp: str


def _case(cid: str) -> KycCase:
    c = KycCase.load(cid)
    if c is None:
        raise HTTPException(404, "KYC case not found")
    return c


def _mask_fields(doc_type: str, fields: dict[str, Any]) -> dict[str, Any]:
    out = dict(fields)
    for k in ("gstin", "gstin_resolved"):
        if out.get(k):
            out[k] = gstin_ids.mask(out[k])
    for k in ("id_number", "consumer_no"):
        if out.get(k):
            v = str(out[k])
            out[k] = "•" * max(0, len(v) - 4) + v[-4:]
    return out


def view(c: KycCase) -> dict:
    return {
        "id": c.id, "order_id": c.order_id, "lang": c.lang, "consent_id": c.consent_id, "verdict": c.verdict,
        "verified_at": c.verified_at, "esigned_at": c.esigned_at,
        "documents": {t: {"id": d.id, "doc_type": t, "label": DOC_TYPES[t], "source": d.source, "filename": d.filename,
                          "quality": d.quality, "fields": _mask_fields(t, d.fields),
                          "raw_deleted": d.raw_deleted_at is not None or d.vault_ref is None}
                      for t, d in c.documents.items()},
        "required": list(DOC_TYPES),
        "checks": [ch.model_dump() for ch in c.checks],
        "demo_otp": pipeline.DEMO_OTP,
    }


@router.get("/notice")
def get_notice(lang: str = "en") -> dict:
    return consent.notice(lang)


@router.post("/cases")
def create_case(req: CreateCase) -> dict:
    c = KycCase(lang=req.lang)
    if req.order_id:
        o = Order.load(req.order_id)
        if o is None:
            raise HTTPException(404, "Order not found")
        c.order_id = o.id
        # The application GSTIN is kept server-side (the order snapshot is masked).
        from ..advisor.session import AdvisorSession
        s = AdvisorSession.load(o.session_id)
        if s:
            c.application = {"gstin": s.profile.get("gstin"), "name": s.profile.get("trade_name"),
                             "city": s.profile.get("city")}
        o.kyc_case_id = c.id
        o.save()
    c.save()
    return view(c)


@router.get("/cases/{cid}")
def get_case(cid: str) -> dict:
    return view(_case(cid))


@router.post("/cases/{cid}/consent")
def give_consent(cid: str, req: ConsentReq) -> dict:
    c = _case(cid)
    try:
        rec = consent.record(c.id, req.purposes, req.lang)
    except ValueError as e:
        raise HTTPException(422, str(e))
    c.consent_id = rec["id"]
    c.save()
    return {"consent": rec, "case": view(c)}


@router.delete("/cases/{cid}/consent")
def withdraw_consent(cid: str) -> dict:
    c = _case(cid)
    if c.esigned_at:
        raise HTTPException(409, "Consent can't be withdrawn after signing; contact support to close the account")
    if c.consent_id:
        consent.withdraw(c.consent_id)
    for d in c.documents.values():
        pipeline.vault.delete(d.vault_ref)
    c.documents, c.checks, c.consent_id, c.verdict = {}, [], None, "pending"
    c.save()
    return view(c)


@router.post("/cases/{cid}/documents")
async def upload(cid: str, file: UploadFile = File(...), doc_type: str | None = Form(None)) -> dict:
    c = _case(cid)
    data = await file.read()
    try:
        doc = pipeline.ingest(c, data, file.filename, doc_type)
    except pipeline.KycError as e:
        raise HTTPException(422, str(e))
    return {"document_type": doc.doc_type, "case": view(c)}


@router.post("/cases/{cid}/sample/{applicant}")
def sample(cid: str, applicant: str) -> dict:
    """Demo helper: load the specimen documents of applicant K01–K12."""
    c = _case(cid)
    try:
        pipeline.load_sample(c, applicant)
    except pipeline.KycError as e:
        raise HTTPException(422, str(e))
    return view(c)


@router.post("/cases/{cid}/digilocker")
def digilocker(cid: str, req: DigiLockerReq) -> dict:
    c = _case(cid)
    try:
        pipeline.digilocker_fetch(c, req.gstin)
    except pipeline.KycError as e:
        raise HTTPException(422, str(e))
    return view(c)


@router.post("/cases/{cid}/confirm-udyam")
def confirm_udyam(cid: str) -> dict:
    c = _case(cid)
    try:
        pipeline.confirm_udyam(c)
    except pipeline.KycError as e:
        raise HTTPException(422, str(e))
    return view(c)


@router.post("/cases/{cid}/verify")
def verify(cid: str) -> dict:
    c = _case(cid)
    if not c.consent_id:
        raise HTTPException(409, "Consent is required")
    pipeline.verify(c)
    return view(c)


@router.post("/cases/{cid}/esign")
def esign(cid: str, req: OtpReq) -> dict:
    c = _case(cid)
    try:
        pipeline.esign(c, req.otp)
    except pipeline.KycError as e:
        raise HTTPException(422, str(e))
    if c.order_id:
        o = Order.load(c.order_id)
        if o and o.state == "QuoteAccepted":
            o.state = "KYCVerified"
            o.events.append(OrderEvent(state="KYCVerified", note="Business verified and e-signed online"))
            o.save()
    return view(c)
