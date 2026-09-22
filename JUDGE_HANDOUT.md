# 🛡️ SentinelX — One-Page Judge Handout

## What does it do?
SentinelX is a real-time, ML-powered **Zero Trust gateway** that sits in front of API microservices and scores every single in-flight request for anomaly risk — in **<5ms**. Requests with low risk are forwarded transparently. Suspicious ones are challenged with MFA, rate-throttled, or revoked instantly.

> **The core insight**: JWTs only tell you *who* claims to be calling. SentinelX tells you *if that behavior makes sense given their history*.

---

## Architecture (1 Sentence)
> Feature extraction from 7 behavioral signals → Isolation Forest ML score + Deterministic rule score → Weighted composite risk 0–100 → 4-tier policy enforcement (Allow / Step-Up / Restrict / Revoke).

---

## Evaluation-Ready Metrics

| Metric | Value |
|---|---|
| ML Precision (threshold = -0.083) | **99.5%** |
| ML Recall (threshold = -0.083) | **100%** |
| False Positive Rate | **0.1%** |
| Gateway P99 Latency | **< 5ms** |
| Scenarios Covered | 5 (normal, freq spike, impossible travel, privilege escalation, endpoint novelty) |
| Model Training Samples | 4,000 synthetic normal traces |
| Features Extracted | 7 per request (Freq, Endpoint Novelty, Geo, Device, Time, Payload, Token Age) |

---

## Security Capabilities

| Attack | Detection Mechanism |
|---|---|
| Account Takeover (stolen token from new country) | Geo drift hard trigger + ML composite |
| Privilege Escalation (student→admin) | Endpoint novelty rule + role-aware override |
| Credential Stuffing / Brute Force | Frequency spike rule (>30 req/min) |
| Token Replay | Nonce dedup store (per-identity 1h TTL) |
| Off-hours access | Time-of-day deviation feature |
| Data exfiltration payload | Payload Z-score feature with EWMA per-identity baseline |

---

## Live Demo Flow (ask me!)

1. `GET /profile` from India → **ALLOW** (Risk ~10)
2. `POST /payments/transfer` from India → **STEP-UP MFA** (Risk ~60)
3. `GET /admin/users` from India → **RESTRICT** (Risk ~70)
4. `GET /profile` from Russia → **REVOKE** (Risk >90)
5. Run **Demo button** for the full automated 5-scenario walkthrough
6. Click any alert ticket to see per-feature ML contribution bars

---

## Production Readiness Evidence
- ✅ Dockerfile + docker-compose (one-command boot)
- ✅ `.env`-based config (pydantic-settings), no hardcoded secrets
- ✅ Structured JSON logging + Prometheus `/metrics` endpoint
- ✅ GitHub Actions CI (lint + ML eval on push)
- ✅ Redis-backed state store with pipeline batching
- ✅ Multi-worker Uvicorn config for horizontal scale
- ✅ Known limitations documented honestly (`JWT_LIMITATION.md`, `DB_MIGRATION_PATH.md`)

---

*Built for the SentinelX Offline Evaluation — September 2026*
