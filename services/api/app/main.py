"""AirtelSync API (Project Udyam Digital). All JSON routes live under /api; the built web app is served at /."""
from __future__ import annotations


from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .advisor.api import router as advisor_router
from .checkout.api import router as checkout_router
from .console.api import router as console_router
from .config import REPO_ROOT
from .engine.api import router as engine_router
from .kyc.api import router as kyc_router
from .orders.api import router as orders_router
from .mocks.registry import router as mock_router

app = FastAPI(title="AirtelSync API", version="0.3.0",
              description="Digital-first MSME acquisition and onboarding for Accel Business (hackathon prototype).")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

api = APIRouter(prefix="/api")
for r in (engine_router, mock_router, advisor_router, checkout_router, kyc_router, orders_router, console_router):
    api.include_router(r)


@api.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(api)

# Serve the built PWA (apps/web/dist) when present: one process for the demo.
WEB_DIST = REPO_ROOT / "apps" / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB_DIST / path
        if path and f.is_file() and WEB_DIST in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
