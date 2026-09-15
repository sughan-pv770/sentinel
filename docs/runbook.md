# SentinelX Security Operations Runbook

## Overview
This runbook describes how to operate, monitor, and respond to alerts from the SentinelX Zero Trust Gateway in production.

---

## Health Checks

### Gateway
```
GET https://sentinelx.example.com/health
```
Expected response:
```json
{
  "status": "ok",
  "ml_circuit_breaker": { "state": "CLOSED" },
  "sse_connections": 12,
  "rate_limit_enabled": true
}
```

### Key indicators:
| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| `ml_circuit_breaker.state` | CLOSED | HALF_OPEN | OPEN |
| `sse_connections` | 0–500 | 500–1000 | >1000 |
| p95 request latency | <15ms | 15–50ms | >50ms |

---

## Alert Runbook

### Alert: `ml_circuit_state == 2` (Circuit OPEN)

**Meaning:** The ML engine has failed 5+ consecutive times. All requests now use rule-only scoring — anomaly detection is degraded.

**Response:**
1. Check gateway pod logs: `kubectl logs -n sentinelx -l app=sentinelx-gateway --tail=100`
2. Look for `[circuit_breaker:ml_engine]` entries.
3. If model file corrupt: re-deploy with `kubectl rollout restart deployment/sentinelx-gateway -n sentinelx`
4. To manually reset: `POST /sentinelx/circuit-breaker/reset` (admin token required).
5. Monitor: circuit auto-probes every 30s (HALF_OPEN) — resolves itself if ML recovers.

---

### Alert: `sentinelx_sessions_revoked_total` spike

**Meaning:** The ML engine or rule layer is terminating many sessions in a short window.

**Response:**
1. Check `/sentinelx/alerts` for the triggering reasons.
2. If all from one identity: likely a compromised account — check `/sentinelx/risk/<identity_id>`.
3. If broad across identities: possible false positive from ML model drift.
4. To pause ML decisions without downtime: `POST /sentinelx/policy` with `ml_shadow_mode: true` equivalent — set `SENTINELX_ML_SHADOW_MODE=true` in ConfigMap and restart.

---

### Alert: `sentinelx_rate_limit_hits_total{key_type="identity_surge"}` firing

**Meaning:** One or more identities are exceeding the 500 req/60s burst ceiling.

**Response:**
1. Check which identity: `GET /sentinelx/alerts?limit=20` — look for `rate_burst_surge` reason.
2. Their sessions are already revoked and SSE broadcast fired.
3. If legitimate high-traffic service account: increase ceiling for that identity via policy, or whitelist in `_BYPASS_PREFIXES` in `rate_limit_middleware.py`.

---

### Alert: `sentinelx_request_latency_ms{p95} > 50ms`

**Meaning:** Gateway latency SLA (15ms overhead) exceeded. Usually caused by Redis slowness or ML executor saturation.

**Response:**
1. Check Redis: `kubectl exec -n sentinelx redis-0 -- redis-cli info stats | grep instantaneous_ops`
2. Check ML timing: `sentinelx_ml_inference_latency_ms` histogram in Prometheus.
3. If Redis is slow: scale Redis memory or check for keyspace eviction (`redis-cli info memory`).
4. If ML slow: reduce `SENTINELX_ML_INFERENCE_TIMEOUT_MS` to 30ms to fail faster.

---

## Manual Session Revocation

To immediately revoke all sessions for a specific identity (admin action):
```bash
curl -X POST https://sentinelx.example.com/api/auth/revoke-all/u_alice \
  -H "Cookie: sentinelx_token=<admin_jwt>"
```

This will:
1. Revoke all JTIs and session IDs for `u_alice`
2. Broadcast `session_terminated` via SSE to all active browser tabs
3. Write a revocation audit entry

---

## Scaling

### Scale gateway pods:
```bash
kubectl scale deployment/sentinelx-gateway -n sentinelx --replicas=10
```
The HPA automatically scales between 3–20 replicas based on CPU (70%) and memory (80%).

### Force rollout (zero downtime):
```bash
kubectl rollout restart deployment/sentinelx-gateway -n sentinelx
kubectl rollout status deployment/sentinelx-gateway -n sentinelx
```

---

## Policy Runtime Updates

Update the Zero Trust policy without restarting the gateway:
```bash
curl -X POST https://sentinelx.example.com/sentinelx/policy \
  -H "Content-Type: application/json" \
  -H "Cookie: sentinelx_token=<admin_jwt>" \
  -d '{
    "thresholds": {"allow": 25, "step_up": 55, "restrict": 80},
    "mfa_risk_tiers": {
      "low": null,
      "medium": "email_otp",
      "high": "totp",
      "critical": "totp"
    }
  }'
```

---

## Secrets Management

The following secrets must be set in the `sentinelx-secrets` K8s Secret:

| Key | Description | Generate with |
|-----|-------------|---------------|
| `SENTINELX_JWT_SECRET_KEY` | Access token signing key | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SENTINELX_JWT_REFRESH_SECRET_KEY` | Refresh token signing key | Same as above |
| `SENTINELX_MFA_ENCRYPTION_KEY` | AES-256-GCM key for TOTP secrets | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

**Never commit these to git. Always use K8s Secrets or a secrets manager (HashiCorp Vault, AWS Secrets Manager).**
