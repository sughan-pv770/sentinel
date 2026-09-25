/**
 * Orbit SaaS Application
 * Uses sentinelx-client.js for all gateway calls.
 * Enforcement (STEP-UP / RESTRICT / REVOKE) is handled by the client library.
 *
 * UI OVERHAUL — Premium Pass
 * Phases 2-5 features added on top of existing logic:
 *   - Command palette (Ctrl/Cmd+K) with ROLE-BASED filtering
 *   - Animated number counters
 *   - Skeleton shimmer loading states
 *   - Cursor-aware card glow
 *   - Success-burst micro-animation
 *   - Risk gauge (SVG arc, live update)
 *   - Sparkline mini-charts
 *   - Live relative timestamps
 *   - 40ms stagger entrance / exit animations
 *   - Stacking toast queue with progress bars
 *   - Sliding nav pill
 *   - Modal focus traps
 *   - Revoke flash (cosmetic only — fires AFTER sync logout)
 */

const GATEWAY_ORG  = "http://localhost:8080";
const GATEWAY_BASE = `${GATEWAY_ORG}/gateway/orbit`;
const SENTINELX_BASE = `${GATEWAY_ORG}/sentinelx`;

let sx = null; // SentinelXClient instance — created on login

// Phase 2 Gap-2 fix: track current user role for command palette filtering
let currentUserRole = null;

// ─── Dev spoofing ────────────────────────────────────────────────────────────
let isDemoMode = false;

/* ════════════════════════════════════════════════
   TRANSPARENT CHALLENGE REASONING (Phase 1)
   Safe-to-show mapping: rule codes → plain English.
   Deliberately excludes thresholds, weights, rule IDs.
   ════════════════════════════════════════════════ */
const SAFE_REASON_MAP = {
    // Rule-layer signals
    impossible_travel:           'access from a location that doesn\'t match your usual pattern',
    sensitive_endpoint_access:   'an action that requires extra verification for your role',
    first_time_sensitive_access: 'a first-time request to a sensitive area of the system',
    frequency_spike:             'an unusually high number of requests in a short time',
    device_and_geo_change:       'a device and location we haven\'t seen together on this account',
    identity_revoked:            'your session was revoked following a security alert',
    token_used_after_revocation: 'a session token used after it was already revoked',
    agent_scope_deviation:       'an AI agent acting outside its declared permissions',
    anomalous_behaviour_pattern: 'activity that deviates from your usual behaviour',
    // ML catch-all
    ml_anomaly:                  'a behaviour pattern our system hasn\'t seen from you before',
};

/**
 * Converts up to 2 raw reason objects from the gateway into a safe,
 * human-readable sentence. Never exposes scores, thresholds, or rule names.
 */
function safeReasonText(reasons) {
    if (!reasons || reasons.length === 0) return null;
    // Pick top 2 by taking the first ones (gateway already orders by severity)
    const phrases = reasons.slice(0, 2).map(r => {
        // r may be a string (from older response shape) or an object with .code
        const code = typeof r === 'string' ? r : (r.code || '');
        return SAFE_REASON_MAP[code] || null;
    }).filter(Boolean);
    if (phrases.length === 0) return null;
    return 'We\'re verifying because: ' + phrases.join(', and ') + '.';
}

async function loadEnv() {
    try {
        const res  = await fetch(`${GATEWAY_BASE}/env`);
        const data = await res.json();
        if (data.env === 'demo') {
            isDemoMode = true;
            const testPanel = document.getElementById('dev-test-panel');
            if (testPanel) testPanel.style.display = 'block';
        }
        
        // Fetch and populate users dropdown dynamically
        const usersRes = await fetch(`${GATEWAY_BASE}/public/users`);
        if (usersRes.ok) {
            const usersData = await usersRes.json();
            const selectEl = document.getElementById('user-select');
            if (selectEl && usersData.users) {
                selectEl.innerHTML = usersData.users.map(u => 
                    `<option value="${u.identity_id}">${u.name} — ${u.role.charAt(0).toUpperCase() + u.role.slice(1)}</option>`
                ).join('');
            }
        }
    } catch (e) { /* hide on error */ }
}

/* ════════════════════════════════════════════════
   PHASE 3 — TOAST SYSTEM (stacking queue)
   ════════════════════════════════════════════════ */
const TOAST_DURATION = 5000; // ms
const TOAST_MAX      = 3;
const _toastQueue    = [];

function showToast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) { return; }

    // Remove oldest if over limit
    if (_toastQueue.length >= TOAST_MAX) {
        _dismissToast(_toastQueue[0]);
    }

    const el = document.createElement('div');
    el.className = `toast toast-${type}`;

    const text = document.createElement('span');
    text.className = 'toast-text';
    text.textContent = msg;
    el.appendChild(text);

    const bar = document.createElement('div');
    bar.className = 'toast-progress';
    bar.style.setProperty('--toast-duration', `${TOAST_DURATION}ms`);
    el.appendChild(bar);

    container.appendChild(el);
    _toastQueue.push(el);

    // Click to dismiss early
    el.addEventListener('click', () => _dismissToast(el));

    // Trigger entrance (next frame so CSS transition fires)
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            el.classList.add('visible');
            bar.classList.add('animating');
        });
    });

    // Auto-dismiss
    el._dismissTimer = setTimeout(() => _dismissToast(el), TOAST_DURATION);
}

function _dismissToast(el) {
    if (!el || el._dismissing) return;
    el._dismissing = true;
    clearTimeout(el._dismissTimer);
    el.classList.add('dismissing');
    const idx = _toastQueue.indexOf(el);
    if (idx !== -1) _toastQueue.splice(idx, 1);
    setTimeout(() => el.remove(), 220);
}

/* ════════════════════════════════════════════════
   PHASE 3 — MODAL FOCUS TRAP
   ════════════════════════════════════════════════ */
const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function trapFocus(modalEl) {
    const focusable = [...modalEl.querySelectorAll(FOCUSABLE)];
    if (!focusable.length) return;
    const first = focusable[0];
    const last  = focusable[focusable.length - 1];

    function handler(e) {
        if (e.key !== 'Tab') return;
        if (e.shiftKey) {
            if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
            if (document.activeElement === last)  { e.preventDefault(); first.focus(); }
        }
    }
    modalEl._trapHandler = handler;
    modalEl.addEventListener('keydown', handler);
    // Initial focus
    setTimeout(() => first.focus(), 50);
}

function releaseFocus(modalEl) {
    if (modalEl._trapHandler) {
        modalEl.removeEventListener('keydown', modalEl._trapHandler);
        delete modalEl._trapHandler;
    }
}

/* ── Modal open / close with animation ── */
function openModal(overlayId) {
    const overlay = document.getElementById(overlayId);
    const box     = overlay && overlay.querySelector('.modal-box');
    overlay.classList.remove('hidden', 'closing');
    if (box) box.classList.remove('closing');
    trapFocus(overlay);
}

function closeModal(overlayId) {
    const overlay = document.getElementById(overlayId);
    const box     = overlay && overlay.querySelector('.modal-box');
    releaseFocus(overlay);
    if (box) box.classList.add('closing');
    overlay.classList.add('closing');
    setTimeout(() => {
        overlay.classList.add('hidden');
        overlay.classList.remove('closing');
        if (box) box.classList.remove('closing');
    }, 180);
}

/* ════════════════════════════════════════════════
   PHASE 3 — SLIDING NAV PILL
   ════════════════════════════════════════════════ */
function positionNavPill(activeBtn) {
    const pill = document.getElementById('nav-pill');
    const nav  = document.getElementById('sidebar-nav');
    if (!pill || !activeBtn || !nav) return;
    const navRect = nav.getBoundingClientRect();
    const btnRect = activeBtn.getBoundingClientRect();
    const top = btnRect.top - navRect.top + nav.scrollTop;
    pill.style.transform = `translateY(${top}px)`;
    pill.style.height = `${btnRect.height}px`;
    pill.classList.add('visible');
}

/* ════════════════════════════════════════════════
   PHASE 4 — RISK GAUGE
   ════════════════════════════════════════════════ */
let _lastRiskScore = 0;

function updateRiskGauge(score) {
    score = Math.min(100, Math.max(0, score || 0));
    _lastRiskScore = score;

    const wrap  = document.getElementById('risk-gauge-wrap');
    const arc   = document.getElementById('risk-arc');
    const label = document.getElementById('risk-gauge-score');
    if (!wrap || !arc || !label) return;

    wrap.style.display = 'flex';

    // circumference = 2π × 14 ≈ 87.96, use 88
    const offset = 88 - (88 * score / 100);
    arc.style.strokeDashoffset = offset;

    // Smooth color: green → yellow → red via hsl
    const hue = Math.round(120 - (score * 1.2)); // 120 (green) → 0 (red)
    const saturation = score > 10 ? 75 : 50;
    arc.style.stroke = `hsl(${hue}, ${saturation}%, 55%)`;

    label.textContent = score;
    label.style.color = `hsl(${hue}, ${saturation}%, 65%)`;

    // Animate label color
    label.style.transition = 'color 0.7s';
}

/* ════════════════════════════════════════════════
   PHASE 4 — ACTIVITY LOG (live timestamps)
   ════════════════════════════════════════════════ */
const _logEntries = []; // { el, ts, color, text }

function log(message, level = 'info') {
    const logEl  = document.getElementById('activity-log');
    const colors = { info: '#8b949e', error: '#f85149', warn: '#d29922', success: '#3fb950' };
    const color  = colors[level] || colors.info;
    const ts     = Date.now();

    const entry    = document.createElement('div');
    entry.className = 'log-entry';
    entry.style.color = color;

    const timeEl   = document.createElement('span');
    timeEl.className = 'log-time-relative';

    const msgEl    = document.createElement('span');
    msgEl.textContent = message;

    entry.appendChild(msgEl);
    entry.appendChild(timeEl);

    logEl.insertBefore(entry, logEl.firstChild);
    _logEntries.unshift({ el: entry, timeEl, ts, color, text: message });

    // Keep max 50 entries
    if (_logEntries.length > 50) {
        const old = _logEntries.pop();
        old.el.remove();
    }

    _updateLogTimestamps();

    // Also extract risk score from message if present
    const riskMatch = message.match(/Score:\s*(\d+)/);
    if (riskMatch) updateRiskGauge(parseInt(riskMatch[1], 10));
}

function _relativeTime(ts) {
    const diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 5)   return 'just now';
    if (diff < 60)  return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
}

function _updateLogTimestamps() {
    _logEntries.forEach(e => {
        if (e.timeEl) e.timeEl.textContent = ` · ${_relativeTime(e.ts)}`;
    });
}

// Refresh timestamps every 10s
setInterval(_updateLogTimestamps, 10000);

/* ════════════════════════════════════════════════
   PHASE 2 — ANIMATED NUMBER COUNTER
   ════════════════════════════════════════════════ */
function animateCounter(el, target, prefix = '', suffix = '', duration = 600) {
    if (!el) return;
    const start    = performance.now();
    const from     = 0;

    function easeOutQuart(t) {
        return 1 - Math.pow(1 - t, 4);
    }

    function tick(now) {
        const elapsed  = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const value    = Math.round(from + (target - from) * easeOutQuart(progress));
        el.textContent = `${prefix}${value.toLocaleString()}${suffix}`;
        if (progress < 1) requestAnimationFrame(tick);
        else el.textContent = `${prefix}${target.toLocaleString()}${suffix}`;
    }

    requestAnimationFrame(tick);
}

/* ════════════════════════════════════════════════
   PHASE 2 — SUCCESS BURST MICRO-ANIMATION
   ════════════════════════════════════════════════ */
function triggerSuccessBurst(btnEl) {
    if (!btnEl) return;
    // Remove any existing ring
    const existing = btnEl.querySelector('.success-burst-ring');
    if (existing) existing.remove();

    const ring = document.createElement('span');
    ring.className = 'success-burst-ring';
    btnEl.style.position = 'relative';
    btnEl.appendChild(ring);
    setTimeout(() => ring.remove(), 420);
}

/* ════════════════════════════════════════════════
   PHASE 2 — CURSOR-AWARE CARD GLOW
   Delegated via single listener on document
   ════════════════════════════════════════════════ */
document.addEventListener('mousemove', (e) => {
    const card = e.target.closest('.user-card, .profile-card');
    if (!card) return;
    const rect = card.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width * 100).toFixed(1);
    const y = ((e.clientY - rect.top)  / rect.height * 100).toFixed(1);
    card.style.setProperty('--cursor-x', `${x}%`);
    card.style.setProperty('--cursor-y', `${y}%`);
});

/* ════════════════════════════════════════════════
   PHASE 4 — SPARKLINE MINI-CHART
   ════════════════════════════════════════════════ */
function drawSparkline(values) {
    const svg = document.getElementById('orders-sparkline');
    const container = document.getElementById('sparkline-container');
    if (!svg || !container || values.length < 2) {
        if (container) container.style.display = 'none';
        return;
    }
    container.style.display = 'flex';

    const W = 80, H = 24, pad = 2;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;

    const points = values.map((v, i) => {
        const x = pad + (i / (values.length - 1)) * (W - pad * 2);
        const y = H - pad - ((v - min) / range) * (H - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    svg.innerHTML = `
        <defs>
            <linearGradient id="spkGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.3"/>
                <stop offset="100%" stop-color="#3b82f6" stop-opacity="0"/>
            </linearGradient>
        </defs>
        <polyline points="${points}" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>
    `;
}

/* ════════════════════════════════════════════════
   PHASE 3 — SKELETON HELPERS
   ════════════════════════════════════════════════ */
function skeletonProfileHTML() {
    return `<div class="skeleton-loader">
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
            <div class="skeleton-avatar"></div>
            <div style="flex:1"><div class="skeleton-line" style="height:14px;margin-bottom:8px"></div><div class="skeleton-line short" style="height:10px"></div></div>
        </div>
        <div class="profile-info-grid">
            <div><div class="skeleton-line" style="height:10px;width:60px;margin-bottom:8px"></div><div class="skeleton-line tall"></div></div>
            <div><div class="skeleton-line" style="height:10px;width:40px;margin-bottom:8px"></div><div class="skeleton-line tall"></div></div>
            <div><div class="skeleton-line" style="height:10px;width:50px;margin-bottom:8px"></div><div class="skeleton-line medium tall"></div></div>
            <div><div class="skeleton-line" style="height:10px;width:70px;margin-bottom:8px"></div><div class="skeleton-line tall"></div></div>
        </div>
    </div>`;
}

function skeletonOrdersHTML(count = 4) {
    return Array.from({ length: count }, () => `
        <div class="order-item" style="opacity:1;animation:none">
            <div style="flex:1"><div class="skeleton-line" style="height:10px;width:60px;margin-bottom:6px"></div><div class="skeleton-line medium" style="height:14px;margin:0"></div></div>
            <div class="skeleton-stat" style="width:60px;height:20px"></div>
            <div class="skeleton-stat" style="width:72px;height:22px;border-radius:20px"></div>
            <div class="skeleton-stat" style="width:56px;height:28px"></div>
        </div>`).join('');
}

function skeletonUsersHTML(count = 6) {
    return `<div class="user-card-grid">${Array.from({ length: count }, () => `
        <div class="skeleton-card" style="opacity:1;animation:none">
            <div style="display:flex;align-items:center;gap:10px">
                <div class="skeleton-avatar"></div>
                <div style="flex:1"><div class="skeleton-line" style="height:14px;margin-bottom:6px"></div><div class="skeleton-line short" style="height:10px;margin:0"></div></div>
            </div>
            <div class="skeleton-stat" style="height:32px"></div>
        </div>`).join('')}</div>`;
}

/* ════════════════════════════════════════════════
   UI HELPERS
   ════════════════════════════════════════════════ */
function switchView(viewId) {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    document.getElementById(viewId).classList.add('active');
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    const tab = document.getElementById(tabId);
    if (tab) tab.classList.add('active');
    // Update nav active state (pill handled separately)
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    const navBtn = document.querySelector(`[data-target="${tabId}"]`);
    if (navBtn) {
        navBtn.classList.add('active');
        positionNavPill(navBtn);
    }
    // Trigger billing counter when billing tab activates
    if (tabId === 'billing-tab') {
        const el = document.getElementById('billing-amount-display');
        if (el) animateCounter(el, 450, '$', '.00');
    }
}

function setLoading(btnId, loading) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.disabled = loading;
    if (loading) {
        btn.dataset.originalHTML = btn.dataset.originalHTML || btn.innerHTML;
        const spinnerHTML = `<span class="btn-loading-spinner"></span>`;
        btn.innerHTML = spinnerHTML + `<span style="opacity:0.7">${btn.dataset.originalText || '…'}</span>`;
    } else if (btn.dataset.originalHTML) {
        btn.innerHTML = btn.dataset.originalHTML;
        delete btn.dataset.originalHTML;
    }
}

/* ════════════════════════════════════════════════
   ENFORCEMENT HANDLERS
   ════════════════════════════════════════════════ */
function onStepUp(data) {
    log(`⚠️ STEP-UP required (Score: ${data.risk_score})`, 'warn');
    updateRiskGauge(data.risk_score);
    const challenge = data.challenge || {};
    document.getElementById('mfa-modal').dataset.challengeId = challenge.challenge_id || '';
    if (challenge.demo_otp) {
        showToast(`📋 Demo OTP: ${challenge.demo_otp}  (expires in ${challenge.ttl_seconds}s)`, 'warn');
        document.getElementById('demo-otp-badge').textContent = `Demo OTP: ${challenge.demo_otp}`;
        document.getElementById('demo-otp-badge').style.display = 'block';
    }
    // TRANSPARENT CHALLENGE REASONING — show safe phrase to the user
    const whyEl = document.getElementById('mfa-why-reason');
    if (whyEl) {
        const phrase = safeReasonText(data.reasons);
        if (phrase) {
            whyEl.textContent = phrase;
            whyEl.style.display = 'block';
        } else {
            whyEl.style.display = 'none';
        }
    }
    openModal('mfa-modal');
    document.getElementById('otp-input').value = '';
    document.getElementById('otp-error').textContent = '';
}

function onRestrict(data) {
    log(`🚫 Restricted by SentinelX (Score: ${data.risk_score})`, 'error');
    updateRiskGauge(data.risk_score);
    const cooldown = data.cooldown_seconds || 60;
    startRestrictCooldown(cooldown);
    // TRANSPARENT CHALLENGE REASONING — show safe phrase in the banner
    const reasonEl = document.getElementById('restriction-reason');
    if (reasonEl) {
        const phrase = safeReasonText(data.reasons);
        reasonEl.textContent = phrase ? ` ${phrase}` : '';
    }
    showToast(`Rate limited by SentinelX. Read-only for ${cooldown}s.`, 'error');
}

function onRevoke(data) {
    log(`💀 Session REVOKED by SentinelX (Score: ${data.risk_score})`, 'error');
    updateRiskGauge(data.risk_score);

    const isIdentityRevoke = data.error === 'identity_revoked';
    // TRANSPARENT CHALLENGE REASONING — build safe phrase for revoke
    const phrase = safeReasonText(data.reasons);
    const whyText = phrase ? ` ${phrase}` : '';

    // ── SAFETY CONSTRAINT: hard logout fires FIRST, synchronously ──
    const revokedUserId = sx ? sx._identityId : null;
    sx = null;
    document.body.classList.add('revoke-shake');
    setTimeout(() => document.body.classList.remove('revoke-shake'), 600);

    if (isIdentityRevoke && revokedUserId) {
        // Identity-level revoke: show unlock screen instead of login
        showToast(`CRITICAL: Identity revoked.${whyText} Contact your admin for an unlock code.`, 'error');
        _syncLogout();
        showRevokeUnlockScreen(revokedUserId);
    } else {
        showToast(`CRITICAL: Session revoked.${whyText} Logging out…`, 'error');
        _syncLogout();
    }

    // ── Cosmetic flash fires AFTER logout — purely decorative ──
    const flash = document.getElementById('revoke-flash');
    if (flash) {
        flash.classList.add('active');
        setTimeout(() => flash.classList.remove('active'), 750);
    }
}

/* _syncLogout: clears state without touching visuals */
function _syncLogout() {
    const logEl = document.getElementById('activity-log');
    if (logEl) logEl.innerHTML = '';
    _logEntries.length = 0;

    closeModal('mfa-modal');
    closeModal('add-user-modal');
    closePalette();

    const banner = document.getElementById('restriction-banner');
    if (banner) banner.classList.add('hidden');
    const otpBadge = document.getElementById('demo-otp-badge');
    if (otpBadge) otpBadge.style.display = 'none';

    if (adminPollInterval) {
        clearInterval(adminPollInterval);
        adminPollInterval = null;
    }

    switchView('login-view');
    currentUserRole = null;
    _lastRiskScore = 0;
}

/* ════════════════════════════════════════════════
   AUTH
   ════════════════════════════════════════════════ */
document.getElementById('login-btn').addEventListener('click', async () => {
    const userId = document.getElementById('user-select').value;

    sx = new SentinelXClient({
        gatewayBase: GATEWAY_BASE,
        identityId:  userId,
        sessionId:   `sess_${userId}_${Date.now()}`,
        spoofGeo:    null,
        spoofDevice: null,
    });
    sx.onStepUp(onStepUp).onRestrict(onRestrict).onRevoke(onRevoke);

    // Show skeleton immediately
    document.getElementById('profile-data').innerHTML = skeletonProfileHTML();

    setLoading('login-btn', true);
    const profileRes = await sx.call('/profile');
    setLoading('login-btn', false);

    if (profileRes && profileRes.ok) {
        if (profileRes.data.password_not_set) {
            switchView('setup-password-view');
        } else {
            completeLogin(userId, profileRes.data);
        }
    } else if (profileRes && profileRes.data && profileRes.data.error === 'identity_revoked') {
        showToast('Your identity is locked. Contact your admin for an unlock code.', 'error');
        showRevokeUnlockScreen(userId);
    } else {
        showToast('Login failed or denied by SentinelX', 'error');
    }
});

function completeLogin(userId, profileData) {
    // Capture role for command palette filtering (Gap 2 fix)
    currentUserRole = profileData.role || 'student';

    const display = document.getElementById('current-user-display');
    if (display) display.textContent = profileData.name || userId;
    const avatar  = document.getElementById('user-avatar');
    if (avatar)   avatar.textContent = (profileData.name || userId).charAt(0).toUpperCase();

    // Show/hide Admin nav item based on role
    const adminNav = document.getElementById('nav-admin-btn');
    if (adminNav) {
        adminNav.style.display = (currentUserRole === 'admin') ? '' : 'none';
    }

    // Show Simulate Hijack button only in demo/admin mode
    const hijackBtn = document.getElementById('simulate-hijack-btn');
    const resetBtn  = document.getElementById('reset-hijack-btn');
    if (hijackBtn) hijackBtn.style.display = (currentUserRole === 'admin') ? '' : 'none';
    if (resetBtn)  resetBtn.style.display  = 'none'; // hidden until hijack is triggered

    switchView('dashboard-view');
    document.getElementById('restriction-banner').classList.add('hidden');
    document.querySelectorAll('.action-btn').forEach(btn => btn.disabled = false);

    log(`✅ Logged in as ${profileData.name || userId} (${currentUserRole})`, 'success');
    renderProfileData(profileData);

    // Position nav pill on initial active item
    const activeNav = document.querySelector('.nav-item.active');
    if (activeNav) positionNavPill(activeNav);

    // Animate billing counter when it's already the active tab
    const billingEl = document.getElementById('billing-amount-display');
    if (billingEl && document.getElementById('billing-tab').classList.contains('active')) {
        animateCounter(billingEl, 450, '$', '.00');
    }
}

document.getElementById('set-password-btn') && document.getElementById('set-password-btn').addEventListener('click', async () => {
    const pwd = document.getElementById('new-password').value;
    if (!pwd) { showToast('Please enter a password', 'error'); return; }
    setLoading('set-password-btn', true);
    const res = await sx.call('/setup_password', 'POST', { password: pwd });
    setLoading('set-password-btn', false);

    if (res && res.ok) {
        showToast('Password set successfully!', 'success');
        const userId = document.getElementById('user-select').value;
        const profileRes = await sx.call('/profile');
        if (profileRes && profileRes.ok) completeLogin(userId, profileRes.data);
    } else {
        showToast('Failed to set password', 'error');
    }
});

function logout() {
    sx = null;
    _syncLogout();
    loadEnv(); // Refresh dropdown on logout to show newly added users
}
document.getElementById('logout-btn').addEventListener('click', logout);

let adminPollInterval = null;

/* ─── Sidebar nav + pill ─── */
document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const target = e.currentTarget.dataset.target;
        switchTab(target);

        if (adminPollInterval) { clearInterval(adminPollInterval); adminPollInterval = null; }

        if (target === 'admin-tab') {
            document.getElementById('load-users-btn').click();
            loadLockedAccounts();
            adminPollInterval = setInterval(() => {
                const loadBtn = document.getElementById('load-users-btn');
                if (loadBtn) loadBtn.click();
                loadLockedAccounts();
            }, 10000);
        }
    });
});

/* ════════════════════════════════════════════════
   PROFILE TAB
   ════════════════════════════════════════════════ */
async function loadProfile() {
    document.getElementById('profile-data').innerHTML = skeletonProfileHTML();
    setLoading('refresh-profile-btn', true);
    const res = await sx.call('/profile');
    setLoading('refresh-profile-btn', false);
    if (res && res.ok) {
        log('Profile loaded', 'success');
        renderProfileData(res.data);
    }
}

function renderProfileData(data) {
    const roleClass = data.role ? `role-${data.role}` : 'role-student';
    document.getElementById('profile-data').innerHTML = `
        <div class="profile-info-grid">
            <div class="profile-info-item">
                <div class="profile-info-label">Name</div>
                <div class="profile-info-value">${data.name || 'N/A'}</div>
            </div>
            <div class="profile-info-item">
                <div class="profile-info-label">Role</div>
                <div class="profile-info-value">
                    <span class="role-badge ${roleClass}">${data.role || 'N/A'}</span>
                </div>
            </div>
            <div class="profile-info-item">
                <div class="profile-info-label">Email</div>
                <div class="profile-info-value">${data.email || 'N/A'}</div>
            </div>
            <div class="profile-info-item">
                <div class="profile-info-label">Identity ID</div>
                <div class="profile-info-value" style="font-family:'JetBrains Mono',monospace;font-size:13px">${data.identity_id || 'N/A'}</div>
            </div>
        </div>
    `;
}

document.getElementById('refresh-profile-btn').addEventListener('click', loadProfile);
document.getElementById('edit-profile-btn').addEventListener('click', async () => {
    setLoading('edit-profile-btn', true);
    const res = await sx.call('/profile', 'PATCH', { updated: true });
    setLoading('edit-profile-btn', false);
    if (res && res.ok) {
        showToast('Profile patched successfully', 'success');
        log('Profile patched', 'success');
        triggerSuccessBurst(document.getElementById('edit-profile-btn'));
    }
});

/* ════════════════════════════════════════════════
   ORDERS TAB
   ════════════════════════════════════════════════ */
async function loadOrders() {
    document.getElementById('orders-list').innerHTML = skeletonOrdersHTML();
    setLoading('load-orders-btn', true);
    const res = await sx.call('/orders');
    setLoading('load-orders-btn', false);

    if (res && res.ok) {
        const orders = res.data.orders || [];

        // Phase 4: update sparkline with order amounts
        drawSparkline(orders.map(o => parseFloat(o.amount) || 0));

        const html = orders.length
            ? orders.map((o, idx) => `
                <div class="order-item" style="--stagger-delay: ${idx * 40}ms">
                    <div>
                        <div class="order-id">#${o.id}</div>
                        <div class="order-name">${o.item}</div>
                    </div>
                    <div class="order-amount">$${o.amount}</div>
                    <span class="status-badge status-${o.status}">${o.status}</span>
                    <button class="btn-cancel-order action-btn cancel-order-btn" data-id="${o.id}">Cancel</button>
                </div>`).join('')
            : '<div class="empty-state"><p>No orders found.</p></div>';

        document.getElementById('orders-list').innerHTML = html;

        document.querySelectorAll('.cancel-order-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const id    = e.currentTarget.dataset.id;
                const item  = e.currentTarget.closest('.order-item');
                e.currentTarget.disabled = true;
                e.currentTarget.textContent = '…';

                const cancelRes = await sx.call('/orders', 'DELETE', { id });
                if (cancelRes && cancelRes.ok) {
                    showToast(`Order ${id} cancelled`, 'success');
                    log(`Order cancelled: ${id}`, 'success');
                    // Phase 5: exit animation before remove
                    if (item) {
                        item.classList.add('removing');
                        setTimeout(() => loadOrders(), 220);
                    } else {
                        loadOrders();
                    }
                } else {
                    e.currentTarget.disabled = false;
                    e.currentTarget.textContent = 'Cancel';
                }
            });
        });

        log('Orders loaded', 'success');
    }
}

document.getElementById('load-orders-btn').addEventListener('click', loadOrders);

document.getElementById('place-order-btn').addEventListener('click', async () => {
    setLoading('place-order-btn', true);
    const res = await sx.call('/orders', 'POST', { item: 'Enterprise License', amount: 999 });
    setLoading('place-order-btn', false);
    if (res && res.ok) {
        showToast(`Order placed! #${res.data.order_id}`, 'success');
        log(`Order placed: ${res.data.order_id}`, 'success');
        triggerSuccessBurst(document.getElementById('place-order-btn'));
        loadOrders();
    }
});

/* ════════════════════════════════════════════════
   BILLING TAB
   ════════════════════════════════════════════════ */
document.getElementById('pay-btn').addEventListener('click', async () => {
    setLoading('pay-btn', true);
    const res = await sx.call('/payments/transfer', 'POST', { amount: 450 });
    setLoading('pay-btn', false);
    if (res && res.ok) {
        showToast(`Payment sent! TX: ${res.data.tx_id}`, 'success');
        log(`Payment successful: ${res.data.tx_id}`, 'success');
        triggerSuccessBurst(document.getElementById('pay-btn'));
    }
});

/* ════════════════════════════════════════════════
   ADMIN / USERS TAB
   ════════════════════════════════════════════════ */
document.getElementById('load-users-btn').addEventListener('click', async () => {
    document.getElementById('admin-data').innerHTML = skeletonUsersHTML();
    setLoading('load-users-btn', true);
    const res = await sx.call('/admin/users');
    setLoading('load-users-btn', false);

    if (res && res.ok) {
        const users = res.data.users || [];
        const html  = users.map((u, idx) => {
            // PHASE 2: sync_status pill — always visible on card
            const syncStatus = u.sync_status || 'synced';
            const syncPill = syncStatus === 'synced'
                ? `<span class="sync-pill sync-ok" title="Registered on Gateway">✅ Registered on Gateway</span>`
                : syncStatus === 'failed'
                    ? `<span class="sync-pill sync-fail" title="Gateway sync failed — use Retry Sync to re-attempt">❌ Gateway Sync Failed</span>`
                    : `<span class="sync-pill sync-pending" title="Sync pending">⏳ Sync Pending</span>`;

            // PHASE 2: warning badge on card header for failed syncs so admin can't miss them
            const failedBadge = syncStatus === 'failed'
                ? `<span class="sync-warning-badge" title="Gateway sync failed">⚠</span>`
                : '';

            // PHASE 2: Retry Sync button only shown for non-synced users
            const retryBtn = syncStatus !== 'synced'
                ? `<button class="action-btn btn-warning retry-sync-btn" data-id="${u.identity_id}" title="Re-attempt gateway registration">🔄 Retry Sync</button>`
                : '';

            return `
            <div class="user-card${syncStatus === 'failed' ? ' user-card-sync-failed' : ''}" style="--stagger-delay: ${idx * 40}ms" data-identity="${u.identity_id}">
                <div class="user-card-header">
                    <h4 class="user-card-name">${u.name}${failedBadge}</h4>
                    <span class="role-badge role-${u.role}">${u.role}</span>
                </div>
                <div class="user-card-id">${u.identity_id}</div>
                <div class="user-card-sync-row">${syncPill}</div>
                <div class="user-card-actions">
                    <button class="action-btn btn-secondary edit-role-btn" data-id="${u.identity_id}">Edit Role</button>
                    ${retryBtn}
                    <button class="action-btn btn-danger remove-user-btn" data-id="${u.identity_id}">Remove</button>
                </div>
            </div>`;
        }).join('');

        document.getElementById('admin-data').innerHTML = `<div class="user-card-grid">${html}</div>`;

        document.querySelectorAll('.edit-role-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const id      = e.target.dataset.id;
                const newRole = prompt("Enter new role (student, manager, admin):");
                if (!newRole) return;
                const updateRes = await sx.call('/admin/users', 'PATCH', { identity_id: id, role: newRole });
                if (updateRes && updateRes.ok) {
                    showToast(`Role updated for ${id}`, 'success');
                    log(`Role updated: ${id} → ${newRole}`, 'success');
                    document.getElementById('load-users-btn').click();
                }
            });
        });

        document.querySelectorAll('.remove-user-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const id   = e.target.dataset.id;
                const card = e.target.closest('.user-card');
                if (!confirm(`Are you sure you want to remove ${id}?`)) return;

                const delRes = await sx.call('/admin/users', 'DELETE', { identity_id: id });
                if (delRes && delRes.ok) {
                    showToast(`User ${id} removed`, 'success');
                    log(`User removed: ${id}`, 'success');
                    if (card) {
                        card.classList.add('removing');
                        setTimeout(() => document.getElementById('load-users-btn').click(), 220);
                    } else {
                        document.getElementById('load-users-btn').click();
                    }
                }
            });
        });

        // PHASE 2: Retry Sync button handler — re-POSTs to /admin/retry_sync and updates card live
        document.querySelectorAll('.retry-sync-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const id = e.target.dataset.id;
                e.target.disabled = true;
                e.target.textContent = '⏳ Retrying…';

                const retryRes = await sx.call('/admin/retry_sync', 'POST', { identity_id: id });

                if (retryRes && retryRes.ok) {
                    const newStatus = retryRes.data.sync_status;
                    if (newStatus === 'synced') {
                        showToast(`✅ ${id} successfully registered on Gateway`, 'success');
                        log(`Retry sync succeeded for ${id}`, 'success');
                    } else {
                        showToast(`❌ Retry failed for ${id}: ${retryRes.data.gateway_error || 'Gateway unreachable'}`, 'error');
                        log(`Retry sync still failing for ${id}`, 'error');
                    }
                    document.getElementById('load-users-btn').click();
                } else {
                    showToast('Retry Sync request failed', 'error');
                    e.target.disabled = false;
                    e.target.textContent = '🔄 Retry Sync';
                }
            });
        });

        log(`Loaded ${users.length} users`, 'success');
    } else {
        document.getElementById('admin-data').innerHTML = `<p class="error-text">Access Denied by SentinelX.</p>`;
    }
});

/* ─── Add User Modal ─── */
function openAddUserModal() {
    document.getElementById('new-user-name').value = '';
    document.querySelectorAll('input[name="new-user-role"]').forEach(r => { r.checked = r.value === 'student'; });
    openModal('add-user-modal');
}
function closeAddUserModal() { closeModal('add-user-modal'); }

document.getElementById('open-add-user-btn') && document.getElementById('open-add-user-btn').addEventListener('click', openAddUserModal);
document.getElementById('close-add-user-modal') && document.getElementById('close-add-user-modal').addEventListener('click', closeAddUserModal);
document.getElementById('cancel-add-user-modal') && document.getElementById('cancel-add-user-modal').addEventListener('click', closeAddUserModal);

// Close on backdrop click
document.getElementById('add-user-modal') && document.getElementById('add-user-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeAddUserModal();
});

document.getElementById('add-user-btn') && document.getElementById('add-user-btn').addEventListener('click', async () => {
    const name   = document.getElementById('new-user-name').value.trim();
    const roleEl = document.querySelector('input[name="new-user-role"]:checked');
    const role   = roleEl ? roleEl.value : 'student';
    if (!name) { showToast('Name is required', 'error'); return; }

    const uid = `u_${name.toLowerCase().replace(/\s+/g, '_')}_${Date.now().toString().slice(-4)}`;
    setLoading('add-user-btn', true);
    const payload = { identity_id: uid, name, role };
    if (role === 'agent') {
        payload.declared_scope = ['/profile', '/orders']; // Default safe scope for new agents
    }
    const res = await sx.call('/admin/add_user', 'POST', payload);
    setLoading('add-user-btn', false);

    if (res && res.ok) {
        // PHASE 2: Local account was always created. Check gateway sync outcome separately.
        const syncStatus = res.data?.gateway_sync || res.data?.user?.sync_status || 'synced';
        if (syncStatus === 'synced') {
            showToast(`\u2705 ${name} created and registered on Gateway`, 'success');
            log(`Admin added user: ${uid} (${role}) — Gateway: \u2705 synced`, 'success');
        } else {
            showToast(`\u26a0\ufe0f ${name} created locally but Gateway Sync Failed — use Retry Sync`, 'warn');
            log(`Admin added user: ${uid} (${role}) — Gateway: \u274c sync failed`, 'warn');
        }
        triggerSuccessBurst(document.getElementById('add-user-btn'));
        closeAddUserModal();
        document.getElementById('load-users-btn').click();
    } else {
        const errorDetail = res?.data?.detail || 'Unknown error';
        showToast(`Failed to create user: ${errorDetail}`, 'error');
        log(`Admin add user failed for ${uid}: ${errorDetail}`, 'error');
    }
});

/* ─── Simulate Hijack / Reset Hijack ─── */
document.getElementById('simulate-hijack-btn') && document.getElementById('simulate-hijack-btn').addEventListener('click', async () => {
    const res = await sx.call('/admin/simulate_hijack', 'POST');
    if (res && res.ok) {
        showToast('⚠️ Agent hijacked! Watch for RESTRICT/REVOKE in the activity log.', 'warn');
        log('🤖 Agent hijack TRIGGERED — SupportBot now making out-of-scope requests', 'warn');
        const hijackBtn = document.getElementById('simulate-hijack-btn');
        const resetBtn  = document.getElementById('reset-hijack-btn');
        if (hijackBtn) hijackBtn.style.display = 'none';
        if (resetBtn)  resetBtn.style.display  = '';
    } else {
        showToast('Failed to trigger hijack', 'error');
    }
});

document.getElementById('reset-hijack-btn') && document.getElementById('reset-hijack-btn').addEventListener('click', async () => {
    const res = await sx.call('/admin/reset_hijack', 'POST');
    if (res && res.ok) {
        showToast('✅ Agent behavior restored to normal.', 'success');
        log('🤖 Agent hijack RESET — SupportBot back to normal operations', 'success');
        const hijackBtn = document.getElementById('simulate-hijack-btn');
        const resetBtn  = document.getElementById('reset-hijack-btn');
        if (hijackBtn) hijackBtn.style.display = '';
        if (resetBtn)  resetBtn.style.display  = 'none';
    } else {
        showToast('Failed to reset hijack', 'error');
    }
});

/* ─── MFA Modal ─── */
document.getElementById('cancel-mfa-btn').addEventListener('click', () => {
    closeModal('mfa-modal');
    document.getElementById('demo-otp-badge').style.display = 'none';
    log('MFA cancelled', 'warn');
});

// Close MFA on backdrop click
document.getElementById('mfa-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
        closeModal('mfa-modal');
        document.getElementById('demo-otp-badge').style.display = 'none';
        log('MFA cancelled', 'warn');
    }
});

document.getElementById('verify-otp-btn').addEventListener('click', async () => {
    const code  = document.getElementById('otp-input').value.trim();
    const errEl = document.getElementById('otp-error');
    errEl.textContent = '';

    setLoading('verify-otp-btn', true);
    const result = await sx.verifyOtp(code);
    setLoading('verify-otp-btn', false);

    if (result === 'ok') {
        closeModal('mfa-modal');
        document.getElementById('demo-otp-badge').style.display = 'none';
        document.getElementById('otp-input').value = '';
        log('✅ MFA verified successfully', 'success');
        showToast('Identity verified. Action unlocked.', 'success');

        if (window.pendingDevAction) {
            const action = window.pendingDevAction;
            window.pendingDevAction = null;
            setTimeout(action, 500);
        }
    } else if (result === 'expired') {
        errEl.textContent = 'Code expired. Retry the action to get a new OTP.';
        log('OTP expired', 'error');
    } else if (result === 'used') {
        errEl.textContent = 'This code has already been used. Retry the action.';
        log('OTP already consumed', 'error');
    } else {
        errEl.textContent = 'Incorrect code. Try again.';
        log('OTP wrong', 'error');
    }
});

/* ════════════════════════════════════════════════
   PHASE 2 — COMMAND PALETTE (Gap 2: role-filtered)
   ════════════════════════════════════════════════ */
const ALL_COMMANDS = [
    // Available to all authenticated users
    { id: 'nav-profile',  label: 'Profile',         desc: 'View your account',         icon: '👤', action: () => switchTab('profile-tab'),  roles: ['student', 'manager', 'admin', 'service'], shortcut: 'P' },
    { id: 'nav-orders',   label: 'Orders',           desc: 'View transactions',          icon: '📦', action: () => switchTab('orders-tab'),   roles: ['student', 'manager', 'admin', 'service'], shortcut: 'O' },
    { id: 'nav-billing',  label: 'Billing',          desc: 'Manage payments',            icon: '💳', action: () => switchTab('billing-tab'),  roles: ['student', 'manager', 'admin', 'service'] },
    { id: 'act-refresh',  label: 'Refresh Profile',  desc: 'Reload profile data',        icon: '🔄', action: () => { switchTab('profile-tab'); loadProfile(); }, roles: ['student', 'manager', 'admin', 'service'] },
    { id: 'act-orders',   label: 'Load Orders',      desc: 'Fetch latest orders',        icon: '📋', action: () => { switchTab('orders-tab'); loadOrders(); },  roles: ['student', 'manager', 'admin', 'service'] },
    { id: 'act-order',    label: 'Place Order',      desc: 'Create a new order',         icon: '➕', action: () => { switchTab('orders-tab'); document.getElementById('place-order-btn')?.click(); }, roles: ['student', 'manager', 'admin', 'service'] },
    // Admin-only commands
    { id: 'nav-admin',    label: 'Admin',            desc: 'Team administration',        icon: '🛡', action: () => switchTab('admin-tab'),    roles: ['admin'] },
    { id: 'act-users',    label: 'Load Users',       desc: 'Refresh team member list',   icon: '👥', action: () => { switchTab('admin-tab'); document.getElementById('load-users-btn')?.click(); }, roles: ['admin'] },
    { id: 'act-adduser',  label: 'Add User',         desc: 'Open add user dialog',       icon: '➕', action: () => { switchTab('admin-tab'); openAddUserModal(); }, roles: ['admin'] },
];

function _getFilteredCommands(query) {
    const role = currentUserRole || 'student';
    let cmds = ALL_COMMANDS.filter(c => c.roles.includes(role));
    if (query) {
        const q = query.toLowerCase();
        cmds = cmds.filter(c =>
            c.label.toLowerCase().includes(q) ||
            c.desc.toLowerCase().includes(q)
        );
    }
    return cmds;
}

let _paletteSelected = 0;
let _paletteVisible  = false;

function openPalette() {
    if (!sx) return; // not logged in
    const overlay = document.getElementById('command-palette-overlay');
    const input   = document.getElementById('command-palette-input');
    overlay.classList.remove('hidden', 'closing');
    input.value = '';
    _paletteVisible = true;
    _renderPaletteList('');
    setTimeout(() => input.focus(), 30);
}

function closePalette() {
    const overlay = document.getElementById('command-palette-overlay');
    overlay.classList.add('closing');
    _paletteVisible = false;
    setTimeout(() => {
        overlay.classList.add('hidden');
        overlay.classList.remove('closing');
    }, 130);
}

function _renderPaletteList(query) {
    const list   = document.getElementById('command-palette-list');
    const cmds   = _getFilteredCommands(query);
    _paletteSelected = 0;

    if (!cmds.length) {
        list.innerHTML = `<div id="command-palette-empty">No matching actions</div>`;
        return;
    }

    list.innerHTML = cmds.map((c, i) => `
        <div class="cp-item ${i === 0 ? 'selected' : ''}" data-idx="${i}" role="option" aria-selected="${i === 0}">
            <div class="cp-item-icon">${c.icon}</div>
            <div>
                <div class="cp-item-label">${c.label}</div>
                <div class="cp-item-desc">${c.desc}</div>
            </div>
            ${c.shortcut ? `<span class="cp-item-shortcut">${c.shortcut}</span>` : ''}
        </div>`).join('');

    list.querySelectorAll('.cp-item').forEach((el, i) => {
        el.addEventListener('mouseenter', () => _selectPaletteItem(i));
        el.addEventListener('click', () => _executePaletteItem(cmds, i));
    });
}

function _selectPaletteItem(idx) {
    const items = document.querySelectorAll('#command-palette-list .cp-item');
    items.forEach((el, i) => {
        el.classList.toggle('selected', i === idx);
        el.setAttribute('aria-selected', i === idx ? 'true' : 'false');
    });
    _paletteSelected = idx;
    // Scroll into view
    if (items[idx]) items[idx].scrollIntoView({ block: 'nearest' });
}

function _executePaletteItem(cmds, idx) {
    const cmd = cmds[idx];
    if (!cmd) return;
    closePalette();
    setTimeout(() => cmd.action(), 140);
}

document.getElementById('command-palette-input').addEventListener('input', (e) => {
    _renderPaletteList(e.target.value);
});

document.getElementById('command-palette-input').addEventListener('keydown', (e) => {
    const list = document.getElementById('command-palette-list');
    const items = [...list.querySelectorAll('.cp-item')];
    const query = document.getElementById('command-palette-input').value;
    const cmds  = _getFilteredCommands(query);

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        _selectPaletteItem(Math.min(_paletteSelected + 1, items.length - 1));
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        _selectPaletteItem(Math.max(_paletteSelected - 1, 0));
    } else if (e.key === 'Enter') {
        e.preventDefault();
        _executePaletteItem(cmds, _paletteSelected);
    } else if (e.key === 'Escape') {
        e.preventDefault();
        closePalette();
    }
});

// Close on backdrop click
document.getElementById('command-palette-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closePalette();
});

// Global Ctrl/Cmd+K trigger
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (_paletteVisible) closePalette();
        else openPalette();
    }
    if (e.key === 'Escape' && _paletteVisible) closePalette();
});

/* ════════════════════════════════════════════════
   DEV TEST PANEL
   ════════════════════════════════════════════════ */
document.getElementById('dev-send-btn') && document.getElementById('dev-send-btn').addEventListener('click', async () => {
    if (!sx) { showToast('Please log in first', 'error'); return; }
    const verb     = document.getElementById('dev-verb-select').value;
    const endpoint = document.getElementById('dev-endpoint-select').value;
    setLoading('dev-send-btn', true);

    try {
        const res = await sx.call(endpoint, verb, { dev_test: true });
        if (res && res.ok) {
            const risk    = res.headers?.riskScore || "N/A";
            const tier    = res.headers?.tier ? res.headers.tier.toUpperCase() : "ALLOW";
            const latency = res.headers?.latencyMs || "N/A";
            document.getElementById('dev-result').innerHTML = `<span style="color:#3fb950">SUCCESS (${res.status})</span><br><span style="color:#8b949e">Risk: ${risk} | Tier: ${tier} | Latency: ${latency}ms</span><br><br>${JSON.stringify(res.data)}`;
            log(`Dev Request: ${verb} ${endpoint} (Success)`, 'info');
        } else if (res) {
            let tier  = "BLOCKED";
            let color = "#f85149";
            if (res.status === 401 && res.data?.error === 'step_up_required')  { tier = "STEP-UP";  color = "#f59e0b"; window.pendingDevAction = () => document.getElementById('dev-send-btn').click(); }
            else if (res.status === 429 && res.data?.error === 'restricted')   { tier = "RESTRICT"; color = "#f97316"; }
            else if (res.status === 401 && (res.data?.error === 'session_revoked' || res.data?.error === 'identity_revoked')) { tier = "REVOKE"; color = "#ef4444"; }
            else if (res.status === 403 && res.data?.error === 'session_revoked') { tier = "REVOKE"; color = "#ef4444"; }

            const risk  = res.data?.risk_score || "N/A";
            document.getElementById('dev-result').innerHTML = `<span style="color:${color}">${tier} (${res.status})</span><br><span style="color:#8b949e">Risk: ${risk} | Tier: ${tier}</span><br><br>${JSON.stringify(res.data)}`;
            log(`Dev Request: ${verb} ${endpoint} (${tier})`, 'info');
        }
    } catch (ex) {
        document.getElementById('dev-result').innerHTML = `<span style="color:#f85149">ERROR:</span><br>${ex.toString()}`;
    }
    setLoading('dev-send-btn', false);
});

/* ─── Bulk Request Engine ─── */
const BULK_MAX        = 1000;
const BULK_BATCH_SIZE = 15;
let bulkStopFlag = false;

document.querySelectorAll('.bulk-preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.getElementById('dev-bulk-count').value = btn.dataset.count;
    });
});

document.getElementById('dev-stop-bulk-btn') && document.getElementById('dev-stop-bulk-btn').addEventListener('click', () => {
    bulkStopFlag = true;
});

document.getElementById('dev-send-bulk-btn') && document.getElementById('dev-send-bulk-btn').addEventListener('click', async () => {
    if (!isDemoMode) { showToast('Bulk burst unavailable outside demo mode', 'error'); return; }
    if (!sx) { showToast('Please log in first', 'error'); return; }

    const verb     = document.getElementById('dev-verb-select').value;
    const endpoint = document.getElementById('dev-endpoint-select').value;
    const rawCount = parseInt(document.getElementById('dev-bulk-count').value, 10);
    const total    = Math.min(Math.max(1, rawCount || 1), BULK_MAX);
    document.getElementById('dev-bulk-count').value = total;

    bulkStopFlag = false;
    const tally = { ALLOW: 0, 'STEP-UP': 0, RESTRICT: 0, REVOKE: 0, ERROR: 0 };
    let sent = 0, latencySum = 0, stepUpAt = null, restrictAt = null;
    const startTime = Date.now();

    const progressEl = document.getElementById('dev-bulk-progress');
    const resultEl   = document.getElementById('dev-result');
    const stopBtn    = document.getElementById('dev-stop-bulk-btn');
    const sendBtn    = document.getElementById('dev-send-bulk-btn');

    progressEl.style.display = 'block';
    stopBtn.style.display    = 'inline-block';
    sendBtn.disabled         = true;

    function renderProgress(stopped = false) {
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        const avgLat  = sent > 0 ? Math.round(latencySum / sent) : 0;
        progressEl.innerHTML = `
<span style="color:#c9d1d9">${stopped ? '⏹ Stopped' : '⏳ Sending…'} ${sent}/${total} | ${elapsed}s | avg ${avgLat}ms</span><br>
<span style="color:#3fb950">ALLOW: ${tally.ALLOW}</span>  
<span style="color:#f59e0b">STEP-UP: ${tally['STEP-UP']}</span>  
<span style="color:#f97316">RESTRICT: ${tally.RESTRICT}</span>  
<span style="color:#ef4444">REVOKE: ${tally.REVOKE}</span>  
<span style="color:#8b949e">ERR: ${tally.ERROR}</span>`;
    }

    function classifyResponse(res) {
        if (!res)                                                          return 'ERROR';
        if (res.ok)                                                        return 'ALLOW';
        if (res.status === 401 && res.data?.error === 'step_up_required') return 'STEP-UP';
        if (res.status === 429 && res.data?.error === 'restricted')        return 'RESTRICT';
        if (res.status === 401 && (res.data?.error === 'session_revoked' || res.data?.error === 'identity_revoked'))   return 'REVOKE';
        return 'ERROR';
    }

    let revokedAfter = null;
    // Leave handlers active so UI reacts to enforcement
    const savedHandlers = { ...sx._handlers };
    batchLoop: for (let i = 0; i < total; i += BULK_BATCH_SIZE) {
        if (bulkStopFlag) break batchLoop;
        const batchSize = Math.min(BULK_BATCH_SIZE, total - i);
        const batch = Array.from({ length: batchSize }, (_, j) =>
            sx.call(endpoint, verb, { dev_test: true, bulk_seq: i + j + 1 })
        );
        const results = await Promise.allSettled(batch);

        for (let k = 0; k < results.length; k++) {
            const reqNum = i + k + 1;
            const res    = results[k].status === 'fulfilled' ? results[k].value : null;
            const tier   = classifyResponse(res);
            tally[tier]++;
            sent++;
            const lat = parseInt(res?.headers?.latencyMs || '0', 10);
            latencySum += lat || 0;
            if (tier === 'STEP-UP'  && stepUpAt   === null) stepUpAt   = reqNum;
            if (tier === 'RESTRICT' && restrictAt  === null) restrictAt = reqNum;
            if (tier === 'REVOKE') {
                revokedAfter = reqNum;
                bulkStopFlag = true;
                break batchLoop;
            }
        }
        renderProgress();
    }

    sx._handlers   = savedHandlers;
    stopBtn.style.display = 'none';
    sendBtn.disabled      = false;
    renderProgress(true);

    const avgLat       = sent > 0 ? Math.round(latencySum / sent) : 0;
    const totalPct     = (k) => sent > 0 ? ` (${Math.round(tally[k] / sent * 100)}%)` : '';
    const escalation   = [
        stepUpAt   ? `escalated to STEP-UP at req #${stepUpAt}`  : null,
        restrictAt ? `RESTRICT at req #${restrictAt}`             : null,
    ].filter(Boolean).join(', ');
    const earlyStop    = revokedAfter
        ? `<br><span style="color:#ef4444">⛔ Burst stopped early: session revoked after ${revokedAfter} of ${total} requests.</span>`
        : (bulkStopFlag ? `<br><span style="color:#d29922">⏹ Manually stopped at ${sent} of ${total}.</span>` : '');

    resultEl.innerHTML = `
<span style="color:#c9d1d9;font-weight:600;">Burst Summary — ${sent}/${total} sent | avg ${avgLat}ms</span><br>
<span style="color:#3fb950">ALLOW ${tally.ALLOW}${totalPct('ALLOW')}</span>  <span style="color:#f59e0b">STEP-UP ${tally['STEP-UP']}${totalPct('STEP-UP')}</span>  <span style="color:#f97316">RESTRICT ${tally.RESTRICT}${totalPct('RESTRICT')}</span>  <span style="color:#ef4444">REVOKE ${tally.REVOKE}${totalPct('REVOKE')}</span><br>
${escalation ? `<span style="color:#8b949e">${escalation}</span><br>` : ''}${earlyStop}`;

    log(`Bulk burst: ${sent}/${total} | ALLOW ${tally.ALLOW} | STEP-UP ${tally['STEP-UP']} | RESTRICT ${tally.RESTRICT} | REVOKE ${tally.REVOKE}`, 'info');
});

/* ════════════════════════════════════════════════
   TIERED RECOVERY SYSTEM
   ════════════════════════════════════════════════ */

/* ─── Phase 2: RESTRICT cooldown with live countdown ─── */
let _restrictCooldownTimer = null;

function startRestrictCooldown(cooldownSeconds) {
    const banner = document.getElementById('restriction-banner');
    const textEl = document.getElementById('restriction-text');
    const countdownEl = document.getElementById('restriction-countdown');
    banner.classList.remove('hidden');
    document.querySelectorAll('.action-btn').forEach(btn => btn.disabled = true);

    let remaining = cooldownSeconds;
    textEl.textContent = 'Restricted due to unusual activity. Access will restore automatically if activity normalizes.';
    countdownEl.textContent = `${remaining}s`;

    if (_restrictCooldownTimer) clearInterval(_restrictCooldownTimer);
    _restrictCooldownTimer = setInterval(() => {
        remaining--;
        countdownEl.textContent = `${remaining}s`;
        if (remaining <= 0) {
            clearInterval(_restrictCooldownTimer);
            _restrictCooldownTimer = null;
            banner.classList.add('hidden');
            document.querySelectorAll('.action-btn').forEach(btn => btn.disabled = false);
            countdownEl.textContent = '';
            textEl.textContent = 'Account restricted — read-only mode active.';
            showToast('Restriction lifted. You can resume normal activity.', 'success');
            log('✅ RESTRICT cooldown expired — access restored', 'success');
        }
    }, 1000);
}

/* ─── Phase 3: REVOKE unlock screen ─── */
let _revokedIdentityId = null;

function showRevokeUnlockScreen(identityId) {
    _revokedIdentityId = identityId;
    document.getElementById('revoke-unlock-identity').value = identityId;
    document.getElementById('revoke-unlock-code').value = '';
    document.getElementById('revoke-unlock-error').textContent = '';
    switchView('revoke-unlock-view');
}

document.getElementById('revoke-unlock-btn') && document.getElementById('revoke-unlock-btn').addEventListener('click', async () => {
    const code = document.getElementById('revoke-unlock-code').value.trim();
    const errEl = document.getElementById('revoke-unlock-error');
    errEl.textContent = '';

    if (!code || code.length < 6) {
        errEl.textContent = 'Please enter the 6-digit unlock code from your administrator.';
        return;
    }

    const identityId = _revokedIdentityId || document.getElementById('revoke-unlock-identity').value;
    setLoading('revoke-unlock-btn', true);

    try {
        const res = await fetch(`${GATEWAY_BASE}/unlock/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identity_id: identityId, code }),
        });
        const data = await res.json();

        if (data.result === 'ok') {
            showToast('Identity unlocked! You can now log in.', 'success');
            _revokedIdentityId = null;
            switchView('login-view');
        } else if (data.result === 'expired') {
            errEl.textContent = 'Unlock code has expired. Ask your administrator for a new one.';
        } else if (data.result === 'used') {
            errEl.textContent = 'This code has already been used. Request a new one.';
        } else if (data.result === 'not_revoked') {
            showToast('Your identity is no longer locked. Try logging in.', 'success');
            switchView('login-view');
        } else {
            errEl.textContent = 'Incorrect code. Please try again.';
        }
    } catch (e) {
        errEl.textContent = 'Could not reach the server. Try again.';
    }

    setLoading('revoke-unlock-btn', false);
});

document.getElementById('revoke-back-to-login') && document.getElementById('revoke-back-to-login').addEventListener('click', () => {
    _revokedIdentityId = null;
    switchView('login-view');
});

/* ─── Phase 4: Admin Locked Accounts panel ─── */
async function loadLockedAccounts() {
    if (!sx) return;
    const listEl = document.getElementById('locked-accounts-list');
    const badge = document.getElementById('locked-count-badge');

    try {
        const res = await sx.call('/admin/locked_accounts');
        if (res && res.ok) {
            const accounts = res.data.locked_accounts || [];
            if (badge) {
                badge.textContent = accounts.length;
                badge.style.display = accounts.length > 0 ? 'inline-flex' : 'none';
            }
            if (accounts.length === 0) {
                listEl.innerHTML = '<div class="empty-state"><p style="opacity:0.4">No locked accounts</p></div>';
                return;
            }
            listEl.innerHTML = accounts.map((a, idx) => `
                <div class="locked-account-card" style="--stagger-delay: ${idx * 40}ms">
                    <div class="locked-account-info">
                        <div class="locked-account-name">${a.name}</div>
                        <div class="locked-account-id">${a.identity_id}</div>
                        <span class="role-badge role-${a.role}">${a.role}</span>
                    </div>
                    <div class="locked-account-risk">
                        <span class="locked-risk-score" style="color:#ef4444;">Score: ${a.risk_score}</span>
                    </div>
                    <div style="display:flex; gap: 8px;">
                        <button class="btn-danger action-btn generate-unlock-btn" data-id="${a.identity_id}" data-name="${a.name}">
                            🔑 Generate Unlock Code
                        </button>
                        <button class="btn-ghost direct-unlock-btn" data-id="${a.identity_id}" data-name="${a.name}" style="color:#10b981; border-color:rgba(16,185,129,0.3);">
                            🔓 Direct Unlock
                        </button>
                    </div>
                </div>
            `).join('');

            listEl.querySelectorAll('.generate-unlock-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.currentTarget.dataset.id;
                    const name = e.currentTarget.dataset.name;
                    e.currentTarget.disabled = true;
                    e.currentTarget.textContent = 'Generating…';

                    try {
                        const unlockRes = await sx.call('/admin/unlock/request', 'POST', { identity_id: id });
                        if (unlockRes && unlockRes.ok) {
                            const code = unlockRes.data.unlock_code;
                            const ttl = unlockRes.data.ttl_seconds;
                            showToast(`🔑 Unlock code for ${name}: ${code} (expires in ${ttl}s)`, 'success');
                            log(`Admin generated unlock code for ${id}: ${code}`, 'success');
                            e.currentTarget.textContent = `Code: ${code}`;
                            e.currentTarget.style.background = '#10b981';
                            e.currentTarget.style.color = '#fff';
                        } else {
                            showToast('Failed to generate unlock code', 'error');
                            e.currentTarget.disabled = false;
                            e.currentTarget.textContent = '🔑 Generate Unlock Code';
                        }
                    } catch (ex) {
                        showToast('Error reaching gateway', 'error');
                        e.currentTarget.disabled = false;
                        e.currentTarget.textContent = '🔑 Generate Unlock Code';
                    }
                });
            });

            listEl.querySelectorAll('.direct-unlock-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const id = e.currentTarget.dataset.id;
                    const name = e.currentTarget.dataset.name;
                    e.currentTarget.disabled = true;
                    e.currentTarget.textContent = '🔓 Unlocking…';

                    try {
                        const unlockRes = await sx.call('/admin/unlock/direct', 'POST', { identity_id: id });
                        if (unlockRes && unlockRes.ok) {
                            showToast(`🔓 Successfully unlocked ${name} and reset risk score.`, 'success');
                            log(`Admin directly unlocked ${id}`, 'success');
                            loadLockedAccounts(); // refresh list
                        } else {
                            showToast(`Failed to direct unlock ${name}`, 'error');
                            e.currentTarget.disabled = false;
                            e.currentTarget.textContent = '🔓 Direct Unlock';
                        }
                    } catch (ex) {
                        showToast('Error reaching gateway', 'error');
                        e.currentTarget.disabled = false;
                        e.currentTarget.textContent = '🔓 Direct Unlock';
                    }
                });
            });

            log(`Loaded ${accounts.length} locked account(s)`, 'info');
        }
    } catch (e) {
        // Silently fail for non-admin users
    }
}

document.getElementById('refresh-locked-btn') && document.getElementById('refresh-locked-btn').addEventListener('click', loadLockedAccounts);

/* ─── Dev Reset Locks button ─── */
document.getElementById('dev-reset-locks-btn') && document.getElementById('dev-reset-locks-btn').addEventListener('click', async () => {
    if (!sx) { showToast('Please log in first', 'error'); return; }
    try {
        const res = await sx.call('/admin/unlock/reset_all', 'POST');
        if (res && res.ok) {
            const count = res.data.count || 0;
            showToast(`🔓 Cleared ${count} identity lock(s)`, 'success');
            log(`Dev reset: cleared ${count} identity locks`, 'success');
            loadLockedAccounts();
        } else {
            showToast('Failed to reset locks (admin role required)', 'error');
        }
    } catch (e) {
        showToast('Error reaching gateway', 'error');
    }
});

/* ════════════════════════════════════════════════
   BOOT
   ════════════════════════════════════════════════ */
loadEnv();
