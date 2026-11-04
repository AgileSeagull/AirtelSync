from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service
from .session import AdvisorSession

router = APIRouter(prefix="/advisor", tags=["advisor"])


class StartRequest(BaseModel):
    lang: str = "en"
    channel: str = "web"


class MessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


def _load(sid: str) -> AdvisorSession:
    s = AdvisorSession.load(sid)
    if s is None:
        raise HTTPException(404, "Session not found")
    return s


@router.post("/sessions")
def start(req: StartRequest) -> dict:
    s = service.start(req.lang, req.channel if req.channel in ("web", "whatsapp", "assisted") else "web")
    return service.view(s)


@router.get("/sessions/{sid}")
def get(sid: str) -> dict:
    return service.view(_load(sid))


@router.post("/sessions/{sid}/messages")
async def message(sid: str, req: MessageRequest) -> dict:
    s = _load(sid)
    reply, mode = await service.message(s, req.text)
    return {**service.view(s), "reply": reply, "mode": mode}
