"""Advisor session state."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from .. import store

LANGS = {"en": "English", "hi": "Hindi", "mr": "Marathi", "ta": "Tamil", "te": "Telugu", "kn": "Kannada",
         "gu": "Gujarati", "bn": "Bengali", "pa": "Punjabi", "ml": "Malayalam"}


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    mode: str | None = None


class AdvisorSession(BaseModel):
    id: str = Field(default_factory=lambda: "S" + uuid.uuid4().hex[:10].upper())
    lang: str = "en"
    channel: Literal["web", "whatsapp", "assisted"] = "web"
    created_at: str = Field(default_factory=store.now)
    profile: dict[str, Any] = Field(default_factory=dict)  # partial Profile fields
    asked: list[str] = Field(default_factory=list)  # slots already asked (scripted mode)
    last_asked: str | None = None
    transcript: list[Turn] = Field(default_factory=list)  # what the owner saw
    llm_messages: list[dict[str, Any]] = Field(default_factory=list)  # Claude API history (append-only)
    gemini_contents: list[dict[str, Any]] = Field(default_factory=list)  # Gemini API history (append-only)
    gemini_model: str | None = None
    lang_switched: bool = False  # the owner changed language in the current message  # model that answered the last Gemini turn
    recommendation: dict[str, Any] | None = None
    selected_tier: str | None = None
    handoff: dict[str, Any] | None = None
    llm_disabled: bool = False  # set after a permanent LLM failure (bad key); the rest of the session runs scripted
    status: Literal["open", "recommended", "quoted", "handoff", "converted"] = "open"

    def save(self) -> None:
        store.put("advisor_sessions", self.id, self.model_dump())

    @classmethod
    def load(cls, sid: str) -> "AdvisorSession | None":
        d = store.get("advisor_sessions", sid)
        return cls(**d) if d else None
