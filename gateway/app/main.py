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
from app.ml_engine import get_ml_engine
from app.utils.logger import get_logger

logger = get_logger("sentinelx.main")

app = FastAPI(
    title=settings.app_name,
    description="Adaptive Runtime Zero Trust Security for APIs and Microservices",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gateway.router)
app.include_router(sentinelx.router)
app.include_router(incidents_router.router)
app.include_router(telemetry_router.router)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def startup():
    # Warms the Isolation Forest at boot so the first real request isn't
    # slowed down by training (~50-150ms one-time cost, done once).
    get_ml_engine()
    logger.info("SentinelX gateway started, environment=%s" % settings.environment)


@app.get("/")
async def dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "sentinelx-gateway"}
