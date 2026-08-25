# Changelog — SentinelX

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] — 2026-08-22

### Added
- **Core Gateway**
  - FastAPI reverse-proxy gateway with inline request scoring
  - 7-signal behavioural feature extraction per request
  - 4-rule deterministic hard-trigger layer (impossible travel, privilege escalation, token revocation, device+geo change)
  - Scikit-learn Isolation Forest ML anomaly detection engine
  - Two-layer score blending (rules 45% + ML 55%) with graduated response
  - Four-tier enforcement: allow → step-up → restrict → revoke
  - Full decision explainability with structured reason objects

- **State Management**
  - Async state store interface with dual backend support
  - InMemoryStore for zero-dependency local demos
  - RedisStore for production persistence with TTL support
  - Per-identity rolling behavioural baselines (endpoints, geos, devices, rates)
  - Session revocation with reuse detection

- **Control Plane API**
  - `GET /sentinelx/risk/{identity_id}` — live risk query
  - `GET /sentinelx/policy` + `POST /sentinelx/policy` — dynamic threshold tuning
  - `POST /sentinelx/revoke/{session_id}` — session revocation
  - `GET /sentinelx/alerts` — explainable alert feed
  - `POST /sentinelx/simulate` — 5-scenario traffic simulator
  - `GET /sentinelx/stats` — system metadata

- **Dashboard**
  - Liquid Glass theme (dark mode, frosted glass panels, depth hierarchy)
  - Real-time SVG risk gauge with colour-banded arcs
  - Identity selector with live polling
  - 5-button traffic simulator panel
  - Dynamic policy threshold editor
  - Scrollable explainable alert ticker
  - Per-identity request audit ledger

- **Demo Service**
  - 5-endpoint toy microservice (/health, /profile, /orders, /admin/users, /payments/transfer)
  - 4 fake users with role-based responses

- **Testing**
  - 9-stage end-to-end pipeline test suite
  - Per-run randomized identity IDs for full idempotency
  - Unit tests for feature extraction, rules, ML engine, and decision engine

- **Infrastructure**
  - Dockerfiles for both gateway and demo-service
  - docker-compose.yml with Redis, health checks, and dependency ordering
  - Google Cloud Run deployment documentation
  - Environment-driven configuration with safe defaults

- **Documentation**
  - Comprehensive README with badges, architecture diagrams, and evaluation criteria mapping
  - Master System Document (complete design reference)
  - Setup & Run Guide (Options A + B)
  - Demo Script with 5-minute narration and Q&A preparation
  - Architecture Deep-Dive document
  - Troubleshooting Guide
  - Operational Analysis & Sign-Off Report
  - Contributing Guidelines
  - Security Policy
  - MIT License

### Fixed
- Test idempotency issue where shared identity state caused false failures on warm servers
- Windows cp1252 Unicode encoding issue in test output

---

*SentinelX — NexHack 2.0*
