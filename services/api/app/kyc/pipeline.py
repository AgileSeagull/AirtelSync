"""KYC case operations: ingest documents, fetch from DigiLocker (mock), verify, e-sign."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .. import store
from ..config import DATA_DIR
from ..data_store import gstin_registry
from ..ids import gstin as gstin_ids
from ..mocks.registry import city_from_address
from . import checks, ocr, parse, vault
from .consent import audit
from .identifiers import find_udyam
from .models import Document, KycCase

log = logging.getLogger("kyc")
MAX_BYTES = 8 * 1024 * 1024
DEMO_OTP = "123456"


class KycError(Exception):
    pass


def ingest(case: KycCase, data: bytes, filename: str | None, declared_type: str | None, source: str = "upload") -> Document:
    if not case.consent_id:
        raise KycError("Consent is required before uploading documents")
    if len(data) > MAX_BYTES:
        raise KycError("File is larger than 8 MB")
    try:
        result = ocr.read(data)
    except Exception as e:  # unreadable image format
        raise KycError("Upload a photo or scan as JPG or PNG") from e
    detected = parse.detect_type(result.lines)
    doc_type = detected or declared_type
    if doc_type not in parse.DOC_TYPES:
        raise KycError("We couldn't tell which document this is. Choose the document type and upload again.")
    fields = parse.parse(doc_type, result.lines) if result.blur_score >= ocr.BLUR_THRESHOLD else {}
    doc = Document(doc_type=doc_type, source=source, filename=Path(filename).name if filename else None,
                   sha256=hashlib.sha256(data).hexdigest(),
                   quality={"blur_score": result.blur_score, "skew_deg": result.skew_deg,
                            "confidence": result.mean_confidence, "warnings": result.warnings,
                            "declared_type": declared_type, "detected_type": detected},
                   fields=fields)
    doc.vault_ref = vault.put(case.id, doc.id, data)
    old = case.documents.get(doc_type)
    if old:
        vault.delete(old.vault_ref)
    case.documents[doc_type] = doc
    case.verdict = "pending"
    audit("kyc.document_uploaded", case.id, {"doc_type": doc_type, "sha256": doc.sha256[:16], "source": source})
    case.save()
    return doc


def load_sample(case: KycCase, applicant: str) -> list[Document]:
    folder = DATA_DIR / "kyc_documents"
    files = sorted(folder.glob(f"{applicant.upper()}_*.png"))
    if not files:
        raise KycError(f"No sample documents for {applicant}")
    # A sample replaces the whole application so documents from different applicants never mix.
    for d in case.documents.values():
        vault.delete(d.vault_ref)
    case.documents, case.checks, case.udyam_confirmed, case.verdict = {}, [], None, "pending"
    return [ingest(case, f.read_bytes(), f.name, f.stem.split("_", 1)[1], source="sample") for f in files]


def digilocker_fetch(case: KycCase, gstin: str | None = None) -> list[Document]:
    """Mock DigiLocker pull: issuer-verified GST (and Udyam, if registered) records, no photos needed."""
    if not case.consent_id:
        raise KycError("Consent is required before fetching documents")
    g = gstin_ids.normalise(gstin or case.application.get("gstin") or "")
    if not gstin_ids.validate(g).valid:
        raise KycError("Enter a valid GSTIN to fetch your certificate from DigiLocker")
    rec = gstin_registry().get(g)
    if rec is None:
        raise KycError("DigiLocker has no GST certificate for this GSTIN")
    out = []
    gst = Document(doc_type="gst_certificate", source="digilocker",
                   fields={"gstin": rec["gstin"], "legal_name": rec["legal_name"], "trade_name": rec["trade_name"],
                           "constitution": rec["constitution"], "address": rec["principal_place_of_business"],
                           "liability_date": rec["registration_date"], "status": rec["status"]})
    old = case.documents.get("gst_certificate")
    if old:
        vault.delete(old.vault_ref)
    case.documents["gst_certificate"] = gst
    out.append(gst)
    u = find_udyam(rec["trade_name"], city_from_address(rec["principal_place_of_business"]))
    if u and "udyam_certificate" not in case.documents:
        ud = _udyam_doc(u, "digilocker")
        case.documents["udyam_certificate"] = ud
        out.append(ud)
    case.verdict = "pending"
    audit("kyc.digilocker_fetch", case.id, {"gstin": gstin_ids.mask(g), "docs": [d.doc_type for d in out]})
    case.save()
    return out


def _udyam_doc(rec: dict, source: str) -> Document:
    return Document(doc_type="udyam_certificate", source=source,
                    fields={"udyam_number": rec["udyam_number"], "enterprise_name": rec["enterprise_name"],
                            "major_activity": rec["major_activity"], "city": rec["city"], "state": rec["state"],
                            "registration_date": rec["date_of_registration"]})


def confirm_udyam(case: KycCase) -> Document:
    gst = case.documents.get("gst_certificate")
    name = city = None
    if gst:
        rec = gstin_registry().get(gst.fields.get("gstin_resolved") or gst.fields.get("gstin") or "")
        if rec:
            name, city = rec["trade_name"], city_from_address(rec["principal_place_of_business"])
        else:
            name = gst.fields.get("trade_name")
    ud = case.documents.get("udyam_certificate")
    if ud:
        name = name or ud.fields.get("enterprise_name")
        city = city or ud.fields.get("city")
    found = find_udyam(name, city)
    if not found:
        raise KycError("No Udyam registration found to confirm")
    if ud:
        vault.delete(ud.vault_ref)
    doc = _udyam_doc(found, "registry")
    case.documents["udyam_certificate"] = doc
    case.udyam_confirmed = found
    case.verdict = "pending"
    case.save()
    return doc


def verify(case: KycCase) -> KycCase:
    case.checks = checks.run(case)
    case.verdict = checks.verdict(case.checks)
    case.verified_at = store.now()
    # Data minimisation: raw images are deleted once a decision is made; kept (encrypted) only
    # while a person needs to review them (max vault.RETENTION_DAYS_REVIEW days).
    if case.verdict in ("approved", "blocked"):
        purge_raw(case)
    audit("kyc.verified", case.id, {"verdict": case.verdict, "codes": [c.code for c in case.checks if c.status not in ("pass", "info")]})
    case.save()
    return case


def purge_raw(case: KycCase) -> None:
    for d in case.documents.values():
        if d.vault_ref and not d.raw_deleted_at:
            vault.delete(d.vault_ref)
            d.vault_ref = None
            d.raw_deleted_at = store.now()


def esign(case: KycCase, otp: str) -> KycCase:
    if case.verdict != "approved":
        raise KycError("Verification must be complete before signing")
    if otp != DEMO_OTP:
        raise KycError("Incorrect OTP")
    case.esigned_at = store.now()
    audit("kyc.esigned", case.id)
    case.save()
    return case
