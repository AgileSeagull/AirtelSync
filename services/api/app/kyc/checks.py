"""Layered KYC checks. Each check returns a status the owner can understand:
pass · info · action (owner can fix) · review (a person must look) · block (cannot proceed)."""
from __future__ import annotations

import re
from datetime import timedelta

from rapidfuzz import fuzz

from ..config import TODAY
from ..data_store import gstin_registry, udyam_registry
from ..ids import gstin as gstin_ids
from . import parse
from .identifiers import find_udyam, repair_gstin, repair_udyam
from .models import Check, KycCase
from .ocr import BLUR_THRESHOLD

ADDRESS_MAX_AGE_DAYS = 90
VERIFIED_SOURCES = ("digilocker", "registry")  # fetched from source systems, not OCR
NAME_MATCH = 90
ADDRESS_MATCH = 85


def _norm(s: str | None) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"\b(pvt|private|ltd|limited|llp)\b\.?", lambda m: {"pvt": "private", "ltd": "limited"}.get(m.group(1), m.group(1)), s)
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def similar(a: str | None, b: str | None) -> int:
    if not a or not b:
        return 0
    return int(fuzz.token_sort_ratio(_norm(a), _norm(b)))


def _lc(label: str) -> str:
    """Lower-case a label for mid-sentence use without breaking acronyms (GST, ID)."""
    return " ".join(w if w.isupper() or (len(w) > 1 and w[1].isupper()) else w.lower() for w in label.split())


def _fmt(d) -> str:
    return d.strftime("%d %b %Y")


def run(case: KycCase) -> list[Check]:
    out: list[Check] = []
    add = out.append
    docs = case.documents
    gst_doc, udyam_doc = docs.get("gst_certificate"), docs.get("udyam_certificate")
    sig_doc, addr_doc = docs.get("signatory_id"), docs.get("address_proof")

    # ---------------------------------------------------------------- quality
    unreadable: set[str] = set()
    for d in docs.values():
        if d.source != "upload" and d.source != "sample":
            continue
        q = d.quality
        label = parse.DOC_TYPES[d.doc_type]
        if q.get("blur_score", 999) < BLUR_THRESHOLD:
            unreadable.add(d.doc_type)
            add(Check(code="Q_BLUR", layer="quality", status="action", doc_type=d.doc_type, action="retake",
                      title=f"{label} is too blurry",
                      message=f"We can't read your {_lc(label)} reliably. Retake the photo in good light, holding the phone steady"
                              + (", or fetch it from DigiLocker." if d.doc_type in ("gst_certificate", "udyam_certificate") else ".")))
            continue
        if abs(q.get("skew_deg", 0)) >= 2:
            add(Check(code="Q_SKEW", layer="quality", status="info", doc_type=d.doc_type,
                      title=f"{label} straightened", message=f"The photo was tilted {abs(q['skew_deg']):.0f}°; we straightened it automatically."))
        key = {"gst_certificate": "legal_name", "udyam_certificate": "enterprise_name", "signatory_id": "name",
               "address_proof": "billed_to"}[d.doc_type]
        if not d.fields.get(key):
            unreadable.add(d.doc_type)
            add(Check(code="Q_UNREADABLE", layer="quality", status="action", doc_type=d.doc_type, action="retake",
                      title=f"Couldn't read {_lc(label)}", message=f"Please upload a clearer photo or scan of your {_lc(label)}."))

    # ---------------------------------------------------------------- identify the business (GSTIN)
    gst_rec = None
    gstin = None
    if gst_doc and "gst_certificate" not in unreadable:
        f = gst_doc.fields
        if gst_doc.source in VERIFIED_SOURCES:
            gstin, how = f.get("gstin"), "source"
        else:
            hints = [f.get("trade_name"), f.get("legal_name"), (addr_doc.fields.get("billed_to") if addr_doc else None)]
            gstin, how = repair_gstin(f.get("gstin"), [h for h in hints if h])
            if how in ("checksum", "registry"):
                add(Check(code="F_GSTIN_CORRECTED", layer="format", status="info", doc_type="gst_certificate",
                          title="GSTIN read and corrected",
                          message=f"OCR read '{f.get('gstin')}'. Using the checksum and GST records it is {gstin_ids.mask(gstin)}."))
            elif how == "unreadable":
                add(Check(code="F_GSTIN_UNREADABLE", layer="format", status="action", doc_type="gst_certificate", action="retake",
                          title="GSTIN not readable", message="We couldn't read a valid GSTIN on the certificate. Upload a clearer copy or fetch it from DigiLocker."))
        if gstin:
            gst_doc.fields["gstin_resolved"] = gstin
            gst_rec = gstin_registry().get(gstin)

    app_gstin = case.application.get("gstin")
    if app_gstin and gstin and app_gstin != gstin:
        add(Check(code="R_APPLICATION_GSTIN", layer="registry", status="review", doc_type="gst_certificate",
                  title="Documents are for a different GSTIN",
                  message=f"Your application uses GSTIN {gstin_ids.mask(app_gstin)} but the certificate shows {gstin_ids.mask(gstin)}."))

    # ---------------------------------------------------------------- completeness
    has_gst = gst_doc is not None
    if not has_gst and not app_gstin:
        add(Check(code="C_GST", layer="completeness", status="info", doc_type="gst_certificate",
                  title="No GST certificate", message="Without GST registration, products that need GST (e.g. WhatsApp Business API, leased lines) can't be activated."))
    elif not has_gst:
        add(Check(code="C_GST", layer="completeness", status="action", doc_type="gst_certificate", action="digilocker",
                  title="GST certificate missing", message="Upload your GST certificate or fetch it from DigiLocker in one tap."))

    canonical_name = (gst_rec or {}).get("trade_name") or (gst_doc.fields.get("trade_name") if gst_doc else None) \
        or (udyam_doc.fields.get("enterprise_name") if udyam_doc else None) or (addr_doc.fields.get("billed_to") if addr_doc else None) \
        or case.application.get("name")
    canonical_city = None
    if gst_rec:
        from ..mocks.registry import city_from_address
        canonical_city = city_from_address(gst_rec["principal_place_of_business"])

    if udyam_doc is None and case.udyam_confirmed is None:
        found = find_udyam(canonical_name, canonical_city)
        if has_gst and found:
            add(Check(code="C_UDYAM", layer="completeness", status="action", action="confirm_udyam", doc_type="udyam_certificate",
                      title="Udyam certificate not uploaded",
                      message=f"We found Udyam registration {found['udyam_number']} for {found['enterprise_name']}, {found['city']}. Confirm it's yours instead of uploading."))
        elif has_gst:
            add(Check(code="C_UDYAM", layer="completeness", status="info", doc_type="udyam_certificate",
                      title="No Udyam registration", message="Udyam registration is optional when you have an active GSTIN."))
        else:
            add(Check(code="C_UDYAM", layer="completeness", status="action", action="upload", doc_type="udyam_certificate",
                      title="Business registration needed", message="Upload a GST or Udyam certificate so we can verify the business."))
    if sig_doc is None:
        add(Check(code="C_SIGNATORY", layer="completeness", status="action", action="upload", doc_type="signatory_id",
                  title="Signatory ID missing", message="Upload the ID of the person who will sign for the business."))
    if addr_doc is None:
        add(Check(code="C_ADDRESS", layer="completeness", status="action", action="upload", doc_type="address_proof",
                  title="Address proof missing", message="Upload a recent electricity, water or phone bill for the installation address."))

    # ---------------------------------------------------------------- GST registry
    if gstin and gst_rec is None:
        add(Check(code="R_GST_FOUND", layer="registry", status="review", doc_type="gst_certificate",
                  title="GSTIN not found in GST records", message=f"{gstin_ids.mask(gstin)} is not registered. A specialist will check the certificate."))
    if gst_rec:
        status = gst_rec["status"]
        if status != "Active":
            add(Check(code="R_GST_STATUS", layer="registry", status="block", doc_type="gst_certificate",
                      title=f"GST registration is {status.lower()}",
                      message=f"GST records show this registration as {status.upper()}. We can't verify the business with it. "
                              "If it has been restored, ask your CA for the reactivation order; or apply without GST for non-GST products."))
        else:
            add(Check(code="R_GST_STATUS", layer="registry", status="pass", doc_type="gst_certificate",
                      title="GST registration active", message="GSTIN found and active in GST records."))
        if gst_doc.source not in VERIFIED_SOURCES:
            f = gst_doc.fields
            for code, field, label in (("R_GST_LEGAL_NAME", "legal_name", "Legal name"), ("R_GST_TRADE_NAME", "trade_name", "Trade name")):
                score = similar(f.get(field), gst_rec[field])
                if f.get(field) and score < NAME_MATCH:
                    add(Check(code=code, layer="registry", status="review", doc_type="gst_certificate",
                              title=f"{label} doesn't match GST records",
                              message=f"Certificate says '{f.get(field)}' but GST records say '{gst_rec[field]}'. The certificate may have been altered; a specialist will review it."))
            if f.get("constitution") and similar(f["constitution"], gst_rec["constitution"]) < NAME_MATCH:
                add(Check(code="R_GST_CONSTITUTION", layer="registry", status="review", doc_type="gst_certificate",
                          title="Constitution doesn't match", message=f"Certificate: {f['constitution']}; GST records: {gst_rec['constitution']}."))
            pin_doc, pin_reg = parse.pincode(f.get("address")), parse.pincode(gst_rec["principal_place_of_business"])
            if f.get("address") and (pin_doc != pin_reg or similar(f.get("address"), gst_rec["principal_place_of_business"]) < ADDRESS_MATCH):
                add(Check(code="R_GST_ADDRESS", layer="registry", status="review", doc_type="gst_certificate",
                          title="Address doesn't match GST records", message="The principal place of business on the certificate differs from GST records."))

    # ---------------------------------------------------------------- Udyam
    if udyam_doc and "udyam_certificate" not in unreadable:
        raw = udyam_doc.fields.get("udyam_number")
        number = raw if udyam_doc.source in VERIFIED_SOURCES else repair_udyam(raw)
        rec = udyam_registry().get(number) if number else None
        if not number:
            found = find_udyam(udyam_doc.fields.get("enterprise_name"), udyam_doc.fields.get("city"))
            if found:
                add(Check(code="F_UDYAM_NUMBER", layer="format", status="action", action="confirm_udyam", doc_type="udyam_certificate",
                          title="Udyam number missing on certificate",
                          message=f"The certificate has no registration number. We found {found['udyam_number']} for this business; confirm it's yours."))
            else:
                add(Check(code="F_UDYAM_NUMBER", layer="format", status="review", doc_type="udyam_certificate",
                          title="Udyam certificate has no registration number",
                          message="The certificate shows no Udyam number and no Udyam registration exists for this business. A specialist will review it."))
        elif rec is None:
            add(Check(code="R_UDYAM_FOUND", layer="registry", status="review", doc_type="udyam_certificate",
                      title="Udyam number not found", message=f"{number} is not in Udyam records."))
        else:
            udyam_doc.fields["udyam_resolved"] = number
            ok_name = similar(udyam_doc.fields.get("enterprise_name"), rec["enterprise_name"]) >= NAME_MATCH
            ok_city = (udyam_doc.fields.get("city") or "").lower() == rec["city"].lower()
            if udyam_doc.source not in VERIFIED_SOURCES and not (ok_name and ok_city):
                add(Check(code="R_UDYAM_DETAILS", layer="registry", status="review", doc_type="udyam_certificate",
                          title="Udyam details don't match records",
                          message=f"Udyam records show {rec['enterprise_name']}, {rec['city']}."))
            else:
                add(Check(code="R_UDYAM", layer="registry", status="pass", doc_type="udyam_certificate",
                          title="Udyam registration verified", message=f"{rec['enterprise_name']} ({rec['enterprise_type']}) found in Udyam records."))
            doc_date = parse.parse_date(udyam_doc.fields.get("registration_date"))
            if udyam_doc.source not in VERIFIED_SOURCES and doc_date and doc_date.isoformat() != rec["date_of_registration"]:
                add(Check(code="R_UDYAM_DATE", layer="registry", status="info", doc_type="udyam_certificate",
                          title="Registration date differs", message=f"Using the Udyam portal date {rec['date_of_registration']}."))

    # ---------------------------------------------------------------- consistency across documents
    names = {}
    if gst_doc and gst_doc.fields.get("trade_name"):
        names["GST certificate"] = gst_doc.fields["trade_name"]
    if udyam_doc and udyam_doc.fields.get("enterprise_name"):
        names["Udyam certificate"] = udyam_doc.fields["enterprise_name"]
    if addr_doc and addr_doc.fields.get("billed_to"):
        names["Address proof"] = addr_doc.fields["billed_to"]
    if sig_doc and sig_doc.fields.get("business"):
        names["Signatory ID"] = sig_doc.fields["business"]
    if canonical_name and names:
        off = {k: v for k, v in names.items() if similar(v, canonical_name) < NAME_MATCH}
        if off:
            add(Check(code="X_BUSINESS_NAME", layer="consistency", status="review",
                      title="Business name differs across documents",
                      message="; ".join(f"{k}: '{v}'" for k, v in off.items()) + f" (expected '{canonical_name}')."))
        else:
            add(Check(code="X_BUSINESS_NAME", layer="consistency", status="pass", title="Business name consistent",
                      message=f"All documents name {canonical_name}."))

    if addr_doc and "address_proof" not in unreadable:
        ref_addr = (gst_rec or {}).get("principal_place_of_business") or (gst_doc.fields.get("address") if gst_doc else None)
        a = addr_doc.fields.get("address")
        if ref_addr and a:
            if parse.pincode(a) != parse.pincode(ref_addr) or similar(a, ref_addr) < ADDRESS_MATCH:
                add(Check(code="X_ADDRESS", layer="consistency", status="action", action="upload", doc_type="address_proof",
                          title="Address proof is for a different address",
                          message="Upload a bill for the registered business address, or tell us the installation address."))
            else:
                add(Check(code="X_ADDRESS", layer="consistency", status="pass", doc_type="address_proof",
                          title="Address matches", message="Address proof matches the registered business address."))

    if sig_doc and "signatory_id" not in unreadable:
        constitution = (gst_rec or {}).get("constitution") or (gst_doc.fields.get("constitution") if gst_doc else None)
        legal = (gst_rec or {}).get("legal_name") or (gst_doc.fields.get("legal_name") if gst_doc else None)
        prop_name, _ = parse.proprietor(legal)
        signer = sig_doc.fields.get("name")
        if constitution and "propriet" in constitution.lower() and prop_name:
            if similar(signer, prop_name) >= NAME_MATCH:
                add(Check(code="X_SIGNATORY", layer="consistency", status="pass", doc_type="signatory_id",
                          title="Signatory is the proprietor", message=f"{signer} is the registered proprietor."))
            else:
                add(Check(code="X_SIGNATORY", layer="consistency", status="action", action="upload", doc_type="signatory_id",
                          title="Signatory isn't the proprietor",
                          message=f"For a proprietorship the proprietor ({prop_name}) must sign. Upload their ID, or an authority letter signed by them."))
        elif constitution:
            add(Check(code="X_SIGNATORY", layer="consistency", status="info", doc_type="signatory_id",
                      title="Signatory authority checked at e-sign",
                      message=f"For a {constitution.lower()}, {signer or 'the signatory'} confirms authority when e-signing with Aadhaar OTP."))

    # ---------------------------------------------------------------- recency / validity
    if addr_doc and "address_proof" not in unreadable:
        d = parse.parse_date(addr_doc.fields.get("bill_date"))
        if d is None:
            add(Check(code="D_ADDRESS_DATE", layer="recency", status="action", action="retake", doc_type="address_proof",
                      title="Bill date not readable", message="Upload a bill where the bill date is clearly visible."))
        elif d > TODAY:
            add(Check(code="D_ADDRESS_DATE", layer="recency", status="review", doc_type="address_proof",
                      title="Bill date is in the future", message=f"The bill is dated {_fmt(d)}."))
        elif (TODAY - d).days > ADDRESS_MAX_AGE_DAYS:
            add(Check(code="D_ADDRESS_DATE", layer="recency", status="action", action="upload", doc_type="address_proof",
                      title="Address proof is too old",
                      message=f"Your bill is dated {_fmt(d)}, more than {ADDRESS_MAX_AGE_DAYS} days ago. Upload one dated after {_fmt(TODAY - timedelta(days=ADDRESS_MAX_AGE_DAYS))}."))
        else:
            add(Check(code="D_ADDRESS_DATE", layer="recency", status="pass", doc_type="address_proof",
                      title="Address proof is recent", message=f"Bill dated {_fmt(d)}."))
    if sig_doc and "signatory_id" not in unreadable:
        v = parse.parse_date(sig_doc.fields.get("valid_till"))
        if v and v < TODAY:
            add(Check(code="D_ID_VALIDITY", layer="recency", status="action", action="upload", doc_type="signatory_id",
                      title="Signatory ID has expired", message=f"The ID expired on {_fmt(v)}. Upload a valid ID."))
        elif v:
            add(Check(code="D_ID_VALIDITY", layer="recency", status="pass", doc_type="signatory_id",
                      title="Signatory ID valid", message=f"Valid till {_fmt(v)}."))
    return out


def verdict(checks: list[Check]) -> str:
    statuses = {c.status for c in checks}
    if "block" in statuses:
        return "blocked"
    if "review" in statuses:
        return "review"
    if "action" in statuses:
        return "needs_action"
    return "approved"
