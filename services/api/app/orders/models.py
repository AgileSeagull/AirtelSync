"""Orders. Phase 3 creates them at quote acceptance; later phases add KYC and fulfilment states."""
from __future__ import annotations

import random
import string
from typing import Any

from pydantic import BaseModel, Field

from .. import store


def _order_id() -> str:
    return "UD-" + "".join(random.choices(string.digits, k=6))


class OrderEvent(BaseModel):
    at: str = Field(default_factory=store.now)
    state: str
    note: str | None = None


class Order(BaseModel):
    id: str = Field(default_factory=_order_id)
    session_id: str
    created_at: str = Field(default_factory=store.now)
    business: dict[str, Any]  # masked profile snapshot
    items: list[dict[str, Any]]
    contract: str
    quote: dict[str, Any]
    state: str = "QuoteAccepted"
    events: list[OrderEvent] = Field(default_factory=list)
    kyc_case_id: str | None = None
    lines: list[dict[str, Any]] = Field(default_factory=list)  # per-product fulfilment (phase 5)

    def save(self) -> None:
        store.put("orders", self.id, self.model_dump())

    @classmethod
    def load(cls, oid: str) -> "Order | None":
        d = store.get("orders", oid)
        return cls(**d) if d else None
