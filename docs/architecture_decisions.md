# Architecture Decision Records

## ADR-001 — In-Process SSE Over WebSocket

**Status:** Accepted  
**Date:** 2026-09-15

### Context
Real-time session termination must reach the browser the instant the ML engine issues a `revoke` verdict. Two candidates: WebSocket (bidirectional) and SSE (server-push, unidirectional).

### Decision
Use SSE (`GET /api/events/session`, `text/event-stream`).

### Rationale
| | SSE | WebSocket |
|---|---|---|
| Protocol overhead | HTTP/1.1 or HTTP/2, no upgrade | Full WS handshake |
| Proxy / CDN support | ✅ Transparent | ❌ Requires WS passthrough |
| Reconnection | ✅ Browser auto-retries | Manual |
| Use-case fit | Server-push only | Bidirectional |
| NGINX config | proxy-buffering off | ws:// proxy config |

SSE is a better fit because the gateway only pushes events — the browser never sends data on the stream. SSE is also natively supported by the `EventSource` browser API with automatic exponential backoff reconnection.

### Consequences
- NGINX/ALB must have `proxy_buffering off` on the SSE path (documented in Ingress manifest).
- `SSEManager` uses an `asyncio.Queue` per connection — scales to thousands of connections in a single event loop without threads.

---

## ADR-002 — Sliding Window Rate Limiter Over Token Bucket

**Status:** Accepted  
**Date:** 2026-09-15

### Context
The requirement is to detect and block "500+ sudden requests from a single source within a configurable time window."

### Decision
Sliding window counter (Redis sorted set for production; in-memory timestamp list for dev).

### Rationale
- **Smooths out burst detection**: A token bucket would allow 500 requests at the very start of a bucket refill period, then block — which is exactly the surge pattern we want to detect, not allow.
- **Atomic Redis operations**: `ZREMRANGEBYSCORE` + `ZCARD` + `ZADD` in a pipeline is O(log N) and atomic.
- **Configurable**: `SENTINELX_RATE_LIMIT_BURST_CEILING` and `SENTINELX_RATE_LIMIT_WINDOW_SECONDS` are env-driven — no redeploy needed to tighten limits.

### Consequences
- Redis memory usage: O(requests per window) per key. At 500 req/min/identity, ~500 sorted set members. Negligible.
- In-memory fallback uses a Python list per key — acceptable for single-node dev.

---

## ADR-003 — Per-Token JTI Blacklist Over Short-Lived Tokens

**Status:** Accepted  
**Date:** 2026-09-15

### Context
To terminate a specific session immediately, we need to invalidate its JWT before natural expiry. Two options: shorten token TTL (e.g. 5 min) or maintain a JTI blacklist.

### Decision
60-minute access tokens + per-JTI Redis blacklist. Refresh tokens rotate on every use.

### Rationale
- Shortening TTL to 5 min increases Redis traffic (every refresh adds a round-trip) and degrades UX (frequent re-auth prompts).
- JTI blacklist is checked in O(1) via Redis `EXISTS` — negligible overhead per request.
- JTI entries auto-expire from Redis at `JWT_EXPIRE_MINUTES + 1 min`, so no cleanup job is needed.
- Refresh token rotation (old JTI revoked on each use) prevents replay of stolen refresh tokens.

### Consequences
- All protected routes must call `is_jti_revoked(jti)` — this is centralised in `get_current_user()` in `auth.py`.
- Revoked JTI set size is bounded by `active_users × tokens_per_user × TTL`, which is a small Redis footprint.

---

## ADR-004 — ML Inference SLA: 50ms With Circuit Breaker

**Status:** Accepted  
**Date:** 2026-09-15

### Context
The ML scoring step (Isolation Forest) runs synchronously. If the model degrades or the executor is saturated, it could block the entire request pipeline and inflate p95 latency beyond the 15ms gateway overhead budget.

### Decision
Wrap ML inference in an `asyncio.wait_for(timeout=0.050)` call within a circuit breaker (`CLOSED → OPEN → HALF_OPEN`).

### Rationale
- **Timeout (50ms):** Gives the ML model 50ms of the total 15ms *gateway overhead* budget. In practice the model scores in 1-3ms; the 50ms is a safety net for executor saturation.
- **Circuit Breaker:** After 5 consecutive timeouts/errors, the circuit OPENS and all ML calls fast-fail with a neutral fallback score (50/100). The rule engine governs alone during this period.
- **Shadow mode:** `SENTINELX_ML_SHADOW_MODE=true` scores ML but excludes it from the decision — safe for A/B testing new models.

### Consequences
- Circuit breaker state is exposed as a Prometheus gauge (`sentinelx_ml_circuit_state`), enabling alerting on `state = 2 (OPEN)`.
- When the circuit is OPEN, anomaly detection degrades gracefully (rule-only mode) rather than failing completely.

---

## ADR-005 — Adaptive MFA Tied to Risk Score

**Status:** Accepted  
**Date:** 2026-09-15

### Context
Fixed-always-on MFA degrades UX. No-MFA is a security gap. The system needs context-aware MFA that scales with detected risk.

### Decision
Map the blended risk score to an MFA method via the runtime-configurable policy:

| Risk Score | Tier     | MFA Method    |
|------------|----------|---------------|
| 0 – 30     | allow    | None          |
| 31 – 60    | step_up  | Email OTP     |
| 61 – 85    | step_up  | TOTP          |
| 86 – 100   | revoke   | Revoke + TOTP |

### Rationale
- Risk-adaptive MFA minimises friction for low-risk sessions while requiring strong auth for anomalous behavior.
- Thresholds are policy-driven (POST `/sentinelx/policy`) — adjustable at runtime without redeploy.
- TOTP secrets are encrypted at rest (AES-256-GCM via Fernet) in Redis.
- Device trust tokens (30-day bypass) reduce MFA fatigue for trusted devices.

### Consequences
- TOTP enrollment flow is required for users who may reach the "high" risk tier.
- Email OTP requires an email delivery integration (stub ready for SES/SendGrid in `mfa_service.py`).
