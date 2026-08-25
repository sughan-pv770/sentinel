# SentinelX — Setup & Run Guide

Two ways to run it: **Option A** (fastest, no Docker, in-memory state) for a
laptop demo in the next 2 minutes, or **Option B** (docker-compose, real
Redis) for the "cloud-ready" story.

---

## Option A — local, no Docker (fastest)

Requires Python 3.11+ (3.10 also works).

```bash
# 1. Origin microservice SentinelX will protect
cd demo-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9000 &

# 2. SentinelX gateway itself (separate terminal / venv is fine, or reuse above)
cd ../gateway
python3 -m venv .venv && source .venv/bin/activate   # skip if reusing venv
pip install -r requirements.txt
export SENTINELX_ORIGIN_BASE_URL=http://localhost:9000
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open **http://localhost:8080** — that's the live dashboard.

No `SENTINELX_REDIS_URL` is set, so the gateway transparently uses the
built-in in-memory state store (identical interface to the Redis-backed
one) — nothing else to install.

### Try it

- Click any button in **"02 — Provoke a scenario"** on the dashboard for
  `u_alex`, `u_mina`, `svc_billing`, or `u_admin`. Each one fires real
  traffic through the actual feature extractor, rule layer, and trained
  Isolation Forest — the risk gauge, alert tickets, and ledger all update
  from genuine scoring, not canned data.
- Or hit the gateway directly, exactly as a real client would:

```bash
# A normal, allowed request -- gets proxied through to the origin service
curl -i http://localhost:8080/gateway/origin/profile \
  -H "x-identity-id: u_alex" -H "x-session-id: sess_1"

# First-ever hit on a sensitive endpoint -> privilege_escalation_attempt
# hard trigger, straight to revoke
curl -i http://localhost:8080/gateway/origin/admin/users \
  -H "x-identity-id: u_alex" -H "x-session-id: sess_1"

# Simulate impossible travel via the mock geo header
curl -i http://localhost:8080/gateway/origin/profile \
  -H "x-identity-id: u_alex" -H "x-session-id: sess_1" \
  -H "x-mock-geo: RU-MOW" -H "x-mock-device: linux-firefox"
```

**Demo tip:** for the cleanest read of each individual scenario, use a
different identity per scenario (`u_alex` for one, `u_mina` for the next,
etc.) — since risk state is genuinely cumulative per identity, running
five scenarios back-to-back on the same identity will show compounding
reasons, which is realistic but busier to narrate live.

---

## Option B — docker-compose (real Redis, full stack)

Requires Docker + Docker Compose.

```bash
docker-compose up --build
```

This builds and runs three containers:
- `redis` — the real behavioural-baseline / risk-state store (§4.3)
- `demo-service` — the origin microservice on :9000
- `gateway` — SentinelX itself on :8080, wired to both via env vars

Open **http://localhost:8080**. The dashboard's top-right chip will read
`backend: redis` instead of `backend: in-memory`, confirming it's on the
real store.

To stop: `docker-compose down`.

---

## API surface reference

| Method | Path | Purpose |
|---|---|---|
| ANY | `/gateway/{service}/{path}` | The actual reverse-proxy path — scores every request, then allows/step-up/restrict/revoke |
| GET | `/sentinelx/risk/{identity_id}` | Current risk score, tier, reasons for one identity |
| GET | `/sentinelx/policy` | Current tier thresholds |
| POST | `/sentinelx/policy` | Update thresholds, e.g. `{"thresholds":{"allow":25}}` |
| POST | `/sentinelx/revoke/{session_id}` | Manually revoke a session/token |
| GET | `/sentinelx/alerts?limit=50` | Recent explainable alerts feed |
| POST | `/sentinelx/simulate` | Fire a demo scenario: `{"identity_id":"u_alex","scenario":"impossible_travel","count":1}` |
| GET | `/sentinelx/stats` | Backend, latency budget, counters (dashboard header) |
| GET | `/health` | Liveness check |

Scenarios accepted by `/sentinelx/simulate`: `normal`, `frequency_spike`,
`new_admin_endpoint`, `impossible_travel`, `privilege_escalation`.

Every gateway response also carries `x-sentinelx-risk-score`,
`x-sentinelx-tier`, and `x-sentinelx-latency-ms` headers so you can watch
the scoring in a normal browser network tab too.

---

## Retraining the model / regenerating baseline data

The Isolation Forest trains automatically at process startup on synthetic
normal traffic (`gateway/app/seed/train_baseline.py`) — no separate step
needed. To inspect or tweak the synthetic distribution it trains on, edit
`generate_normal_traffic()` in that file. To export a trained model to disk
instead of retraining on every boot:

```bash
cd gateway
python -m app.seed.train_baseline
# writes app/seed/isolation_forest.joblib
```

(`ml_engine.py` currently retrains fresh on each boot for MVP simplicity —
swap in `joblib.load(...)` there if you want to pin a specific trained
model across restarts.)

---

## Environment variables

See `.env.example` at the repo root. All have safe defaults; nothing is
required to run Option A.

| Variable | Default | Meaning |
|---|---|---|
| `SENTINELX_REDIS_URL` | unset (in-memory fallback) | Redis connection string |
| `SENTINELX_ORIGIN_BASE_URL` | `http://localhost:9000` | Where the protected origin service lives |
| `SENTINELX_ENVIRONMENT` | `development` | Cosmetic, logged at startup |

---

## Deploying to Cloud Run (matches §3/§5 of the master doc)

```bash
# from gateway/
gcloud builds submit --tag gcr.io/PROJECT_ID/sentinelx-gateway
gcloud run deploy sentinelx-gateway \
  --image gcr.io/PROJECT_ID/sentinelx-gateway \
  --set-env-vars SENTINELX_REDIS_URL=redis://YOUR_MEMORYSTORE_IP:6379/0,SENTINELX_ORIGIN_BASE_URL=https://your-origin-service \
  --allow-unauthenticated
```

Repeat the same `gcloud builds submit` pattern for `demo-service/` (or
point `SENTINELX_ORIGIN_BASE_URL` at whatever real service you're actually
protecting).

---

## What's mocked vs real, for the judges

Being upfront about MVP scope (§9 of the master doc):

- **Real**: FastAPI reverse proxy, feature extraction against a genuine
  rolling per-identity profile, deterministic rule layer, a real trained
  scikit-learn Isolation Forest scoring real feature vectors, the
  allow/step-up/restrict/revoke decision + enforcement, the explainable
  reasons attached to every decision, the dashboard reading only from live
  API responses.
- **Mocked for demo purposes**: GeoIP/device-fingerprint resolution (a real
  deployment would parse this from request headers via a GeoIP DB + UA
  parser; here it's supplied via `x-mock-geo` / `x-mock-device` headers or
  the identity's synthetic scenario), and the OTP step-up challenge itself
  (returns a challenge object; wiring it to a real OTP provider is out of
  scope for the hackathon window per §9).
