/* ═══════════════════════════════════════════════════
   SentinelX — Zero Trust Runtime Console v4
   ═══════════════════════════════════════════════════ */

const API = "";
let currentIdentity = "u_alex";
let seenAlertKeys = new Set();
let lastScoredRequest = null;
let latencyHistory = [];

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function tierColor(tier) {
  return { allow: "#10b981", step_up: "#f59e0b", restrict: "#f97316", revoke: "#ef4444" }[tier] || "#f8fafc";
}

/* ═════ TOASTS ═════ */
function showToast(msg, isError = false) {
  const stack = $("#toast-stack");
  if (!stack) return;
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `<div class="toast-icon">${isError ? '✕' : '✓'}</div><div class="toast-msg">${msg}</div>`;
  if (isError) el.style.borderLeftColor = "#ef4444";
  stack.appendChild(el);
  setTimeout(() => {
    el.classList.add("toast-dying");
    setTimeout(() => el.remove(), 300);
  }, 4000);
}

/* ═════ TABS ═════ */
$$(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    $$(".tab-btn").forEach(b => b.classList.remove("active"));
    $$(".tab-content").forEach(c => c.classList.remove("active"));
    btn.classList.add("active");
    const content = $(`#content-${btn.dataset.tab}`);
    if (content) content.classList.add("active");
  });
});

/* ═════ USERS API ═════ */
async function loadUsers() {
  try {
    const res = await fetch(`${API}/sentinelx/users`);
    if (!res.ok) throw new Error("Backend not available (status " + res.status + ")");
    const data = await res.json();
    if (!data || !data.users) throw new Error("Invalid user data");

    const select = $("#identity-select");
    if (!select) return;
    select.innerHTML = "";
    data.users.forEach(u => {
      const opt = document.createElement("option");
      opt.value = u.identity_id;
      opt.textContent = `${u.name} (${u.role})`;
      select.appendChild(opt);
    });
    if (!data.users.find(u => u.identity_id === currentIdentity) && data.users.length > 0) {
      currentIdentity = data.users[0].identity_id;
    }
    select.value = currentIdentity;

    // Users Tab Table
    const tbody = $("#users-body");
    if (tbody) {
      tbody.innerHTML = data.users.map(u => `
        <tr>
          <td style="font-family:var(--font-mono)">${u.identity_id}</td>
          <td style="font-weight:600">${u.name}</td>
          <td><span class="tier-tag ${u.role === 'admin' || u.role === 'manager' ? 'step_up' : 'allow'}">${u.role}</span></td>
          <td>${u.supervisor_id || '—'}</td>
          <td>${u.network_tag || '—'}</td>
          <td style="font-family:var(--font-mono); color:var(--text-muted)">Tracking</td>
        </tr>
      `).join("");
    }
  } catch (err) {
    console.error("Users load failed:", err);
  }
}

// Add user toggle
const addUserToggle = $("#add-user-toggle");
if (addUserToggle) {
  addUserToggle.addEventListener("click", () => {
    const form = $("#add-user-form");
    if (form) form.style.display = form.style.display === "none" ? "block" : "none";
  });
}

const submitAddUser = $("#submit-add-user");
if (submitAddUser) {
  submitAddUser.addEventListener("click", async () => {
    const payload = {
      identity_id: ($("#new-uid")?.value || "").trim(),
      name: ($("#new-name")?.value || "").trim(),
      role: $("#new-role")?.value || "student",
      network_tag: ($("#new-tag")?.value || "").trim() || undefined,
      supervisor_id: currentIdentity
    };
    if (!payload.identity_id || !payload.name) return showToast("Identity ID and Name required", true);

    try {
      const res = await fetch(`${API}/sentinelx/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        let msg = "Failed to add user";
        try { const d = await res.json(); msg = d.detail || msg; } catch (e) { }
        throw new Error(msg);
      }
      showToast(`User ${payload.identity_id} added successfully`);
      const form = $("#add-user-form");
      if (form) form.style.display = "none";
      if ($("#new-uid")) $("#new-uid").value = "";
      if ($("#new-name")) $("#new-name").value = "";
      if ($("#new-tag")) $("#new-tag").value = "";
      currentIdentity = payload.identity_id;
      await loadUsers();
      await pollRisk();
    } catch (e) {
      showToast(e.message, true);
    }
  });
}

/* ═════ RISK RING ═════ */
function updateRiskRing(score) {
  const arc = $("#risk-arc");
  const num = $("#risk-number");
  if (!arc || !num) return;

  const offset = 502 - (Math.min(100, Math.max(0, score)) / 100) * 502;
  arc.style.strokeDashoffset = offset;
  num.textContent = Math.round(score);

  let color = tierColor(score < 30 ? 'allow' : score < 60 ? 'step_up' : score < 85 ? 'restrict' : 'revoke');
  const s1 = $("#grad-stop1"), s2 = $("#grad-stop2");
  if (s1) s1.setAttribute("stop-color", color);
  if (s2) s2.setAttribute("stop-color", color);
  arc.style.filter = `drop-shadow(0 0 10px ${color})`;
}

/* ═════ POLLING ═════ */
async function pollRisk() {
  try {
    const res = await fetch(`${API}/sentinelx/risk/${currentIdentity}`);
    if (!res.ok) return;
    const data = await res.json();
    const state = data.risk_state || {};
    const score = state.risk_score ?? 0;
    const tier = state.tier ?? "allow";

    updateRiskRing(score);

    const badge = $("#tier-badge");
    if (badge) {
      badge.style.color = tierColor(tier);
      badge.style.borderColor = tierColor(tier);
    }
    const dot = $("#tier-dot");
    if (dot) {
      dot.style.background = tierColor(tier);
      dot.style.boxShadow = `0 0 10px ${tierColor(tier)}`;
    }
    const lbl = $("#tier-label");
    if (lbl) lbl.textContent = `${tier.replace("_", " ")} · ${data.total_requests_seen ?? 0} REQ SEEN`;

    const ml = state.ml_score ?? 0, rule = state.rule_score ?? 0;
    const barMl = $("#bar-ml"), barRule = $("#bar-rule");
    if (barMl) barMl.style.width = Math.min(100, ml) + "%";
    if (barRule) barRule.style.width = Math.min(100, rule) + "%";
    const valMl = $("#val-ml"), valRule = $("#val-rule");
    if (valMl) valMl.textContent = Math.round(ml);
    if (valRule) valRule.textContent = Math.round(rule);

    const actionMap = {
      allow: "Request proxied normally to the origin service.",
      step_up: "Step-up authentication (OTP) required before request proceeds.",
      restrict: "Rate-limited and degraded to read-only access.",
      revoke: "Session revoked outright — network assignment blocked.",
    };
    const al = $("#action-line");
    if (al) al.textContent = actionMap[tier] || "Awaiting first request for this identity.";
    const ai = $("#action-icon");
    if (ai) {
      ai.textContent = tier === 'allow' ? '✓' : tier === 'step_up' ? '?' : tier === 'restrict' ? '⚠' : '✕';
      ai.style.color = tierColor(tier);
    }

    lastScoredRequest = state;
    updatePipelineUI();
  } catch (e) { /* silently retry */ }
}

async function pollAlerts() {
  try {
    const res = await fetch(`${API}/sentinelx/alerts?limit=40`);
    if (!res.ok) return;
    const alerts = await res.json();
    renderTicker(alerts);
    updateLedger(alerts);
  } catch (e) { }
}

async function pollStats() {
  try {
    const res = await fetch(`${API}/sentinelx/stats`);
    if (!res.ok) throw new Error();
    const s = await res.json();

    const sd = $("#status-dot");
    if (sd) sd.style.background = "#10b981";
    const st = $("#status-text");
    if (st) st.textContent = "GW: LIVE";
    const sb = $("#stat-backend");
    if (sb) sb.textContent = s.backend;

    const ms = s.latency_budget_ms;
    latencyHistory.push(ms);
    if (latencyHistory.length > 20) latencyHistory.shift();
    const avg = latencyHistory.reduce((a, b) => a + b, 0) / latencyHistory.length;

    const lbv = $("#lb-val");
    if (lbv) lbv.textContent = `${Math.round(avg)} ms`;
    const fill = $("#lb-fill");
    if (fill) {
      fill.style.width = Math.min(100, (avg / 50) * 100) + "%";
      fill.className = `lb-fill ${avg < 15 ? 'good' : avg < 30 ? 'warn' : 'bad'}`;
    }
  } catch (e) {
    const sd = $("#status-dot");
    if (sd) sd.style.background = "#ef4444";
    const st = $("#status-text");
    if (st) st.textContent = "GW: OFFLINE";
  }
}

/* ═════ API SANDBOX PRESETS ═════ */
$$(".preset-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    $$(".preset-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const ep = $("#sandbox-endpoint");
    if (ep) ep.value = btn.dataset.ep;
  });
});

/* ═════ LIVE API SANDBOX ═════ */
const sandboxSend = $("#sandbox-send");
if (sandboxSend) {
  sandboxSend.addEventListener("click", async () => {
    sandboxSend.disabled = true;
    sandboxSend.textContent = "Sending…";

    let endpoint = ($("#sandbox-endpoint")?.value || "/profile").trim();
    if (!endpoint.startsWith("/")) endpoint = `/${endpoint}`;

    const geoVal = $("#sandbox-geo")?.value || "IN";
    const geo = geoVal === "RU" ? "RU-MOW" : "IN-TN";
    const speed = $("#sandbox-speed")?.value || "normal";
    const httpMethod = $("#sandbox-method")?.value || "POST";

    const be = $("#browser-endpoint");
    if (be) be.textContent = endpoint;
    const bsi = $("#browser-status-icon");
    if (bsi) { bsi.textContent = "↻"; bsi.style.animation = "spin 1s infinite linear"; }

    try {
      let scenario = "custom";
      if (speed === "spike") scenario = "frequency_spike";
      else if (geoVal === "RU") scenario = "impossible_travel";
      else if (endpoint.includes("admin")) scenario = "new_admin_endpoint";
      else if (endpoint.includes("payment") || endpoint.includes("transfer")) scenario = "privilege_escalation";
      else scenario = "normal";

      const count = speed === "spike" ? 28 : (scenario === "normal" ? 1 : 1);
      const payloadSize = httpMethod === "GET" ? 180 : 520;
      const device = geoVal === "RU" ? "linux-firefox" : "chrome-macos";

      const simRes = await fetch(`${API}/sentinelx/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          identity_id: currentIdentity,
          scenario,
          count,
          method: httpMethod,
          endpoint: endpoint,
          geo: geo,
          device: device,
          payload_size: payloadSize
        })
      });

      const simData = await simRes.json();
      const latestResult = (simData.results && simData.results.length > 0) ? simData.results[simData.results.length - 1] : null;

      await new Promise(r => setTimeout(r, 200));
      await pollRisk();
      await pollAlerts();

      const state = latestResult || lastScoredRequest;
      const tier = state?.tier || "allow";
      const tColor = tierColor(tier);

      if (bsi) {
        bsi.textContent = tier === 'revoke' ? '✕' : (tier === 'step_up' ? '?' : '●');
        bsi.style.animation = "none";
        bsi.style.color = tColor;
      }

      const body = $("#browser-body");
      if (body) {
        const reasonsList = (state?.reasons || []).map(r => r.message || r).join("<br>");
        if (tier === 'revoke' || tier === 'restrict') {
          body.innerHTML = `
            <div class="browser-block-view">
              <h1>🛡️ ACCESS RESTRICTED / REVOKED</h1>
              <p>HTTP 429 / 401 — High Risk Detected (${Math.round(state?.risk_score || 0)}/100)</p>
              <p style="margin-top:14px; font-size:13px; opacity:0.9"><strong>Reasons:</strong><br>${reasonsList || 'Policy restriction violation'}</p>
              <p style="margin-top:10px; font-size:12px; opacity:0.6">Identity: <strong>${currentIdentity}</strong> | Target: <strong>${endpoint}</strong> | Location: <strong>${geo}</strong></p>
            </div>
          `;
        } else if (tier === 'step_up') {
          body.innerHTML = `
            <div class="browser-block-view" style="background:rgba(245, 158, 11, 0.1); color:#f59e0b">
              <h1>🔐 MFA STEP-UP REQUIRED</h1>
              <p>HTTP 401 — Risk Score ${Math.round(state?.risk_score || 0)}/100</p>
              <p style="margin-top:14px; font-size:13px; opacity:0.9"><strong>Challenge:</strong> One-Time Passcode (OTP) challenge issued.</p>
              <p style="margin-top:10px; font-size:12px; opacity:0.8">Reason: ${reasonsList || 'Privilege or location drift detected'}</p>
            </div>
          `;
        } else {
          body.innerHTML = `
            <div class="browser-json-view">{
  "status": 200,
  "endpoint": "${endpoint}",
  "identity": "${currentIdentity}",
  "method": "${httpMethod}",
  "verdict": "ALLOWED",
  "risk_score": ${Math.round(state?.risk_score || 0)},
  "ml_anomaly_score": ${Math.round(state?.ml_score || 0)},
  "rule_score": ${Math.round(state?.rule_score || 0)},
  "tier": "${tier}",
  "message": "Passed Zero Trust ML & deterministic filters."
}</div>
          `;
        }
      }

      // Append to browser mini log
      const logBody = $("#browser-log-body");
      if (logBody) {
        const idle = logBody.querySelector(".log-idle");
        if (idle) idle.remove();
        const c = (tier === 'revoke' || tier === 'restrict') ? 'c403' : (tier === 'step_up' ? 'c403' : 'c200');
        logBody.innerHTML += `<div class="log-line"><span class="arr">→</span><span class="url">${httpMethod} ${endpoint} (${geo})</span><span class="status ${c}">${tier.toUpperCase()} (${Math.round(state?.risk_score || 0)})</span><span class="ms">${Math.floor(Math.random() * 10 + 2)}ms</span></div>`;
        logBody.scrollTop = logBody.scrollHeight;
      }

      showToast(`Request scored: ${Math.round(state?.risk_score || 0)}/100 — Tier: ${tier.toUpperCase()}`);

    } catch (e) {
      console.error("Sandbox error:", e);
      showToast("Request failed: " + e.message, true);
    }

    sandboxSend.disabled = false;
    sandboxSend.textContent = "Send Request ➔";
  });
}

/* ═════ PIPELINE VIZ ═════ */
function pulseLine(num) {
  const line = $(`#conn-${num}`);
  const pulse = $(`#cpulse-${num}`);
  if (line) line.classList.add("active");
  if (pulse) {
    pulse.style.animation = 'none';
    pulse.offsetHeight;
    pulse.classList.add("pulsing");
  }
}

function resetPipeline() {
  $$(".connector-line").forEach(l => l.classList.remove("active"));
  $$(".connector-pulse").forEach(p => p.classList.remove("pulsing"));
  $$(".pipeline-stage").forEach(s => s.classList.remove("active-stage"));
}

function updatePipelineUI() {
  if (!lastScoredRequest) return;
  const s = lastScoredRequest;

  resetPipeline();

  setTimeout(() => { pulseLine(1); const el = $("#ps-1"); if (el) el.classList.add("active-stage"); const d = $("#ps-1-data"); if (d) d.textContent = `identity_id: ${currentIdentity}\nendpoint: ${s.endpoint || '/profile'}`; const l = $("#ps-1-lat"); if (l) l.textContent = "0.2ms"; }, 0);
  setTimeout(() => { pulseLine(2); const el = $("#ps-2"); if (el) el.classList.add("active-stage"); const d = $("#ps-2-data"); if (d) d.textContent = `Baseline extracted.\n7-signal vector computed.`; const l = $("#ps-2-lat"); if (l) l.textContent = "2.1ms"; }, 300);
  setTimeout(() => {
    pulseLine(3);
    const a = $("#ps-3a"); if (a) a.classList.add("active-stage");
    const b = $("#ps-3b"); if (b) b.classList.add("active-stage");
    const da = $("#ps-3a-data"); if (da) da.textContent = `Rule Hits: ${s.reasons ? s.reasons.length : 0}\nScore: ${Math.round(s.rule_score || 0)}/100`;
    const db = $("#ps-3b-data"); if (db) db.textContent = `IsoForest Trees: 150\nScore: ${Math.round(s.ml_score || 0)}/100`;
  }, 600);
  setTimeout(() => { pulseLine(4); const el = $("#ps-4"); if (el) el.classList.add("active-stage"); const d = $("#ps-4-data"); if (d) d.textContent = `Blend: ML(55%) + Rule(45%)\nFinal Risk: ${Math.round(s.risk_score || 0)}/100`; }, 900);
  setTimeout(() => { const el = $("#ps-5"); if (el) el.classList.add("active-stage"); const d = $("#ps-5-data"); if (d) { d.textContent = `Verdict: ${(s.tier || 'allow').toUpperCase()}\nAction: ${s.action || 'allow'}`; d.style.color = tierColor(s.tier); } }, 1200);

  if (s.features && Array.isArray(s.features)) {
    const keys = ['freq', 'novelty', 'geo', 'device', 'time', 'payload', 'age'];
    const caps = [50, 1.0, 1.0, 1.0, 1.0, 4.0, 3600];
    const fixeds = [1, 2, 2, 2, 2, 2, 0];

    keys.forEach((key, i) => {
      const val = s.features[i] ?? 0;
      let pct = (Math.abs(val) / caps[i]) * 100;
      pct = Math.max(8, Math.min(100, pct));
      const fv = $(`#fv-${key}`);
      if (fv) fv.textContent = Number(val).toFixed(fixeds[i]);
      const fb = $(`#fb-${key}`);
      if (fb) {
        fb.style.height = `${pct}%`;
        fb.style.background = pct > 70 ? '#ef4444' : pct > 35 ? '#f59e0b' : '#818cf8';
      }
    });
  }
}

/* ═════ ALERTS & LEDGER ═════ */
function renderTicker(alerts) {
  const scroll = $("#ticker-scroll");
  if (!scroll) return;
  const relevant = alerts.filter(a => a.identity_id === currentIdentity);
  if (relevant.length === 0) return;
  const empty = $("#ticker-empty");
  if (empty) empty.style.display = "none";

  const counter = $("#alert-counter");

  relevant.slice().reverse().forEach(a => {
    const key = `${a.identity_id}-${a.timestamp}-${a.endpoint}`;
    if (seenAlertKeys.has(key)) return;
    seenAlertKeys.add(key);

    if (counter) counter.textContent = `${seenAlertKeys.size} active`;

    const div = document.createElement("div");
    div.className = `ticket ${a.tier}`;
    const time = new Date(a.timestamp).toLocaleTimeString();
    const reasons = (a.reasons || []).map(r => `<li>${r.message}</li>`).join("");
    div.innerHTML = `
      <div class="ticket-head">
        <span>${time}</span>
        <span class="ticket-tier ${a.tier}">${a.tier.replace("_", " ")}</span>
      </div>
      <div class="ticket-endpoint">${a.endpoint}</div>
      <ul class="ticket-reasons">${reasons}</ul>
      <div class="ticket-score">RISK ${Math.round(a.risk_score)}/100 · RULE ${Math.round(a.rule_score)} · ML ${Math.round(a.ml_score)}</div>
    `;
    scroll.prepend(div);
  });
}

function updateLedger(alerts) {
  const rows = alerts.filter(a => a.identity_id === currentIdentity).slice(0, 12);
  const body = $("#ledger-body");
  if (!body) return;
  const lbl = $("#ledger-identity-label");
  if (lbl) lbl.textContent = `— ${currentIdentity}`;
  if (rows.length === 0) {
    body.innerHTML = `<tr><td colspan="5" class="ledger-empty">Nothing logged yet for this identity.</td></tr>`;
    return;
  }
  body.innerHTML = rows.map(a => {
    const time = new Date(a.timestamp).toLocaleTimeString();
    const topReason = (a.reasons && a.reasons[0]) ? a.reasons[0].message : "—";
    return `<tr>
      <td style="font-family:var(--font-mono); color:var(--text-muted)">${time}</td>
      <td style="font-family:var(--font-mono)">${a.endpoint}</td>
      <td style="font-weight:700">${Math.round(a.risk_score)}</td>
      <td><span class="tier-tag ${a.tier}">${a.tier.replace("_", " ")}</span></td>
      <td>${topReason}</td>
    </tr>`;
  }).join("");
}

/* ═════ CONTROLS ═════ */
const identitySelect = $("#identity-select");
if (identitySelect) {
  identitySelect.addEventListener("change", (e) => {
    currentIdentity = e.target.value;
    seenAlertKeys.clear();
    const ts = $("#ticker-scroll");
    if (ts) ts.innerHTML = '<div class="ticker-empty" id="ticker-empty">No alerts yet in this session.</div>';
    const ac = $("#alert-counter");
    if (ac) ac.textContent = "0 active";
    pollRisk(); pollAlerts();
  });
}

const savePolicy = $("#save-policy");
if (savePolicy) {
  savePolicy.addEventListener("click", async () => {
    savePolicy.textContent = "Applying...";
    const thresholds = {
      allow: parseInt($("#th-allow")?.value || "30", 10),
      step_up: parseInt($("#th-stepup")?.value || "60", 10),
      restrict: parseInt($("#th-restrict")?.value || "85", 10),
    };
    try {
      await fetch(`${API}/sentinelx/policy`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thresholds })
      });
      showToast("Zero-Trust Policy Applied");
    } catch (e) {
      showToast("Failed to apply policy", true);
    }
    savePolicy.textContent = "Apply Policy";
  });
}

$$(".slider").forEach(sl => {
  sl.addEventListener("input", (e) => {
    const valEl = $(`#${e.target.id}-val`);
    if (valEl) valEl.textContent = e.target.value;
  });
});

async function loadPolicy() {
  try {
    const res = await fetch(`${API}/sentinelx/policy`);
    if (!res.ok) return;
    const p = await res.json();
    if (p.thresholds) {
      if ($("#th-allow")) { $("#th-allow").value = p.thresholds.allow; }
      if ($("#th-allow-val")) { $("#th-allow-val").textContent = p.thresholds.allow; }
      if ($("#th-stepup")) { $("#th-stepup").value = p.thresholds.step_up; }
      if ($("#th-stepup-val")) { $("#th-stepup-val").textContent = p.thresholds.step_up; }
      if ($("#th-restrict")) { $("#th-restrict").value = p.thresholds.restrict; }
      if ($("#th-restrict-val")) { $("#th-restrict-val").textContent = p.thresholds.restrict; }
    }
  } catch (e) { }
}

function tickClock() {
  const el = $("#clock");
  if (el) el.textContent = new Date().toUTCString().slice(0, 25) + " UTC";
}

/* ═════ INIT ═════ */
tickClock();
setInterval(tickClock, 1000);

// Inject spin keyframe for loading spinner
const spinStyle = document.createElement('style');
spinStyle.textContent = '@keyframes spin { 100% { transform:rotate(360deg); } }';
document.head.appendChild(spinStyle);

(async () => {
  try {
    await loadUsers();
    await loadPolicy();
    // Initial polls
    pollRisk();
    pollAlerts();
    pollStats();
    // Recurring polls
    setInterval(pollRisk, 2500);
    setInterval(pollAlerts, 3000);
    setInterval(pollStats, 5000);
  } catch (e) {
    console.error("Init error:", e);
  }
})();
