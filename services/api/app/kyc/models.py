"""KYC case, documents and check results."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from .. import store

CheckStatus = Literal["pass", "info", "action", "review", "block"]
Verdict = Literal["pending", "approved", "needs_action", "review", "blocked"]


class Check(BaseModel):
    code: str
    layer: Literal["quality", "completeness", "format", "registry", "consistency", "recency"]
    status: CheckStatus
    title: str
    message: str
    doc_type: str | None = None
    action: Literal["retake", "upload", "confirm_udyam", "digilocker", "none"] = "none"


class Document(BaseModel):
    id: str = Field(default_factory=lambda: "D" + uuid.uuid4().hex[:10])
    doc_type: str
    source: Literal["upload", "digilocker", "registry", "sample"] = "upload"
    filename: str | None = None
    sha256: str | None = None
    uploaded_at: str = Field(default_factory=store.now)
    quality: dict[str, Any] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)
    vault_ref: str | None = None
    raw_deleted_at: str | None = None


class KycCase(BaseModel):
    id: str = Field(default_factory=lambda: "KYC" + uuid.uuid4().hex[:8].upper())
    order_id: str | None = None
    created_at: str = Field(default_factory=store.now)
    lang: str = "en"
    application: dict[str, Any] = Field(default_factory=dict)  # what the owner told the advisor (gstin, name, city)
    consent_id: str | None = None
    documents: dict[str, Document] = Field(default_factory=dict)  # one current document per type
    udyam_confirmed: dict[str, Any] | None = None
    checks: list[Check] = Field(default_factory=list)
    verdict: Verdict = "pending"
    verified_at: str | None = None
    esigned_at: str | None = None
    reviewer_note: str | None = None

    def save(self) -> None:
        store.put("kyc_cases", self.id, self.model_dump())

    @classmethod
    def load(cls, cid: str) -> "KycCase | None":
        d = store.get("kyc_cases", cid)
        return cls(**d) if d else None
