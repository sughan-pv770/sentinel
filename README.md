# SentinelX 🛡️
**Adaptive Zero-Trust API Proxy powered by Machine Learning**

*A Hackathon Submission by Sughan Pinto (sughan-pv770)*

![SentinelX Dashboard UI Showcase](gateway/app/static/img/hero.png) <!-- *Placeholder: Please add a screenshot named hero.png to the img folder if possible!* -->

## 🌟 The Vision
Modern APIs are constantly under attack. Traditional security heavily relies on static validation—if an attacker steals an API key, they gain unhindered access. 

**SentinelX** radically transforms API security. It acts as a lightning-fast, transparent reverse proxy that intercepts all incoming traffic to your backend services. Instead of static checks, it leverages a continuous **Machine Learning Isolation Forest Model** paired with a deterministic Rule Engine to evaluate *how* an identity behaves.

If an attacker tries to scrape data (bursting) or attempts lateral movement (privilege escalation), SentinelX instantly reacts by stepping up security (injecting immediate MFA challenges) or outright terminating the connection. **Zero backend code changes required.**

---

## 🚀 Key Features

*   **Machine Learning Anomaly Detection:** Extracts a 7-dimensional behavioral feature vector (token age, geographic distance, pacing, payload payload sizes) from every request and scores it using an Isolation Forest model.
*   **Zero-Trust Enforcement:** Automatically brokers the connection by acting dynamically:
    *   `ALLOW`: Standard transparent proxying (`HTTP 200`).
    *   `STEP-UP`: Injects a mandatory MFA challenge for moderate risk deviations.
    *   `RESTRICT`: Rate-limits and degrades privileges for anomalies.
    *   `REVOKE`: Severely terminates the network session for flagrant attacks.
*   **"Liquid Glass" Dashboard:** A highly interactive, beautifully designed dark-mode web console tracking alerts, ML vector pulses, and proxy telemetry in real-time.
*   **Interactive API Sandbox:** An embedded sandbox to construct live spoofed requests and watch the pipeline react directly in the UI.

---

## 🛠️ Technology Stack
*   **Core Architecture:** Asynchronous Reverse Proxy Pattern.
*   **Backend Server:** [FastAPI](https://fastapi.tiangolo.com/) (Python) + Uvicorn + SQLAlchemy.
*   **Machine Learning Engine:** Scikit-Learn (`IsolationForest`) integrated natively into the core request lifecycle.
*   **UI/Frontend:** Vanilla HTML/CSS/JS with custom Zero-Dependency UI components (Glassmorphism design, CSS grid, SVG animations).
*   **Database:** Configured for PostgreSQL (Cloud) with local SQLite falback.

---

## ⚡ How to Run Locally

SentinelX operates in a separated architecture. You will need to spin up the Origin Service (simulating the vulnerable API) and the Gateway (The SentinelX Proxy + UI).

### 1. Launch the Origin Target Service
```bash
cd demo-service
# Install dependencies
pip install -r requirements.txt
# Run the target backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 9000
```

### 2. Launch the SentinelX Gateway & Security Console
In a new terminal window:
```bash
cd gateway
# Install dependencies
pip install -r requirements.txt
# Point the gateway to the backend origin
export SENTINELX_ORIGIN_BASE_URL="http://localhost:9000"
# Run the gateway
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```
*(Windows Users: Use `set SENTINELX_ORIGIN_BASE_URL="http://localhost:9000"` or `$env:SENTINELX_ORIGIN_BASE_URL` depending on your shell).*

### 3. Monitor and Interact
Open your browser to: **[http://localhost:8080](http://localhost:8080)**

---

## 💡 How it Built for the Hackathon
What originated as a standard proxy grew into a deeply integrated behavior tracking suite. During development, the core technical hurdle was guaranteeing sub-20ms latency while running the ML scoring logic and database logging. 
By utilizing Python's `asyncio` queues, caching behavioral baselines, and offloading heavy tasks to `.add_task()` backgrounds, SentinelX guarantees nearly transparent validation while maintaining ironclad Zero-Trust principles. 

**SentinelX proves that robust, enterprise-grade AI security does not require monolithic refactoring to deploy.**

