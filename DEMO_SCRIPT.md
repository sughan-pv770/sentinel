# SentinelX — Live Demo Narration Script

> **Duration:** 5 minutes  
> **Audience:** NexHack 2.0 Mentor Panel  
> **Date:** 5 September 2026  
> **Prerequisites:** Both services running (`demo-service` on :9000, `gateway` on :8080)

---

## Pre-Demo Checklist

- [ ] Both terminal windows are running (demo-service and gateway)
- [ ] Browser open to `http://localhost:8080` (Gateway dashboard)
- [ ] Dashboard identity selector set to `u_alex — Alex Rao, customer`
- [ ] Risk gauge shows "—" or a low score (clean state preferred)
- [ ] Screen shared with mentor panel

---

## Slide 1 — The Hook (0:00 – 0:30)

**[Speaker — do NOT show dashboard yet, start with a verbal hook]**

> "Every API security system today answers the same question: *is this token valid?* And that's the wrong question. A stolen session token is perfectly valid — it's real, it's not expired, it passes every firewall and WAF check. The right question is: *is this behaviour consistent with who this token claims to be?*"
>
> "That's what SentinelX does. It sits between your users and your microservices, and on every single API request — not just at login — it asks: does this still look like you?"

---

## Slide 2 — The Problem (0:30 – 1:15)

> "Modern microservice architectures have three critical blind spots:"
>
> **[Count on fingers as you say each one]**
>
> 1. **Static tokens grant unlimited trust.** A valid JWT is indistinguishable from a stolen JWT. Once you're past the door, you're in.
>
> 2. **Service-to-service traffic is implicitly trusted.** Inside a Kubernetes cluster, if one pod is compromised, it can reach every internal API — no further authentication required.
>
> 3. **Rate limiters are static.** A fixed threshold of 100 requests per minute doesn't know that *this specific user* normally makes 5. An attacker who stays at 90 won't trigger anything.
>
> "The average cost of an API-related data breach hit $4.45 million last year. Static perimeter security is fundamentally broken for distributed architectures."

---

## Slide 3 — Live Demo: Normal Traffic (1:15 – 1:45)

**[Switch to browser — show the dashboard]**

> "Let me show you how SentinelX actually works. This is our Runtime Trust Console — it polls a live FastAPI gateway in real-time."

**[Point to the identity selector: `u_alex — Alex Rao, customer`]**

> "We're watching Alex Rao, a normal customer. Watch what happens when Alex makes a standard API request."

**[Click "Normal traffic" button]**

> "The request flows through SentinelX's feature extractor — it computes 7 behavioural signals — then through our two-layer risk engine. The rule layer finds no triggers. The Isolation Forest ML model sees this matches Alex's baseline behaviour."

**[Point to gauge showing a low green score, ~10-15]**

> "Risk score: 12 out of 100. Tier: **allow**. The request was proxied directly to the origin service — zero friction. This is what 99% of legitimate traffic looks like."

---

## Slide 4 — Live Demo: Attack Scenario #1 — Impossible Travel (1:45 – 2:30)

> "Now let's simulate a real attack. Someone steals Alex's session token and uses it from Russia, on a totally different device."

**[Click "Impossible travel" button]**

> "Watch the gauge."

**[Gauge swings to red, shows score 79-100, tier = restrict or revoke]**

> "Instantly: score jumps to 79. Tier: **restrict** — or even **revoke** depending on the policy. Look at the alert ticker..."

**[Point to the alert card that appeared on the right side]**

> "Here's the key differentiator — explainability. The system doesn't just say 'blocked'. It says **why**:"
>
> - *'Source geo RU-MOW never seen before for this identity'*  
> - *'Device fingerprint and source geo both changed simultaneously'*
>
> "This is what a security analyst needs. Not a number — a diagnosis."

---

## Slide 5 — Live Demo: Attack Scenario #2 — Privilege Escalation (2:30 – 3:15)

> "One more scenario. What if a normal customer suddenly tries to access an admin endpoint they've never touched before?"

**[Click "Privilege escalation" button]**

> "Watch..."

**[Point to the alert showing `privilege_escalation_attempt`]**

> "Score: 74. Tier: **restrict**. Reason: *'First-ever access to sensitive endpoint /payments/transfer from this identity.'* SentinelX knows this endpoint is sensitive and that this user has zero history with it."
>
> "Most importantly — we didn't block a regular admin who accesses this every day. We blocked *this user's first-ever attempt*. That's the difference between static rules and behavioural trust."

---

## Slide 6 — Architecture Deep-Dive (3:15 – 3:45)

> "Under the hood, every request goes through a 7-stage pipeline in under 15 milliseconds:"
>
> 1. **Context extraction** — we pull the identity, session, geo, and device from headers
> 2. **Feature extraction** — 7 signals computed against a rolling behavioural baseline
> 3. **Rule evaluation** — 4 deterministic hard triggers (impossible travel, privilege escalation, token revocation, simultaneous device+geo change)
> 4. **ML scoring** — a trained Isolation Forest maps the feature vector to an anomaly score
> 5. **Score blending** — rules (45%) + ML (55%) → final risk score 0-100
> 6. **Decision & enforcement** — score maps to a tier, tier maps to an action
> 7. **Audit logging** — full structured JSON trace for compliance
>
> "The key innovation is the *two-layer engine*. Rules catch the obvious attacks deterministically. The ML model catches the subtle anomalies that no rule would find — slow privilege escalation, gradual behavioural drift, novel attack patterns."

---

## Slide 7 — Live Demo: Policy Tuning (3:45 – 4:00)

**[Scroll to "03 — Policy thresholds" panel]**

> "And these thresholds are tunable at runtime. Right now, 'allow' is anything under 30. If my security team wants to be stricter..."

**[Change "allow" from 30 to 15 and click "Apply policy"]**

> "Done. No restart. No redeployment. Every request from this moment uses the new thresholds. This is Zero Trust that adapts in real-time."

**[Reset thresholds back to defaults: 30 / 60 / 85]**

---

## Slide 8 — Tech Stack & Why (4:00 – 4:15)

> "Tech stack — deliberately lightweight:"
>
> - **FastAPI** — async Python, handles thousands of requests per second with sub-millisecond routing
> - **Scikit-learn Isolation Forest** — unsupervised ML that requires no labelled attack data and no GPU. Trains in 150 milliseconds on startup
> - **Redis** — sub-millisecond state reads for behavioural baselines. Falls back to in-memory for laptop demos
> - **Docker** — reproducible three-container stack with health checks
>
> "No TensorFlow. No Kubernetes. No cloud dependency to run the demo. The entire system starts on a laptop in under 3 seconds."

---

## Slide 9 — Scalability & Future (4:15 – 4:45)

> "Scaling: the gateway is stateless — all state lives in Redis. Cloud Run autoscales the compute; Memorystore scales the state. Add more instances as traffic grows, zero architecture change."
>
> "Roadmap:"
>
> - **Next**: Wire real OTP providers (Twilio/SendGrid) to the step-up challenge
> - **Medium-term**: Upgrade from Isolation Forest to LSTM sequence models for temporal pattern detection. Export alerts to Splunk/Elastic via SIEM webhooks
> - **Long-term**: Federated cross-service baselines to detect coordinated multi-service attacks. Multi-cloud deployment — same container on AWS, Azure, or GCP

---

## Slide 10 — Close (4:45 – 5:00)

> "SentinelX is **continuous, adaptive, explainable Zero Trust**."
>
> "Not a bigger firewall. Not a stricter rate limiter. A system that actually understands whether the entity behind the token is still the entity you authenticated."
>
> "Thank you. We're ready for questions."

---

## Q&A Preparation — Anticipated Questions & Answers

### Q: "How does the Isolation Forest work without labelled attack data?"

> "Isolation Forest is an *unsupervised* anomaly detector. It doesn't learn 'what attacks look like' — it learns 'what normal looks like.' It builds random decision trees that isolate data points. Normal points require many splits to isolate; anomalies require very few. So it detects any behaviour that deviates from the baseline — including attack types we've never seen before. We train it on 4,000 synthetic normal requests at startup, which takes ~150ms."

### Q: "What's the false positive rate?"

> "Lower than static rules because the baseline is per-identity. A developer who normally hits 50 endpoints a day won't trigger 'endpoint novelty' alerts that would fire for a customer who only uses `/profile`. The Isolation Forest adapts to each user's actual behaviour pattern. In our testing, normal traffic consistently scores 10-16 out of 100 — well below the allow threshold of 30."

### Q: "Can this handle production-scale traffic?"

> "Yes. The gateway is stateless — FastAPI handles thousands of requests/second per instance. State lives in Redis, which provides sub-millisecond reads. On Cloud Run, it autoscales horizontally. The < 15ms overhead per request is verified — feature extraction, ML inference, and decision all fit within that budget."

### Q: "What if the ML model is wrong and blocks a legitimate user?"

> "That's exactly why we use graduated response instead of binary blocking. A borderline anomaly doesn't get blocked — it gets a step-up challenge (MFA). The user can prove their identity and continue. Only extreme anomalies (score > 85) trigger restrict/revoke. And thresholds are tunable at runtime — a security team can adjust sensitivity without code changes."

### Q: "What's mocked vs real in this demo?"

> "Being transparent: **Real** — the reverse proxy, feature extraction, Isolation Forest ML, rule triggers, enforcement actions, behavioural baselines, the dashboard. **Mocked** — GeoIP resolution (we use header-based mock geo instead of IP lookup) and OTP delivery (the step-up returns a challenge object but doesn't actually send an SMS). Both are documented in our master system doc. The mocked pieces are < 50 lines each to wire up to real providers."

### Q: "How is this different from a WAF?"

> "A WAF inspects the *content* of requests — looking for SQL injection, XSS, malformed payloads. SentinelX inspects the *behaviour* of identities — looking for anomalous patterns in who is making requests, how fast, from where, to which endpoints. They're complementary, not competing. SentinelX can sit behind a WAF, adding the behavioural trust layer that WAFs fundamentally cannot provide."

### Q: "Why Python/FastAPI instead of Go or Rust for a security gateway?"

> "For the hackathon MVP, Python gives us direct access to scikit-learn's Isolation Forest without an IPC boundary, and FastAPI's async performance is more than sufficient for demo-scale traffic (thousands of RPS). In a production evolution, the scoring engine could be extracted as a gRPC service written in any language — the architecture is pluggable. The < 15ms overhead we're hitting in Python already meets our latency budget."

---

## Emergency Fallback

If the live demo encounters any issues during the presentation:

1. **Dashboard not loading**: Switch to terminal and show `curl` commands with live output
2. **Services crashed**: Have a pre-recorded terminal session ready showing all 9 test stages passing
3. **Score not changing**: Select a different identity from the dropdown and try again
4. **Network issues**: Run everything on `127.0.0.1` — no external network required

---

*Prepared for NexHack 2.0 — SentinelX Team*
