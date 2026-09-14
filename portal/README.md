# 🖥️ SentinelX Security Portal & SOC Console

The **SentinelX Portal** is a high-performance Single Page Application (SPA) built with React and Vite. It serves as both the **Security Operations Center (SOC) Command Console** for administrative oversight and the **Identity Self-Service Portal** for individual user telemetry and activity auditing.

---

## 🌟 Key Capabilities

- **Real-Time SOC Command Center**: Live visibility into active requests, latency percentiles, dynamic policy thresholds, and active sessions.
- **Incident & Alert Ledger**: Structured, explainable threat feeds mapping behavioral anomalies to specific security vector signals.
- **Interactive Security Sandbox**: Real-time traffic emulator to test and visualize gateway scoring across varied roles, endpoints, geolocations, and devices.
- **Pipeline Vector Visualizer**: Live 5-stage graphical pipeline showing feature vector extraction, isolation forest ML evaluation, deterministic rules, and composite risk scoring.
- **Identity & Risk Management**: Administrative user registry with role-based policies and user-facing risk profile auditing.

---

## 🚀 Development & Build

### Prerequisites
- Node.js 18+
- npm / yarn / pnpm

### Quick Start

```bash
# Install dependencies
npm install

# Start Vite development server (hot reload enabled)
npm run dev
```
The development server will boot at `http://localhost:5173`.

### Production Build

```bash
# Compile optimized production bundle to /dist
npm run build

# Preview production build locally
npm run preview
```

---

## 📂 Architecture & Directory Structure

```
portal/
├── src/
│   ├── admin/             # SOC Admin Console views (AlertFeed, ApiSandbox, PolicyControl, etc.)
│   ├── student/           # Identity / User views (Activity, RiskProfile, Notifications)
│   ├── auth/              # Authentication context, login, and registration views
│   ├── components/        # Reusable UI widgets, risk gauges, and simulation tools
│   ├── layouts/           # AdminLayout and UserLayout navigation wrappers
│   ├── api/               # Unified HTTP client for SentinelX Gateway & Control Plane
│   ├── App.jsx            # Application routing and role switching
│   └── main.jsx           # React DOM entrypoint
├── public/                # Static assets, icons, and favicons
└── vite.config.js         # Vite bundler configuration
```
