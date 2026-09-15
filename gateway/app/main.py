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
from app.routers import sse_router
from app.routers import mfa_router
from app.ml_engine import get_ml_engine
from app.utils.logger import get_logger

logger = get_logger("sentinelx.main")

app = FastAPI(
    title=settings.app_name,
    description="Adaptive Runtime Zero Trust Security for APIs and Microservices",
    version="3.0.0",
)

# ── Middleware (order matters: outermost first) ────────────────────────────────

# Observability (outermost — records latency for the entire stack)
from app.middleware.observability_middleware import ObservabilityMiddleware
app.add_middleware(ObservabilityMiddleware)

# Rate limiting (before CORS so surge requests are rejected before processing)
from app.middleware.rate_limit_middleware import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ── API Routers ────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)        # /api/auth/*
app.include_router(mfa_router.router)         # /api/mfa/*
app.include_router(sse_router.router)         # /api/events/*
app.include_router(dashboard_api.router)      # /api/dashboard/*
app.include_router(sentinelx.router)          # /sentinelx/*
app.include_router(incidents_router.router)   # /sentinelx/incidents/*
app.include_router(telemetry_router.router)   # /sentinelx/telemetry/*
app.include_router(gateway.router)            # /gateway/* and direct resource routes

# ── Prometheus Metrics ─────────────────────────────────────────────────────────
if settings.metrics_enabled:
    from app.observability import get_metrics_app
    app.mount("/metrics", get_metrics_app())

# ── Static Files ───────────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Portal frontend (Vite build output)
PORTAL_DIR = Path(__file__).parent.parent.parent / "portal" / "dist"
if PORTAL_DIR.exists():
    app.mount("/portal/assets", StaticFiles(directory=PORTAL_DIR / "assets"), name="portal-assets")


@app.on_event("startup")
async def startup():
    # Warm the Isolation Forest at boot so the first real request isn't
    # slowed down by training (~50-150ms one-time cost).
    get_ml_engine()
    logger.info(
        f"SentinelX gateway v3.0.0 started  "
        f"env={settings.environment}  "
        f"rate_limit={settings.rate_limit_enabled}  "
        f"ml_shadow={settings.ml_shadow_mode}  "
        f"metrics={settings.metrics_enabled}"
    )


# ── Route Handlers ─────────────────────────────────────────────────────────────

@app.get("/portal/{full_path:path}", include_in_schema=False)
async def serve_portal(full_path: str):
    """Serve the React portal SPA. Falls back to index.html for client-side routing."""
    if PORTAL_DIR.exists():
        file_path = PORTAL_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(PORTAL_DIR / "index.html")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="http://localhost:5173")


@app.get("/portal", include_in_schema=False)
async def portal_root():
    if PORTAL_DIR.exists():
        return FileResponse(PORTAL_DIR / "index.html")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="http://localhost:5173")


@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/portal")


@app.get("/legacy")
async def legacy_dashboard():
    """Legacy sandbox dashboard — preserved for reference."""
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/health")
async def health():
    """Liveness + readiness probe endpoint (K8s / ALB)."""
    from app.state_store import get_store
    from app.services.circuit_breaker import get_ml_circuit_breaker
    from app.services.sse_manager import get_sse_manager

    store = get_store()
    cb = get_ml_circuit_breaker()
    sse = get_sse_manager()

    return {
        "status": "ok",
        "service": "sentinelx-gateway",
        "version": "3.0.0",
        "environment": settings.environment,
        "ml_circuit_breaker": cb.status(),
        "sse_connections": sse.active_connection_count(),
        "rate_limit_enabled": settings.rate_limit_enabled,
    }
