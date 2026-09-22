# SentinelX Integration Guide

Zero Trust protection for any SaaS application in 4 steps.

## What You Get

Any service registered with SentinelX automatically receives:
- **ML + Rule-based risk scoring** on every request (7-signal feature vector)
- **Automatic enforcement** — ALLOW / STEP-UP / RESTRICT / REVOKE — without touching your backend
- **Behavioral baselining** per identity
- **Incident logging** and real-time risk dashboard

---

## Step 1 — Register Your Service in `services.json`

Open `gateway/services.json` and add your service block:

```json
{
  "services": {
    "my-saas": {
      "base_url": "http://localhost:9005",
      "docker_base_url": "http://my-saas:9005",
      "description": "My SaaS application",
      "endpoints": {
        "/dashboard":        { "sensitivity": "normal",    "auth_required": true },
        "/billing/pay":      { "sensitivity": "sensitive", "auth_required": true },
        "/admin/settings":   { "sensitivity": "admin",     "auth_required": true },
        "/signup":           { "sensitivity": "normal",    "auth_required": false },
        "/login":            { "sensitivity": "normal",    "auth_required": false }
      }
    }
  }
}
```

**Sensitivity tiers:**
| Tier | Typical verdict for normal users | Example endpoints |
|------|----------------------------------|-------------------|
| `normal` | `allow` | `/profile`, `/orders`, `/dashboard` |
| `sensitive` | `step_up` for low-privilege users | `/payments/*`, `/orders/place` |
| `admin` | `step_up`/`revoke` for non-admins | `/admin/*`, `/users` |

**`auth_required: false`** — Routes that have no identity yet (signup, login) are forwarded directly without identity-based scoring. They receive simple IP rate-limiting only.

> No gateway code changes required. Restart the gateway to pick up the new config.

---

## Step 2 — Attach Identity Headers to Every Request

Every post-login request from your frontend must include:

```http
x-identity-id: <user_id>
x-session-id: <session_token>
x-nonce: <unique_per_request_value>
```

The easiest way is to drop in the client library (Step 3).

---

## Step 3 — Drop in `sentinelx-client.js`

Copy `orbit/app/static/js/sentinelx-client.js` into your frontend. Then:

```javascript
// 1. Create a client instance after the user logs in
const sx = new SentinelXClient({
    gatewayBase: 'http://localhost:8080/gateway/my-saas',
    identityId: 'user_123',
    sessionId: 'sess_abc',
});

// 2. Register enforcement handlers
sx.onStepUp((data) => {
    // Show MFA modal, use data.challenge.demo_otp for the presenter OTP
    console.log('Demo OTP:', data.challenge.demo_otp);
    showMfaModal(data.challenge.challenge_id);
});
sx.onRestrict((data) => { showRateLimitBanner(); });
sx.onRevoke((data)   => { forceLogout(); });

// 3. Replace all fetch() calls with sx.call()
const profile = await sx.call('/dashboard');
const order   = await sx.call('/billing/pay', 'POST', { amount: 99 });

// 4. Verify OTP from the MFA modal
const result = await sx.verifyOtp(userEnteredCode);
// result: 'ok' | 'expired' | 'wrong' | 'used'
```

That's the complete frontend integration. No other wiring needed.

---

## Step 4 — Register New Users with the Gateway on Signup

When a new user signs up, call the gateway's user registration endpoint **before** their first post-auth request:

```python
import httpx

async def on_signup(user_id: str, name: str, role: str):
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            await client.post("http://localhost:8080/sentinelx/users", json={
                "identity_id": user_id,
                "name": name,
                "role": role,
            })
        except Exception as e:
            # Non-fatal — log it, don't block the signup
            print(f"WARNING: SentinelX registration failed: {e}")
```

This ensures the gateway tracks their behavior from the very first request and applies cold-start neutral scoring (no false positives for new accounts).

---

## Test That Enforcement Works

```bash
# 1. Verify your service appears in the registry
curl http://localhost:8080/sentinelx/services

# 2. Test a normal request (should ALLOW)
curl -X GET http://localhost:8080/gateway/my-saas/dashboard \
  -H "x-identity-id: user_123" \
  -H "x-session-id: sess_abc" \
  -H "x-nonce: n_001"

# 3. Test a sensitive request from a low-privilege user (should STEP-UP → 401)
curl -X POST http://localhost:8080/gateway/my-saas/billing/pay \
  -H "x-identity-id: user_123" \
  -H "x-session-id: sess_abc" \
  -H "x-nonce: n_002" \
  -H "Content-Type: application/json" \
  -d '{"amount": 99}'
# Expected: HTTP 401 with {"error":"step_up_required","challenge":{...}}
```

## Reference Implementation

See `orbit/` for a complete working example. Orbit is **not special-cased** in the gateway — it runs through the same `services.json` config path that your new service will use.
