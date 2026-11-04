"""Udyam Digital API."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .advisor.api import router as advisor_router
from .engine.api import router as engine_router
from .mocks.registry import router as mock_router

app = FastAPI(title="Udyam Digital API", version="0.1.0",
              description="Digital-first MSME acquisition and onboarding for Accel Business (hackathon prototype).")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(engine_router)
app.include_router(mock_router)
app.include_router(advisor_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
