# SentinelX — Architecture Deep-Dive

> This document provides a detailed technical reference for every component in the SentinelX pipeline. For setup instructions, see [`SETUP.md`](SETUP.md). For the demo script, see [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

---

## 1. System Topology

SentinelX deploys as a **reverse-proxy gateway** between clients and origin services:

```
                    Internet / Service Mesh
                           │
                           ▼
            ┌──────────────────────────┐
            │   SentinelX Gateway      │ ← FastAPI + Uvicorn
            │   (stateless compute)    │    Port 8080
            │                          │
            │   ┌──────────────────┐   │
            │   │ Scoring Pipeline │   │    < 15ms per request
            │   └───────┬──────────┘   │
            │           │              │
            │   ┌───────▼──────────┐   │
            │   │ State Store      │───┼──→ Redis (production)
            │   │ Interface        │   │    or InMemoryStore (demo)
            │   └──────────────────┘   │
            │                          │
            │   ┌──────────────────┐   │
            │   │ Control Plane    │   │    /sentinelx/* API
            │   └──────────────────┘   │
            │                          │
            │   ┌──────────────────┐   │
            │   │ Dashboard        │   │    Static HTML/CSS/JS
            │   └──────────────────┘   │
            └──────────────────────────┘
                           │
                           │ proxied (tier=allow only)
                           ▼
            ┌──────────────────────────┐
            │   Origin Service         │ ← Any microservice
            │   (demo-service)         │    Port 9000
            └──────────────────────────┘
```

### Design Principle: Stateless Compute, Externalized State

The gateway process holds **zero persistent state**. All behavioural baselines, risk scores, revoked sessions, and alert entries live in the state store (Redis or in-memory). This means:

- Multiple gateway instances can serve the same traffic with consistent scoring
- Gateway crashes don't lose security state
- Horizontal scaling is trivial (add more Cloud Run / ECS instances)

---

## 2. Component Reference

### 2.1 FastAPI Application (`main.py`)

**Purpose:** Application entry point. Initializes the ML engine at startup, mounts routers, and serves the static dashboard.

**Startup sequence:**
1. `@app.on_event("startup")` — calls `ml_engine.train()` to fit the Isolation Forest on 4,000 synthetic normal samples
2. Mounts `StaticFiles` at `/static` for dashboard assets
3. Serves `dashboard.html` at `/` (root)
4. Includes `gateway_router` at `/gateway` and `sentinelx_router` at `/sentinelx`

**Key design decisions:**
- ML training runs synchronously during startup (blocks for ~150ms) rather than lazily on first request — this ensures the very first request through the gateway is scored, not passed through unscored
- Dashboard is served from the same process to minimize deployment complexity for the hackathon demo

### 2.2 Configuration (`config.py`)

**Purpose:** Environment-driven settings via Pydantic, plus a mutable policy dictionary.

| Setting | Source | Default |
|---|---|---|
| `REDIS_URL` | `SENTINELX_REDIS_URL` env var | `None` (→ in-memory) |
| `ORIGIN_BASE_URL` | `SENTINELX_ORIGIN_BASE_URL` env var | `http://localhost:9000` |
| `ENVIRONMENT` | `SENTINELX_ENVIRONMENT` env var | `development` |

**Policy (mutable at runtime via `/sentinelx/policy`):**
```python
POLICY = {
    "thresholds": {"allow": 30, "step_up": 60, "restrict": 85},
    "hard_triggers": ["privilege_escalation_attempt", "impossible_travel",
                      "token_used_after_revocation", "device_and_geo_change"],
    "step_up": {"method": "otp", "ttl_seconds": 300},
    "restrict": {"action": "rate_limit", "limit_per_minute": 5},
}
```

### 2.3 State Store (`state_store.py`)

**Purpose:** Provides an async interface for reading/writing identity behavioural profiles, risk state, alerts, and revoked sessions.

**Two implementations, one interface:**

| Method | `InMemoryStore` | `RedisStore` |
|---|---|---|
| `get_baseline(identity_id)` | Python dict lookup | `HGETALL sentinelx:baseline:{id}` |
| `update_baseline(identity_id, ctx)` | Dict mutation | `HMSET` + `SADD` for endpoint/geo/device sets |
| `get_risk_state(identity_id)` | Dict lookup | `HGETALL sentinelx:risk:{id}` |
| `set_risk_state(identity_id, ...)` | Dict mutation | `HMSET` with TTL |
| `revoke_session(session_id)` | Set addition | `SADD sentinelx:revoked` |
| `is_session_revoked(session_id)` | Set membership test | `SISMEMBER` |
| `append_alert(alert)` | List prepend | `LPUSH` + `LTRIM` |
| `get_alerts(limit)` | List slice | `LRANGE` |

**Behavioural Baseline Data Model:**
```python
{
    "total": 47,                    # Total requests from this identity
    "endpoints": {"_profile": 35, "_orders": 10, "_admin_users": 2},
    "geos": {"IN-TN", "IN-KA"},     # Set of seen geographic regions
    "devices": {"chrome-macos"},     # Set of seen device fingerprints
    "avg_rate": 2.3,                # Exponentially weighted moving average RPM
    "avg_payload_size": 245.0,      # EWMA of request body sizes
    "timestamps_1m": [1693..., ...]  # Recent request timestamps for rate calc
}
```

### 2.4 Feature Extraction (`features.py`)

**Purpose:** Computes a 7-dimensional feature vector for each incoming request, using the identity's behavioural baseline as context.

**Signal computation logic:**

| Signal | Formula | Edge Case Handling |
|---|---|---|
| `request_frequency` | `len(timestamps_in_last_60s) / max(avg_rate, 1)`, clamped to [0,1] | If `avg_rate == 0` → clamp avoids division by zero |
| `endpoint_novelty` | `1.0` if endpoint not in baseline's endpoint set AND `total > 0`; else `0.0` | If `total == 0` (cold identity), novelty is `0.0` — prevents false positives on first-ever request |
| `geo_change` | `1.0` if geo not in baseline's geo set AND `total > 0`; else `0.0` | Same cold-identity protection |
| `device_change` | `1.0` if device not in baseline's device set AND `total > 0`; else `0.0` | Same cold-identity protection |
| `token_freshness` | `min(token_age_seconds / 3600, 1.0)` | Normalized to [0,1]; fresh tokens (< 1 hour) score low |
| `payload_size_zscore` | `abs(payload_size - avg_payload_size) / max(std_dev, 1)`, clamped to [0,1] | If no prior payload data → 0.0 |
| `request_rate` | `actual_rpm / 60.0`, clamped to [0,1] | Normalized to a 60 RPM max |

### 2.5 Rule Layer (`rules.py`)

**Purpose:** Deterministic, explainable hard triggers that can short-circuit ML scoring.

**Four active rules:**

| Rule Code | Condition | Score Added | Description |
|---|---|---|---|
| `impossible_travel` | `geo_change == 1.0 AND total >= 3` | +60 | Source region never seen, and identity has enough history for this to be meaningful |
| `privilege_escalation_attempt` | `endpoint_novelty == 1.0 AND endpoint in ADMIN_PREFIXES AND total >= 3` | +60 | First-ever access to a sensitive path (/admin/*, /payments/*) |
| `token_used_after_revocation` | `session_id in revoked_sessions` | = 100 | Absolute hard-circuit — revoked token reuse is always score 100 |
| `device_and_geo_change` | `device_change == 1.0 AND geo_change == 1.0` | +15 | Simultaneous device and geo change (adds to impossible_travel when both fire) |

**ADMIN_PREFIXES:** `/admin`, `/payments`, `/internal`

### 2.6 ML Engine (`ml_engine.py`)

**Purpose:** Wraps scikit-learn's `IsolationForest` for anomaly scoring.

**Training:**
- 4,000 synthetic "normal" feature vectors generated by `seed/train_baseline.py`
- Each vector has 7 features with distributions matching expected legitimate traffic
- Training time: ~150ms on a standard laptop CPU

**Inference:**
- Input: 7-dimensional feature vector (output of `features.py`)
- `decision_function()` returns a float in approximately [-0.20, 0.25]
- Score normalization: `anomaly_score = (1.0 - decision_function_output) * 50`, clamped to [0, 100]
- Normal traffic → low score (10-20); anomalous traffic → high score (60-100)

### 2.7 Decision Engine (`decision.py`)

**Purpose:** Blends rule and ML scores into a final risk score, maps to a tier, maps to an enforcement action.

**Score blending formula:**
```
final_score = max(rule_score, blended_score)
where blended_score = rule_score * 0.45 + ml_score * 0.55
```

The `max()` ensures hard triggers always dominate — a rule score of 75 won't be diluted by a low ML score.

**Tier mapping (configurable via `/sentinelx/policy`):**
```
score ≤ 30  → allow    → proxy to origin
score ≤ 60  → step_up  → return OTP challenge
score ≤ 85  → restrict → rate-limit + degrade to read-only
score > 85  → revoke   → kill session immediately
```

### 2.8 Reverse Proxy (`proxy.py`)

**Purpose:** Forwards allowed requests to the origin service via `httpx`.

- Uses `httpx.AsyncClient` with connection pooling
- Forwards all request headers (minus hop-by-hop)
- Returns the origin's response with added SentinelX headers (`x-sentinelx-risk-score`, `x-sentinelx-tier`, `x-sentinelx-latency-ms`)
- Only executes when the decision tier is `allow`

### 2.9 Gateway Router (`routers/gateway.py`)

**Purpose:** Orchestrates the full request lifecycle.

**Pipeline per request:**
1. Extract request context from headers
2. Check session revocation (→ instant 401 if revoked)
3. Extract features from context + baseline
4. Evaluate rules against features
5. Score features with ML engine
6. Blend scores and make decision
7. Update baseline with this request's data
8. Update risk state
9. Log alert (if tier ≠ allow)
10. Execute enforcement action (proxy / challenge / rate-limit / kill)

### 2.10 Control-Plane Router (`routers/sentinelx.py`)

**Purpose:** Exposes management APIs for the dashboard and external tooling.

Seven endpoints, all secured for demo use (production would add RBAC):
- Risk query, policy read/write, session revocation, alert feed, traffic simulation, system stats

---

## 3. Data Flow Diagram

```
 Request arrives
       │
       ▼
 ┌─────────────┐     ┌──────────────┐
 │ Parse headers│────>│ Is session   │──YES──> 401 + score=100
 │ into Context │     │ revoked?     │
 └─────────────┘     └──────┬───────┘
                            │ NO
                            ▼
                     ┌──────────────┐     ┌─────────────┐
                     │ Load baseline│<───>│ State Store  │
                     │ for identity │     │ (Redis/Mem)  │
                     └──────┬───────┘     └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ Extract 7    │
                     │ features     │
                     └──────┬───────┘
                            │
                   ┌────────┴────────┐
                   │                  │
                   ▼                  ▼
            ┌──────────┐     ┌──────────────┐
            │ Rule     │     │ ML Engine    │
            │ Layer    │     │ (IsolationF) │
            │ 4 rules  │     │ predict()    │
            └────┬─────┘     └──────┬───────┘
                 │                   │
                 ▼                   ▼
            rule_score          ml_score
                 │                   │
                 └────────┬──────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │ Blend scores │
                   │ max(rule,    │
                   │  0.45r+0.55m)│
                   └──────┬───────┘
                          │
                          ▼
                   ┌──────────────┐
                   │ Map to tier  │
                   │ + action     │
                   └──────┬───────┘
                          │
              ┌───────────┼───────────┬──────────┐
              ▼           ▼           ▼          ▼
           allow       step_up    restrict    revoke
           proxy       OTP req    rate-limit  kill session
           to origin   + 401      + 429       + 401
```

---

## 4. Security Properties

| Property | Implementation |
|---|---|
| **Defence in depth** | Rule layer catches known-bad patterns; ML layer catches unknown anomalies |
| **No security by obscurity** | All decision reasons are logged and surfaced to analysts |
| **Fail-secure** | If scoring fails, the request is blocked (not allowed) by default |
| **Least privilege** | Even a valid token gets only the access its behavioural baseline supports |
| **Separation of concerns** | Scoring pipeline is decoupled from enforcement — changing rules doesn't require proxy changes |

---

## 5. Performance Characteristics

| Metric | Measured Value | Budget |
|---|---|---|
| Feature extraction | 1-2ms | — |
| Rule evaluation | <1ms | — |
| ML inference | 1-2ms | — |
| State store read/write | 1-3ms (in-memory) / 2-5ms (Redis) | — |
| **Total pipeline overhead** | **6-10ms** | **< 15ms p95** |
| ML training at startup | ~150ms | — |
| Training data size | 4,000 vectors × 7 features | — |
| Memory footprint (per identity baseline) | ~2KB | — |

---

*Technical reference for NexHack 2.0 — SentinelX Team*
