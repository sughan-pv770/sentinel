# Orbit SaaS + SentinelX: Demo Script for Judges

This 3-minute walkthrough demonstrates SentinelX protecting a real application ("Orbit") via live UI enforcement, proving Zero-Code Integration and Dynamic Onboarding.

## Preparation
1. Ensure the gateway and all origin services are running: `python start_all.py`
2. Open two browser windows side-by-side:
   - **Left Window:** Orbit SaaS (`http://localhost:9001`)
   - **Right Window:** SentinelX Dashboard (`http://localhost:8080/dashboard`)

## The Walkthrough

### 1. Templatization & Pre-Auth Bypass (Signup)
* **Action (Orbit):** On the login screen, click **Sign Up** instead of logging in. Create a new user (e.g. "Judge", "judge@demo.com", Role: "Admin").
* **Talking Point:** *"Notice that this signup request worked immediately. In our `services.json` config, we marked `/signup` as `auth_required: false`. The SentinelX gateway proxies it straight through without identity scoring—preventing a chicken-and-egg problem where brand new users get blocked by the ML model."*

### 1.5. Live Gateway-to-Orbit Sync (JIT Provisioning)
* **Action (Gateway):** Ensure Orbit's **Admin** tab is open so the 10-second background polling is active. Then, from the terminal, create a new user directly in the SentinelX gateway: `curl -X POST http://localhost:8080/sentinelx/users -H "Content-Type: application/json" -d '{"identity_id": "u_new", "name": "New User"}'`
* **Observation (Orbit):** Watch the Orbit Admin tab. Within 10 seconds, the new user automatically appears in the table.
* **Action (Orbit):** Log out. On the login screen, manually enter or select the new identity ID (`u_new`) and click **Log In**.
* **Observation (Orbit):** Instead of logging into the dashboard, Orbit immediately halts the flow and routes the user to a **"Set Password"** screen.
* **Talking Point:** *"Notice what happened here: we created a user directly in the security gateway. Orbit's UI dynamically picked up that new identity via its live sync integration. But because the user was created remotely, they don't have a local password yet. Orbit recognizes this `password_not_set` state and forces a password setup flow before granting access, demonstrating seamless, secure state synchronization between the Zero Trust Gateway and the SaaS application."*

### 2. Dynamic Onboarding & Cold-Start (The "ALLOW" Path)
* **Action (Orbit):** The new user is automatically logged in. Click **Refresh Profile** or switch to the **Orders** tab.
* **Action (Dashboard):** Show the judge the dashboard. Point out the new request with a Tier clearly showing `ALLOW`. 
* **Talking Point:** *"When Orbit created the user, it immediately registered them with the SentinelX control plane. Because of this, SentinelX knows they are a new, legitimate user, not an anomalous old user. Their first action on a normal endpoint receives a clean ALLOW decision—no onboarding friction."*

### 3. The "STEP-UP" Path (Privilege / Sensitivity)
* **Action (Orbit):** As the new user (or as Alex Rao), switch to the `Billing` tab and click **Pay Now**.
* **Observation (Orbit):** The **Security Verification Required (MFA)** modal pops up instantly. A Toast notification shows the actual 6-digit OTP code (for demo purposes).
* **Action (Orbit):** Type the OTP code into the modal and submit. The payment completes successfully.
* **Action (Dashboard):** Point out the `STEP-UP` decision in the dashboard.
* **Talking Point:** *"The ML and Rule engines recognize `/payments/transfer` as highly sensitive. Even for a logged-in user, the gateway dynamically intercepts the request and issues a cryptographic OTP. Only after verification does the payment proceed. The Origin Service never wrote a single line of MFA code—it's entirely handled by the Gateway and the drop-in `sentinelx-client.js`."*

### 3.5. Verb-Aware Sensitivity & Dev Test Panel
* **Action (Orbit):** Switch to the `Admin` tab. Explain that `GET /admin/users` was allowed to load the table. Now click **Remove** on a user.
* **Observation (Orbit):** The MFA modal pops up again, or the action is denied (RESTRICT).
* **Talking Point:** *"Notice that just viewing the Admin page (`GET`) was allowed, but clicking Remove (`DELETE`) triggered high-risk enforcements. SentinelX is verb-aware—it keys sensitivity off both the path and the HTTP method."*
* **Action (Orbit):** Open the **Dev Test Panel** in the bottom right corner (only visible in `ORBIT_ENV=demo`).
* **Talking Point:** *"For complete Sandbox parity, we included this hidden Dev Test panel. You can manually fire any of the 25 Endpoint + Verb combinations through the gateway directly from the UI to prove the ML engine evaluates every combination uniquely."*

### 3.7. Bulk Risk Escalation (Live Frequency Demo)
* **Action (Orbit):** In the Dev Test Panel, make sure `GET /profile` is selected and the user is a standard member (e.g. Alex Rao).
* **Action (Orbit):** Click the **×100** preset button (or type `100` in the count input), then click **Send Bulk**.
* **Observation (Orbit — live, updating in real time):** Watch the tally in the Dev Test Panel update as the burst fires: the first requests come back as **ALLOW**, then after ~10–20 requests the panel will show the first **STEP-UP** verdict, and around request ~30–50 the score will cross into **RESTRICT**.
* **Observation (Dashboard):** On the right, the SentinelX Console's ML Pipeline tab should show the risk score climbing visibly — from baseline to elevated — as the burst proceeds.
* **Talking Point:** *"What you're watching is the ML engine's behavioral baseline working in real time. The first few requests look like normal traffic — ALLOW. As volume accelerates, the frequency anomaly score starts climbing — that's the model detecting unusual request rate for this user. We escalate through STEP-UP, requiring verification, and then into RESTRICT, rate-limiting the identity at the edge. No rules were written for this — it's the model reacting to live behavior."*
* **On Completion:** Read out the escalation points from the summary (e.g., *"Escalated to STEP-UP at request #14, RESTRICT at #31"*). These numbers make the abstract concept concrete and narrate the demo clearly.
* **Note for presenter:** If you want to demonstrate REVOKE in the same burst, switch on the **Spoof Location/Device** toggle before starting — the impossible travel rule will trigger a 403 REVOKE mid-burst, and the panel will automatically stop and display: *"Burst stopped early: session revoked after N of 100 requests."*

### 4. The "REVOKE" Path (Impossible Travel Attack)
* **Action (Orbit):** Click **Log Out**.
* **Action (Orbit):** Check the **[Dev] Spoof Location/Device** toggle. Select your user (or Alex) again and **Log In**. 
* **Action (Orbit):** Click `Refresh Profile`.
* **Observation (Orbit):** A critical security alert pops up ("Session revoked"), and the user is immediately kicked back to the Login screen.
* **Action (Dashboard):** Show the dashboard. The score is near 100, Tier is `REVOKE`. The Incident Log shows "Impossible Travel detected".
* **Talking Point:** *"An attacker stole the session token and tried to use it from a new device in a different country. SentinelX caught the anomaly, the Rule Engine flagged it as Impossible Travel, and the Gateway instantly revoked the session at the edge. The attacker is blocked, and the real account is protected."*

### 5. Proof of Zero-Code Integration
* **Action (Browser):** Open a new tab and hit `http://localhost:8080/gateway/stub-service/hello`. 
* **Observation (Browser):** The JSON response shows `{"status": "ok", "service": "stub"}`.
* **Talking Point:** *"This is a completely separate 20-line microservice running on port 9002. By simply adding 5 lines to our `services.json`, SentinelX is now protecting it with full ML scoring and behavioral baselines. Zero gateway code changes were required to onboard it."*

### 6. Recovery Workflow — Detection AND Graceful Recovery ⭐

> **This is the moment that separates us from "block and done" demos. Most hackathon security projects stop at detection. We show the complete lifecycle: detect → block → recover → audit.**

#### 6a. Trigger a REVOKE via Bulk Burst
* **Action (Orbit):** Log in as **Alex Rao** (Member). Open the Dev Test Panel (visible in demo mode).
* **Action (Orbit):** Click **Send Bulk ×100** to fire a burst of requests. Watch as the risk score climbs through ALLOW → STEP-UP → RESTRICT → REVOKE.
* **Observation (Orbit):** When REVOKE fires, Orbit doesn't just show "Login failed" — it shows a **dedicated Revoke Unlock Screen**: *"Your session was terminated due to suspicious activity. Contact your administrator for an unlock code."* There's a code input field waiting for an admin OTP.
* **Talking Point:** *"Notice the user isn't stuck at a dead-end error. They're told exactly what happened and exactly what to do — contact their admin. This is a designed recovery workflow, not a bug."*

#### 6b. Admin Sees the Lock in Real Time
* **Action (Orbit):** Open a second browser tab. Log in as **Priya Nair** (Admin).
* **Action (Orbit):** Switch to the **Admin** tab. Scroll down to the **🔒 Locked Accounts** panel.
* **Observation (Orbit):** Alex Rao appears in the locked accounts list with their risk score and a red badge showing "1" locked account.
* **Talking Point:** *"The admin has real-time visibility into every locked identity — who's locked, why, and their risk score at the time of revocation. No digging through logs."*

#### 6c. Admin Generates Unlock Code
* **Action (Orbit):** Click **🔑 Generate Unlock Code** next to Alex's entry.
* **Observation (Orbit):** An OTP code appears (displayed in a toast and on the button itself). The admin would relay this to Alex out-of-band (verbally, chat, etc.).
* **Talking Point:** *"This OTP is separate from the normal step-up MFA system — it's a distinct code space, purpose-built for recovery. It's one-time use, expires in 5 minutes, and the generation itself is logged in the audit trail."*

#### 6d. Member Recovers Access
* **Action (Orbit):** Switch back to Alex's browser tab (showing the unlock screen). Enter the OTP code from step 6c and click **Submit Unlock Code**.
* **Observation (Orbit):** Success — Alex is redirected to the login screen. Log in again as Alex. This time, login succeeds normally.
* **Talking Point:** *"Alex is back in with a genuinely fresh session. The identity-level lock was lifted by a human-in-the-loop decision, not by the clock running out. And every step — the lock, the OTP generation, and the unlock — is in the audit trail."*

#### 6e. (Optional) Dev Reset for Rehearsal
* **Action (Orbit):** As admin, in the Dev Test Panel, click **🔓 Reset All Identity Locks** to clear all locks for the next demo run.
* **Talking Point:** *"For development and rehearsal, we have a demo-only reset tool so we can run this showcase repeatedly without manual cleanup."*

## Wrap Up
*"This demonstrates how SentinelX isn't just a passive monitor — it's an active gateway that transforms backend risk intelligence into real-time, user-facing security enforcements (MFA, rate limiting, and session revocation) without requiring any backend logic changes in the protected application. And critically, it includes a complete, audited recovery workflow — because real security systems need to handle the 'what happens next' just as carefully as the initial detection."*
