# SentinelX — Master System Document
### Adaptive Runtime Zero Trust Security for APIs and Microservices
**NexHack 2.0 · New Delhi · Online Evaluation, 5 September 2026**

---

## 1. Executive summary

SentinelX is a runtime security layer that sits between clients/microservices and the APIs they call. Instead of trusting a request because it carries a valid API key or a session cookie, SentinelX keeps asking, on every request: *does this behaviour still look like the entity we authenticated?* It builds a behavioural baseline per user/service, scores each request against that baseline plus a set of explainable rules, and enforces a graduated Zero Trust response — allow, step-up auth, restrict, or revoke — instead of a binary allow/deny.

This document is the single reference for the team: architecture, components, data model, ML approach, API contracts, deployment plan, demo script, and a mapping of every design choice back to the hackathon's evaluation rubric.

---

## 2. Problem framing (why this matters)

- Perimeter firewalls and static API keys authenticate **once**, at the door. A stolen token or a compromised service account is trusted for its entire lifetime.
- Microservice-to-microservice traffic is usually **implicitly trusted** inside the cluster network — a single compromised pod can pivot laterally with no further checks.
- Traditional WAFs/rate-limiters use **static rules** (fixed thresholds, IP allowlists) that don't adapt to how a specific user or service actually behaves, so they miss slow, low-and-slow anomalies and generate noisy false positives for legitimate bursty traffic.
- SentinelX's bet: **behavioural, continuous, explainable trust scoring** at the runtime layer, cheap enough to run inline on every request.

---

## 3. System architecture

**Request lifecycle (see diagram above):**

1. **Client / service** sends an API request.
2. **SentinelX gateway (FastAPI)** intercepts it as a reverse proxy / sidecar in front of the real microservice.
3. **Feature extraction** pulls behavioural + contextual signals for this request (see §5).
4. **Redis state store** is read for the caller's rolling behavioural profile and current risk state, and written back after scoring.
5. **Risk engine** (rule layer + lightweight ML model) combines signals into a risk score 0–100 with a reason list.
6. **Zero Trust decision engine** maps the score + policy tier to an action.
7. **Response action** is enforced: request forwarded unchanged, step-up challenge returned, request throttled/blocked, or session/token revoked — and an explainable alert is logged/emitted.

### Deployment topology
- SentinelX runs as a **sidecar/reverse-proxy container** per service, or as a **shared gateway** in front of a service mesh — pick sidecar for the demo (simpler to show causally: "this specific service is protected").
- Stateless compute (FastAPI + Scikit-learn) scales horizontally on **Cloud Run**; all cross-instance state (behavioural baselines, risk scores, revoked sessions) lives in **Redis**, so any gateway instance can score any request consistently.
- Images built via **Docker**, pushed to **Google Artifact Registry**, deployed to **Cloud Run** — fits the "cloud-ready, cloud-native" scalability story.

---

## 4. Component breakdown

### 4.1 SentinelX Gateway (FastAPI)
- Reverse-proxy layer: receives the request, forwards to the origin microservice only after a decision is reached.
- Middleware pipeline: `auth context extraction → feature extraction → risk scoring → policy enforcement → proxy/deny → audit log`.
- Adds latency budget target: **<15ms p95 overhead** per request (mock/cache aggressively for demo).

### 4.2 Feature extraction
Signals computed per request, split into three groups:

| Group | Example features |
|---|---|
| **Identity/session** | Token age, token reuse across IPs/devices, time since last privilege check, session idle time |
| **Request pattern** | Endpoint accessed, HTTP method, request frequency (per minute/hour), deviation from the caller's normal endpoint set, payload size anomaly |
| **Contextual** | Source IP/geo change since last request, device/user-agent fingerprint change, time-of-day deviation from baseline, sequence anomalies (e.g. calling an admin endpoint before ever calling a login endpoint) |

### 4.3 Redis state store
- **Behavioural baseline** per identity: rolling window (e.g. last 500 requests / 24h) of endpoint frequency, average request rate, typical geos/devices — stored as compact aggregates (counts, EWMA) not raw logs, so it stays low-latency.
- **Risk state**: current score, decision tier, active restrictions, revoked token list — read on every request, TTL-based expiry for step-up challenges.
- Chosen for **low-latency in-memory access** at request-time — this is the piece that makes "continuous" scoring cheap enough to run inline instead of async/batch.

### 4.4 Risk scoring engine
Two-layer design (this is the core innovation to emphasize in the pitch):

1. **Rule layer** (deterministic, explainable, always-on): hard triggers like privilege escalation attempts, disabled-account token use, or requests to endpoints never seen for that identity — these can short-circuit straight to a high score regardless of the ML output.
2. **ML layer** (Scikit-learn, lightweight): an **unsupervised anomaly detector** — Isolation Forest or a One-Class SVM — trained per-identity or per-role on the behavioural feature vector, since labelled attack data won't exist for a hackathon MVP. Output is an anomaly score, normalized and blended with the rule layer into the final 0–100 risk score.
3. **Score → tier mapping**: e.g. 0–30 allow, 31–60 step-up auth, 61–85 restrict, 86–100 revoke — thresholds configurable per environment/policy.

### 4.5 Zero Trust decision & response engine
| Risk tier | Action | Example |
|---|---|---|
| Low | Allow | Request proxied normally |
| Medium | Step-up authentication | Require MFA/re-auth before proceeding |
| High | Restrict | Rate-limit, block specific endpoints, degrade to read-only |
| Critical | Revoke | Kill session/token immediately, force re-login |

### 4.6 Explainability layer
Every non-allow decision returns/logs a structured reason set, e.g.:
```json
{
  "risk_score": 78,
  "tier": "restrict",
  "reasons": [
    "Request frequency 6x above 7-day baseline",
    "First-ever access to /admin/users from this identity",
    "Source IP changed country twice in 10 minutes"
  ]
}
```
This is what a security analyst — or the demo judges — actually want to see: not just "blocked," but *why*.

---

## 5. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Runtime gateway | FastAPI (Python) | Async, low overhead, easy middleware pipeline for inline scoring |
| Anomaly detection | Scikit-learn (Isolation Forest) | Lightweight, trains fast on tabular behavioural features, no GPU needed |
| State/session store | Redis | Sub-millisecond reads/writes, TTL support for step-up challenges and revocation |
| Containerization | Docker | Reproducible builds, portable across dev/cloud |
| Deployment | Google Cloud Run + Artifact Registry | Serverless autoscaling, pay-per-use, fits "cloud-native, scalable" story |
| Observability (optional stretch) | Structured JSON logs → any log sink | Feeds the explainability layer and a future SOC dashboard |

---

## 6. API surface (MVP)

- `POST /gateway/{service}/**` — proxied application traffic; SentinelX evaluates and forwards.
- `GET /sentinelx/risk/{identity_id}` — current risk score, tier, and recent reasons (for a demo dashboard).
- `POST /sentinelx/policy` — update tier thresholds (admin-only, for demo tunability).
- `POST /sentinelx/revoke/{session_id}` — manual/automatic session revocation.
- `GET /sentinelx/alerts` — recent explainable alerts feed.

---

## 7. Zero Trust response matrix (policy config, illustrative)

```yaml
policy:
  thresholds: { allow: 30, step_up: 60, restrict: 85 }
  hard_triggers:
    - privilege_escalation_attempt
    - token_used_after_revocation
    - impossible_travel   # geo change faster than physically possible
  step_up:
    method: otp
    ttl_seconds: 300
  restrict:
    action: rate_limit
    limit_per_minute: 5
```

---

## 8. Scalability & future scope

- **Horizontal scaling**: gateway is stateless per-instance (Cloud Run autoscale); Redis can move to a managed cluster (Memorystore) as load grows.
- **Federated baselines**: extend per-identity baselines to per-service-mesh baselines for microservice-to-microservice traffic at scale.
- **Model upgrade path**: swap Isolation Forest for a sequence model (e.g. lightweight LSTM/transformer on request sequences) once enough production data exists — architecture doesn't need to change, only the scoring plugin.
- **SOC integration**: export explainable alerts to SIEM tools (Splunk, Elastic) via a webhook.
- **Multi-cloud**: containerized design means the same image runs on AWS Fargate / Azure Container Apps with no code change — only the deployment target changes.
- **Adaptive thresholds**: auto-tune tier thresholds per service based on false-positive feedback loop (human-in-the-loop labelling from the alerts dashboard).

---

## 9. MVP scope for the hackathon timeline

To keep the build achievable before 5 September while still demoing every claim in the problem statement:

1. FastAPI gateway proxying one demo microservice.
2. Feature extraction for 4–5 signals (request frequency, endpoint novelty, geo/device change, token age).
3. Redis-backed rolling baseline per identity.
4. Isolation Forest trained on synthetic/simulated normal traffic + rule-layer hard triggers.
5. Score → tier → action enforcement (allow / step-up mock / restrict / revoke).
6. A minimal dashboard (even a single HTML page or CLI) showing live risk scores and explainable reasons — this is what judges will remember visually.
7. Dockerfile + one successful Cloud Run deploy, to genuinely demonstrate "cloud-ready."

---

## 10. Mapping to evaluation criteria

| Criterion | Weight | How this design addresses it |
|---|---|---|
| Innovation & Originality | 25% | Continuous, per-request adaptive trust scoring instead of one-time auth; graduated response (not binary block) — pitch this as the headline differentiator, not just "we use ML for security" |
| Problem Relevance & Impact | 20% | Directly targets a well-known, current gap: static API keys and perimeter firewalls fail against lateral movement and token misuse in microservice architectures |
| Feasibility | 20% | Every component is a proven, lightweight tool (FastAPI, Scikit-learn, Redis, Docker) — no exotic infra, buildable as a real MVP in hackathon time |
| Technical Approach & Stack | 15% | Clear two-layer risk engine (deterministic rules + lightweight ML), sensible state design (Redis for latency), cloud-native deployment path |
| Clarity & Quality of Presentation | 10% | Use the request-lifecycle diagram as the spine of the pitch; lead with a live demo of a risky request getting stepped-up/blocked with an explainable reason shown on screen |
| Scalability & Future Scope | 10% | Stateless compute + externalized state scales horizontally; explicit upgrade path (sequence models, SIEM integration, multi-cloud) shows the team has thought past the MVP |

---

## 11. Suggested 5-minute pitch structure

1. **Hook (30s)** — one sentence on why "trust once, forever" auth is broken for modern APIs.
2. **Problem (45s)** — static keys/rules vs. today's lateral-movement and token-misuse threats.
3. **Solution walkthrough (90s)** — the request-lifecycle diagram, narrated live.
4. **Live/recorded demo (90s)** — a normal request flows through untouched; a simulated anomalous request (frequency spike + new endpoint) gets step-up'd or blocked, with the explainable reason shown.
5. **Architecture & stack (30s)** — why FastAPI + Redis + Scikit-learn + Cloud Run is the right lightweight combination.
6. **Scalability & roadmap (30s)** — one sentence each on Memorystore scaling, sequence-model upgrade, SIEM export.
7. **Close (15s)** — restate the innovation line: continuous, adaptive, explainable Zero Trust — not a bigger firewall.

---

*Prepared for NexHack 2.0 — SentinelX team.*
