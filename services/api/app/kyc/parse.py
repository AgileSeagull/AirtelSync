"""Turn OCR lines into typed fields for each document type."""
from __future__ import annotations

import re
from datetime import date

DOC_TYPES = {
    "gst_certificate": "GST registration certificate",
    "udyam_certificate": "Udyam registration certificate",
    "signatory_id": "Authorised signatory ID",
    "address_proof": "Address proof (utility bill)",
}

LABELS = {
    "gst_certificate": [("gstin", r"GSTIN"), ("legal_name", r"Legal\s*name"), ("trade_name", r"Trade\s*name"),
                        ("constitution", r"Constitution"), ("address", r"Address\s*of\s*principal"),
                        ("address_cont", r"place\s*of\s*business"), ("liability_date", r"Date\s*of\s*liability"),
                        ("registration_type", r"Type\s*of\s*.?egistration")],
    "udyam_certificate": [("udyam_number", r"Udyam\s*reg\.?\s*number"), ("enterprise_name", r"Enterprise\s*name"),
                          ("major_activity", r"Major\s*activity"), ("city", r"^City"), ("state", r"^State"),
                          ("registration_date", r"Date\s*of\s*registration")],
    "signatory_id": [("name", r"^Name$"), ("designation", r"^Designation$"), ("business", r"^For\s*business$"),
                     ("id_number", r"^ID\s*n[oa]\.?$"), ("valid_till", r"^Valid\s*till$")],
    "address_proof": [("consumer_no", r"Consumer\s*no"), ("billed_to", r"Billed\s*to"),
                      ("address", r"Supply\s*address"), ("bill_date", r"Bill\s*date"),
                      ("units", r"Units\s*consumed"), ("amount_due", r"Amount\s*due")],
}

TITLES = [("gst_certificate", r"GST\s*Registration"), ("udyam_certificate", r"Udyam\s*Registration"),
          ("signatory_id", r"Signatory\s*ID"), ("address_proof", r"Bill|Utility|address proof")]

_FOOTER = re.compile(r"Hackathon|Fictional|Specimen|Format for|SYNTHETIC", re.I)


def detect_type(lines: list[str]) -> str | None:
    head = " ".join(lines[:4])
    for t, pat in TITLES:
        if re.search(pat, head, re.I):
            return t
    return None


def _clean(v: str) -> str:
    v = v.replace("~", "-").replace("—", "-").replace("|", "").strip(" :;,.")
    return re.sub(r"\s+", " ", v).strip()


def parse(doc_type: str, lines: list[str]) -> dict[str, str | None]:
    body = [l for l in lines if not _FOOTER.search(l)]
    spec = LABELS[doc_type]
    out: dict[str, str | None] = {k: None for k, _ in spec}
    stacked = doc_type == "signatory_id"  # label on one line, value on the next
    i = 0
    last_key = None
    while i < len(body):
        line = body[i]
        matched = False
        for key, pat in spec:
            m = re.search(pat, line, re.I)
            if m and (stacked or m.start() < 6):
                if stacked:
                    nxt = body[i + 1] if i + 1 < len(body) else ""
                    is_label = any(re.search(p, nxt, re.I) for _, p in spec)
                    out[key] = None if is_label else _clean(nxt)
                    i += 0 if is_label else 1
                else:
                    out[key] = _clean(line[m.end():]) or None
                last_key = key
                matched = True
                break
        if not matched and not stacked and last_key in ("address", "address_cont") and doc_type in ("address_proof",):
            out["address"] = _join(out.get("address") or "", line)
        i += 1
    if doc_type == "gst_certificate":
        if out.get("address_cont"):
            out["address"] = _join(out.get("address") or "", out.pop("address_cont") or "")
        else:
            out.pop("address_cont", None)
    return out


def _join(a: str, b: str) -> str:
    """Addresses wrap mid-word ('…Visakhapatnam, A' + 'ndhra Pradesh'): glue lowercase continuations."""
    b = _clean(b)
    if not a:
        return b
    if b[:1].islower() and a[-1:].isalpha():
        return a + b
    return f"{a} {b}"


def parse_date(v: str | None) -> date | None:
    if not v:
        return None
    s = re.sub(r"[^0-9-]", "", v.replace(" ", ""))
    m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def pincode(address: str | None) -> str | None:
    if not address:
        return None
    m = re.search(r"-\s*([\d\s]{6,9})\s*$", address.strip())  # "Kerala - 75 2083" (wrapped PIN)
    if m:
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) == 6:
            return digits
    m = re.search(r"\b(\d{6})\b", address)
    return m.group(1) if m else None


def proprietor(legal_name: str | None) -> tuple[str | None, str | None]:
    """'Neha Kaur (Prop. Vindhya Tours & Travels)' → ('Neha Kaur', 'Vindhya Tours & Travels')."""
    if not legal_name:
        return None, None
    m = re.match(r"\s*(.+?)\s*\(\s*Prop[.,]?\s*(.+?)\s*\)?\s*\}?\s*$", legal_name, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip(" )}")
    return None, None
