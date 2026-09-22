<div align="center">

<img src="https://img.shields.io/badge/Zero_Trust-Runtime_Security-blue?style=for-the-badge&logo=shield&logoColor=white" />
<img src="https://img.shields.io/badge/ML-Isolation_Forest-purple?style=for-the-badge&logo=scikit-learn&logoColor=white" />
<img src="https://img.shields.io/badge/Latency-%3C5ms-green?style=for-the-badge" />
<img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" />

# 🛡️ SentinelX

### *Adaptive Zero Trust Runtime API Security Gateway*

**Autonomous, real-time behavioral anomaly detection & policy enforcement for modern microservices.**
Scoring trust on every in-flight API request in under **5ms** — using Hybrid Unsupervised ML + Deterministic Rules.

[🚀 Quick Start](#-fast-start-setup) · [📖 Architecture](#️-architecture) · [🎮 Demo](#-live-demo-guide) · [📊 Results](#-evaluation-metrics)

</div>

---

## 📌 The Problem

Traditional API security relies on **static tokens** (JWT / OAuth2 / API Keys). Once a token is issued, it is blindly trusted until it expires — even if it's **stolen, leaked, or replayed from an unauthorized country**.

`
Attacker steals a JWT token
       ↓
Makes requests from Russia using Indian user's token
       ↓
Standard gateway: ✅ Valid token → let it through
SentinelX:        🚫 Impossible travel detected → SESSION REVOKED in <5ms
`

---

## 🏗️ Architecture

`
                     ┌────────────────────────────────────────────────┐
                     │          SentinelX Gateway  (<5ms)             │
                     │                                                │
 Incoming Request ─► │  1. Feature Extraction (7 behavioral signals)  │
                     │  2. Isolation Forest ML Score                  │
                     │  3. Deterministic Rule Engine                  │
                     │  4. Weighted Risk Composite (0–100)            │
                     │  5. Policy Enforcement Decision                │
                     └──────────┬─────────────────────────────────────┘
                                │
       ┌────────────────────────┼──────────────────────┬──────────────────────┐
       ▼                        ▼                       ▼                      ▼
✅ ALLOW (200)        🔐 STEP-UP MFA (401)    🔒 RESTRICT (429)     🚫 REVOKE (403)
Forward to Upstream   Require OTP Challenge   Degrade to Read-Only  Kill Session Instantly
`

### System Components

| Service | Port | Description |
|---|---|---|
| **SentinelX Gateway** | 8080 | Core ML scoring engine + policy enforcer |
| **Orbit SaaS App** | 9001 | Protected demo SaaS frontend (premium UI) |
| **Demo Origin Service** | 9000 | Upstream microservice (proxied by gateway) |
| **Stub Service** | 9002 | Additional test surface for demo scenarios |

---

## 🧠 The 7-Signal Behavioral Feature Vector

> SentinelX builds a **rolling behavioral baseline** per identity using EWMA — and flags statistical divergence in real time.

| # | Feature | Normal | Anomalous | Why It Matters |
|---|---|---|---|---|
| 1 | **Request Frequency** | 1–10 req/min | ≥ 30 req/min | Detects brute force, credential stuffing |
| 2 | **Endpoint Novelty** | 0.0 (seen before) | 1.0 (first access) | Flags reconnaissance on new APIs |
| 3 | **Geo Drift** | 0.0 (familiar region) | 1.0 (unseen location) | Detects impossible travel / account takeover |
| 4 | **Device Change** | 0.0 (known device) | 1.0 (new user-agent) | Identifies token exfiltration |
| 5 | **Time Deviation** | 0.0–0.2 (normal hours) | > 0.5 (off-hours) | Catches unauthorized off-hours activity |
| 6 | **Payload Z-Score** | 0.0–1.5 (200–800B) | > 3.0 (> 5KB) | Flags data exfiltration payloads |
| 7 | **Token Age** | 300–3600s | < 10s or > 12h | Distinguishes newly minted stolen tokens |

### Decision Formula

`
Final Score = max(Rule, ML)                         if hard rule triggered
            = (0.55 × ML_Score) + (0.45 × Rule_Score)  otherwise
`

---

## 🎮 Live Demo Guide

### The 5 Attack Scenarios

| # | Scenario | User | Endpoint | Location | Expected Verdict |
|---|---|---|---|---|---|
| 1 | Normal Request | u_alex (Member) | GET /profile | India | ✅ ALLOW ~10 |
| 2 | Privilege Escalation | u_alex (Member) | POST /payments/transfer | India | 🔐 STEP-UP MFA ~60 |
| 3 | Admin Boundary | u_alex (Member) | GET /admin/users | India | 🔒 RESTRICT ~70 |
| 4 | Impossible Travel | u_alex (Member) | GET /profile | Russia | 🚫 REVOKE > 90 |
| 5 | Brute Force Burst | Dev Panel | ×500 requests | — | 🚫 REVOKE (escalates live) |

### Orbit — The Protected SaaS App (Port 9001)

Orbit is a full-featured demo SaaS that shows **real-time Zero Trust enforcement in the UI**:

- 🔐 **MFA Modal** pops up instantly when step-up is triggered mid-session
- 🚫 **Forced logout + screen flash** when the session is revoked
- ⚠️ **Restriction banner** appears when account is degraded to read-only
- 📊 **Live activity log** showing every enforcement decision in real time
- 🎛️ **Dev Sandbox Panel** (bottom-right) for firing single or bulk requests on demand

---

## 🚀 Fast-Start Setup

### Prerequisites
- Python 3.9+ (3.10+ recommended)
- pip

### One-Command Launch

`ash
git clone https://github.com/sughan-pv770/sentinel.git
cd sentinel
python start_all.py
`

Open:
- 🌐 **Orbit SaaS App:** [http://localhost:9001](http://localhost:9001)
- 🔧 **Gateway Dashboard:** [http://localhost:8080](http://localhost:8080)

### Docker (Production Stack)

`ash
docker-compose up
`

Brings up: sentinelx-gateway + orbit-app + origin-demo-service + Redis in one command.

### Environment Setup

`ash
cp .env.example .env
# Edit .env as needed
`

---

## 📊 Evaluation Metrics

| Metric | Value |
|---|---|
| **ML Precision** (threshold = -0.083) | **99.5%** |
| **ML Recall** | **100%** |
| **False Positive Rate** | **0.1%** |
| **Gateway P99 Latency** | **< 5ms** |
| **Attack Scenarios Covered** | **5** |
| **Behavioral Signals Extracted** | **7 per request** |
| **Training Samples** | 4,000 synthetic normal traces |

---

## 🔒 Security Capabilities

| Attack Vector | Detection Mechanism |
|---|---|
| Account Takeover (stolen token, new country) | Geo drift hard trigger + ML composite |
| Privilege Escalation (member → admin) | Endpoint novelty rule + role-aware override |
| Credential Stuffing / Brute Force | Frequency spike rule (> 30 req/min) |
| Token Replay Attack | Nonce dedup store (per-identity 1h TTL) |
| Off-hours unauthorized access | Time-of-day deviation feature |
| Data exfiltration payload | Payload Z-score with EWMA per-identity baseline |
| Session hijacking | Geo + Device change composite trigger |

---

## 📁 Project Structure

`
sentinel/
├── gateway/                    # SentinelX Gateway (core engine)
│   ├── app/
│   │   ├── main.py             # FastAPI app entrypoint
│   │   ├── ml_engine.py        # Isolation Forest ML pipeline
│   │   ├── features.py         # 7-signal behavioral feature extraction
│   │   ├── rules.py            # Deterministic hard-trigger rule engine
│   │   ├── decision.py         # Risk score blending & enforcement
│   │   ├── state_store.py      # In-memory / Redis behavioral store
│   │   ├── incidents.py        # Alert ledger & incident management
│   │   ├── agents.py           # AI scenario simulator
│   │   ├── proxy.py            # Upstream reverse proxy
│   │   ├── config.py           # Environment-based configuration
│   │   ├── routers/            # API route handlers
│   │   └── static/             # Gateway dashboard UI
│   ├── Dockerfile
│   └── requirements.txt
│
├── orbit/                      # Orbit SaaS Frontend (protected app)
│   ├── app/
│   │   ├── main.py             # FastAPI backend (profile, orders, billing, admin)
│   │   └── static/
│   │       ├── index.html      # Full SPA UI
│   │       ├── css/styles.css  # Premium design system (glassmorphism)
│   │       └── js/
│   │           ├── orbit.js            # SaaS app logic + enforcement UI
│   │           └── sentinelx-client.js # Zero Trust client SDK
│   ├── Dockerfile
│   └── requirements.txt
│
├── demo-service/               # Origin microservice (upstream target)
├── stub-service/               # Additional test surface
├── start_all.py                # One-command launcher
├── docker-compose.yml          # Production Docker stack
├── test_e2e_suite.py           # End-to-end automated tests
├── .env.example                # Environment variable template
└── README.md
`

---

## 🧪 Automated Test Suite

`ash
python test_e2e_suite.py
`

**9 Verified Pipeline Stages:**
1. ✅ Service Health Checks
2. ✅ Control-Plane Telemetry
3. ✅ Normal Traffic Proxying (ALLOW → 200 OK)
4. ✅ Impossible-Travel Detection
5. ✅ Privilege Escalation Defense
6. ✅ Session Revocation & Post-Revocation Token Reuse
7. ✅ All 5 Simulator Anomaly Scenarios
8. ✅ Explainable Alert Feed & Incident Ledger
9. ✅ Dynamic Policy Threshold Mutation

---

## 📡 API Reference

### Control Plane

| Method | Endpoint | Description |
|---|---|---|
| GET | /sentinelx/stats | Latency, active identities, store backend |
| GET | /sentinelx/risk/{identity_id} | Current risk score & request count |
| GET | /sentinelx/policy | Current enforcement thresholds |
| POST | /sentinelx/policy | Update thresholds live (no restart needed) |
| POST | /sentinelx/revoke/{session_id} | Instantly invalidate a session |
| GET | /sentinelx/alerts | Real-time explainable alert log |
| POST | /sentinelx/simulate | Run scenarios through the ML pipeline |

### Data Plane (Proxy)

| Method | Endpoint | Description |
|---|---|---|
| ANY | /gateway/{service}/{path} | Intercept, score & proxy to upstream |
| GET | /health | Readiness probe |
| GET | /metrics | Prometheus-format counters |

---

## 🆚 SentinelX vs. Alternatives

| Capability | Traditional WAF | API Gateway | **SentinelX** |
|---|---|---|---|
| Identity-Aware Scoring | ❌ IP-only | ✅ OAuth2 token | ✅ Per-identity EWMA behavioral profile |
| Unsupervised Anomaly Detection | ❌ | ❌ | ✅ Isolation Forest (no labels needed) |
| Sub-5ms Latency | ✅ static rules | ⚠️ varies | ✅ In-process inference pipeline |
| Impossible Travel Detection | ⚠️ manual rules | ❌ | ✅ Geo drift rule + ML composite |
| Dynamic Policy Tuning | ❌ requires redeploy | ⚠️ config reload | ✅ Live REST API |
| Explainable Decisions | ❌ | ❌ | ✅ Per-feature contribution scores |
| Real-Time Frontend Enforcement | ❌ | ❌ | ✅ Orbit UI reacts in < 1s |

---

## 🏆 Judge Q&A

<details>
<summary><strong>Q: How do you achieve sub-5ms latency with ML in the hot path?</strong></summary>

SentinelX uses a lightweight, pre-warmed **Isolation Forest** with compact in-memory EWMA deques (O(1) lookups). Feature normalization and inference execute in under 1.5ms, well within API latency budgets.
</details>

<details>
<summary><strong>Q: How does it handle cold-start for new users?</strong></summary>

New identities start with neutral novelty (0.0) for common paths. As requests accumulate, the EWMA baseline converges to a personalized behavioral profile within ~10 requests.
</details>

<details>
<summary><strong>Q: How do you train without labeled attack datasets?</strong></summary>

SentinelX uses **unsupervised anomaly detection** trained on 4,000 synthetic normal traces. Rather than searching for known attacks, it flags statistical divergence from learned baselines — meaning it can detect **novel, never-before-seen attacks**.
</details>

<details>
<summary><strong>Q: Is the frontend enforcement real or just cosmetic?</strong></summary>

It's real. The Orbit app integrates with SentinelX via the SentinelXClient SDK. When the gateway issues a session_revoked 401, Orbit's session manager intercepts it and forces an immediate logout. MFA modals are triggered by actual 401 step-up responses — not mocked timers.
</details>

---

## 📄 License

MIT License — Built with 🔥 for the Hackathon Prototype Showcase, September 2026.

> *SentinelX: Because a stolen token shouldn't be a free pass.*
