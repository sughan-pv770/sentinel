from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import gateway, sentinelx
from app.routers import incidents_router
from app.routers import telemetry_router
from app.routers import auth as auth_router
from app.routers import dashboard_api
from app.ml_engine import get_ml_engine
from app.utils.logger import get_logger

logger = get_logger("sentinelx.main")

app = FastAPI(
    title=settings.app_name,
    description="Adaptive Runtime Zero Trust Security for APIs and Microservices",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ── API Routers ────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)        # /api/auth/*
app.include_router(dashboard_api.router)      # /api/dashboard/*
app.include_router(sentinelx.router)          # /sentinelx/*
app.include_router(incidents_router.router)   # /sentinelx/incidents/*
app.include_router(telemetry_router.router)   # /sentinelx/telemetry/*
app.include_router(gateway.router)            # /gateway/* and direct resource routes

# ── Static Files ───────────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Portal frontend (Vite build output)
PORTAL_DIR = Path(__file__).parent.parent.parent / "portal" / "dist"
if PORTAL_DIR.exists():
    app.mount("/portal/assets", StaticFiles(directory=PORTAL_DIR / "assets"), name="portal-assets")


@app.on_event("startup")
async def startup():
    # Warms the Isolation Forest at boot so the first real request isn't
    # slowed down by training (~50-150ms one-time cost, done once).
    get_ml_engine()
    logger.info("SentinelX gateway started, environment=%s" % settings.environment)


# ── Route Handlers ─────────────────────────────────────────────────────────────

@app.get("/portal/{full_path:path}", include_in_schema=False)
async def serve_portal(full_path: str):
    """Serve the React portal SPA. Falls back to index.html for client-side routing."""
    if PORTAL_DIR.exists():
        file_path = PORTAL_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(PORTAL_DIR / "index.html")
    # Dev mode fallback: redirect to Vite dev server
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="http://localhost:5173")


@app.get("/portal", include_in_schema=False)
async def portal_root():
    """Redirect /portal to /portal/"""
    if PORTAL_DIR.exists():
        return FileResponse(PORTAL_DIR / "index.html")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="http://localhost:5173")


@app.get("/")
async def root():
    """Root: redirect to portal (new UI) or legacy dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/portal")


@app.get("/legacy")
async def legacy_dashboard():
    """Legacy sandbox dashboard — preserved for reference."""
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sentinelx-gateway", "version": "2.0.0"}
