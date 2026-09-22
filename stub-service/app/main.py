"""
Stub Service — port 9002
Minimal proof-of-concept showing that SentinelX can protect ANY SaaS app
purely via services.json config, with zero gateway code changes.

Onboarding steps that were taken:
  1. Added "stub-service" block to services.json (base_url, endpoints)
  2. Added stub-service to docker-compose.yml and start_all.py
  That's it. No gateway code was touched.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="SentinelX Stub Service", version="1.0")


@app.get("/hello")
async def hello(request: Request):
    identity = request.headers.get("x-identity-id", "anonymous")
    return {"message": f"Hello, {identity}! This endpoint is NORMAL sensitivity.", "service": "stub-service"}


@app.post("/secret")
async def secret(request: Request):
    identity = request.headers.get("x-identity-id", "anonymous")
    return {"message": f"Sensitive operation executed by {identity}.", "service": "stub-service", "sensitivity": "sensitive"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "stub-service", "port": 9002}
