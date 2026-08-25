# Security Policy — SentinelX

## Scope

This security policy applies to the SentinelX runtime gateway, control-plane API, and dashboard.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x (current) | ✅ Yes |

## Reporting a Vulnerability

If you discover a security vulnerability in SentinelX, please report it responsibly:

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. **Email** the team directly with a description of the vulnerability
3. Include: affected component, reproduction steps, potential impact, and suggested fix if you have one
4. We will acknowledge receipt within 48 hours and provide a timeline for resolution

## Security Design Principles

SentinelX is built on the following security principles:

### Fail-Secure
If the scoring pipeline encounters an error, the request is **blocked** (not allowed). We fail secure, never fail open.

### Defence in Depth
Two independent scoring layers (deterministic rules + unsupervised ML) ensure that bypassing one layer doesn't compromise security.

### Least Privilege
Even a valid authentication token only grants access consistent with the identity's behavioural baseline. Accessing a new sensitive endpoint triggers a step-up challenge.

### Explainability
Every security decision includes human-readable reasons. Opaque "blocked" responses are never acceptable.

### No Security by Obscurity
All rule logic, scoring formulas, and threshold configurations are documented and transparent. Security comes from the adaptive behavioural model, not hidden logic.

## Known Limitations (MVP Scope)

These are documented transparently, not hidden:

1. **GeoIP resolution is mocked** — demo uses `x-mock-geo` headers instead of real IP-to-geo lookup. Production deployment would use MaxMind GeoLite2 or similar.

2. **Device fingerprinting is mocked** — demo uses `x-mock-device` headers instead of User-Agent parsing. Production deployment would use a UA parser library.

3. **OTP delivery is not wired** — step-up challenge returns a challenge object but doesn't send a real SMS/email. Integration with Twilio/SendGrid is a straightforward ~50-line addition.

4. **Control-plane API has no RBAC** — all `/sentinelx/*` endpoints are publicly accessible in the demo. Production deployment would add authentication middleware.

5. **No TLS termination** — the demo runs over HTTP. Production deployment would terminate TLS at a load balancer or use `--ssl-keyfile` / `--ssl-certfile` with uvicorn.

---

*SentinelX Team — NexHack 2.0*
