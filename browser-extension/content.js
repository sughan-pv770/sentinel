/**
 * SentinelX Content Script
 *
 * Injected into every page. Responsibilities:
 *  - Detect login/logout events by watching for common auth patterns
 *  - Listen for security events from the background service worker
 *  - Inject the SentinelX shield badge (bottom-right corner)
 *  - Show in-page banners for session_terminated / session_restricted
 *  - Auto-detect the SentinelX portal SDK if present
 */

(function () {
  'use strict';

  // Avoid double-injection
  if (window.__sentinelxInjected) return;
  window.__sentinelxInjected = true;

  // ── Shield badge ─────────────────────────────────────────────────────────────
  let badge = null;
  let currentStatus = 'inactive'; // inactive | protected | warning | critical

  function injectBadge() {
    if (badge) return;
    badge = document.createElement('div');
    badge.id = 'sentinelx-shield-badge';
    badge.innerHTML = `
      <div id="sx-badge-inner">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        <span id="sx-badge-label">Protected</span>
      </div>
    `;
    badge.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 2147483647;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 12px;
      font-weight: 600;
      cursor: default;
      user-select: none;
      transition: all 0.3s ease;
    `;

    const inner = badge.querySelector('#sx-badge-inner');
    inner.style.cssText = `
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: rgba(17, 24, 39, 0.92);
      border: 1px solid rgba(34, 197, 94, 0.4);
      border-radius: 20px;
      color: #4ade80;
      backdrop-filter: blur(8px);
      box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    `;

    document.body.appendChild(badge);
    updateBadge('protected');
  }

  function updateBadge(status) {
    if (!badge) return;
    currentStatus = status;
    const inner = badge.querySelector('#sx-badge-inner');
    const label = badge.querySelector('#sx-badge-label');

    const styles = {
      inactive:  { border: 'rgba(100,116,139,0.4)', color: '#94a3b8', text: 'SentinelX' },
      protected: { border: 'rgba(34,197,94,0.4)',   color: '#4ade80', text: 'Protected' },
      warning:   { border: 'rgba(245,158,11,0.4)',  color: '#fbbf24', text: 'Warning' },
      critical:  { border: 'rgba(239,68,68,0.4)',   color: '#f87171', text: 'Session Ending' },
      mfa:       { border: 'rgba(99,102,241,0.4)',  color: '#a5b4fc', text: 'Verify Identity' },
    };

    const s = styles[status] || styles.inactive;
    inner.style.borderColor = s.border;
    inner.style.color = s.color;
    label.textContent = s.text;
  }

  // ── In-page banner ────────────────────────────────────────────────────────────
  function showBanner(type, message) {
    // Remove existing banner
    const existing = document.getElementById('sentinelx-banner');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.id = 'sentinelx-banner';

    const isRevoke = type === 'terminated';
    banner.style.cssText = `
      position: fixed;
      top: 0; left: 0; right: 0;
      z-index: 2147483646;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 14px;
      font-weight: 500;
      color: #fff;
      background: ${isRevoke ? 'rgba(185,28,28,0.97)' : 'rgba(146,64,14,0.97)'};
      border-bottom: 1px solid ${isRevoke ? 'rgba(239,68,68,0.5)' : 'rgba(245,158,11,0.5)'};
      backdrop-filter: blur(12px);
      animation: sx-slide-down 0.3s ease;
    `;

    banner.innerHTML = `
      <style>
        @keyframes sx-slide-down {
          from { transform: translateY(-100%); opacity: 0; }
          to   { transform: translateY(0); opacity: 1; }
        }
      </style>
      <div style="display:flex;align-items:center;gap:10px;">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        <strong>SentinelX:</strong> ${escHtml(message)}
      </div>
      ${!isRevoke ? `<button id="sx-banner-dismiss" style="
        background: rgba(255,255,255,0.2); border: none; border-radius: 6px;
        color: #fff; padding: 5px 12px; cursor: pointer; font-size: 12px;">
        Dismiss
      </button>` : ''}
    `;

    document.body.prepend(banner);

    const btn = banner.querySelector('#sx-banner-dismiss');
    if (btn) btn.addEventListener('click', () => banner.remove());

    if (!isRevoke) setTimeout(() => banner.remove(), 8000);
  }

  // ── Listen for messages from background service worker ───────────────────────
  chrome.runtime.onMessage.addListener((msg) => {
    switch (msg.type) {
      case 'SESSION_TERMINATED':
        updateBadge('critical');
        showBanner('terminated',
          `Your session has been terminated. Reason: ${msg.data?.reason || 'security policy'}. Please sign in again.`
        );
        break;

      case 'SESSION_RESTRICTED':
        updateBadge('warning');
        showBanner('restricted',
          msg.data?.message || 'Unusual activity detected. Some features may be limited.'
        );
        break;

      case 'MFA_CHALLENGE':
        updateBadge('mfa');
        showBanner('restricted', 'Security check required — please verify your identity in the portal.');
        break;
    }
  });

  // ── Auto-detect login by watching for cookie / auth API calls ─────────────────
  // Intercept fetch to detect when a page logs in via a known auth endpoint pattern
  const _fetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await _fetch.apply(this, args);
    try {
      const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      if (response.ok && (url.includes('/login') || url.includes('/auth/login') || url.includes('/signin'))) {
        const clone = response.clone();
        clone.json().then(data => {
          const identityId = data?.identity_id || data?.user?.id || data?.userId || 'unknown';
          chrome.runtime.sendMessage({ type: 'SENTINELX_LOGIN', identityId });
          injectBadge();
        }).catch(() => {});
      }
      if (url.includes('/logout') || url.includes('/signout')) {
        chrome.runtime.sendMessage({ type: 'SENTINELX_LOGOUT' });
        updateBadge('inactive');
      }
    } catch { /* ignore */ }
    return response;
  };

  // ── Check if SentinelX portal SDK is already on this page ─────────────────────
  window.addEventListener('load', () => {
    // If the page uses window.__sentinelxPortal (injected by the SentinelX React app),
    // we know it's a protected portal and can connect immediately.
    if (window.__sentinelxPortal) {
      injectBadge();
    }
    // Also check for SentinelX session SSE stream presence
    chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (status) => {
      if (status?.session) injectBadge();
    });
  });

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

})();
