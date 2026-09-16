/**
 * SentinelX Background Service Worker
 *
 * Responsibilities:
 *  - Track per-tab session metadata (identity, risk score, gateway URL)
 *  - Relay messages between content script and the SentinelX gateway
 *  - Maintain SSE connection to the gateway for real-time events
 *  - Trigger browser notifications for security events
 *  - Store user settings via chrome.storage
 */

// ── Default settings ──────────────────────────────────────────────────────────
const DEFAULT_SETTINGS = {
  gatewayUrl: 'http://localhost:8080',
  enabled: true,
  notifyOnRestrict: true,
  notifyOnRevoke: true,
  notifyOnStepUp: true,
  protectedDomains: [],  // empty = protect all domains
};

// ── In-memory state ───────────────────────────────────────────────────────────
let settings = { ...DEFAULT_SETTINGS };
let tabSessions = {};     // tabId → { identityId, riskScore, tier, gatewayUrl }
let sseEventSource = null;
let currentIdentityId = null;

// ── Init ──────────────────────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(async () => {
  await chrome.storage.sync.set({ settings: DEFAULT_SETTINGS });
  console.log('[SentinelX] Extension installed');
});

// Load settings on startup
chrome.storage.sync.get('settings', (data) => {
  if (data.settings) settings = { ...DEFAULT_SETTINGS, ...data.settings };
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.settings) {
    settings = { ...DEFAULT_SETTINGS, ...changes.settings.newValue };
    reconnectSSE();
  }
});

// ── Message handling from content scripts / popup ─────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const tabId = sender.tab?.id;

  switch (msg.type) {
    case 'SENTINELX_LOGIN':
      // Content script detected a successful login
      tabSessions[tabId] = {
        identityId: msg.identityId,
        gatewayUrl: settings.gatewayUrl,
        riskScore: 0,
        tier: 'allow',
        host: sender.tab?.url ? new URL(sender.tab.url).hostname : 'unknown',
      };
      currentIdentityId = msg.identityId;
      connectSSE(msg.identityId);
      sendResponse({ ok: true });
      break;

    case 'SENTINELX_LOGOUT':
      delete tabSessions[tabId];
      currentIdentityId = null;
      disconnectSSE();
      sendResponse({ ok: true });
      break;

    case 'GET_STATUS':
      sendResponse({
        enabled: settings.enabled,
        session: tabSessions[tabId] || null,
        gatewayUrl: settings.gatewayUrl,
        connected: sseEventSource?.readyState === 1,
      });
      break;

    case 'GET_SETTINGS':
      sendResponse({ settings });
      break;

    case 'SAVE_SETTINGS':
      chrome.storage.sync.set({ settings: msg.settings }, () => {
        settings = msg.settings;
        reconnectSSE();
        sendResponse({ ok: true });
      });
      return true; // async

    case 'PING_GATEWAY':
      fetch(`${settings.gatewayUrl}/health`, { signal: AbortSignal.timeout(3000) })
        .then(r => sendResponse({ ok: r.ok, status: r.status }))
        .catch(err => sendResponse({ ok: false, error: err.message }));
      return true; // async
  }
});

// ── SSE Connection to gateway ─────────────────────────────────────────────────
function connectSSE(identityId) {
  if (sseEventSource) sseEventSource.close();

  const url = `${settings.gatewayUrl}/api/events/session`;
  try {
    sseEventSource = new EventSource(url, { withCredentials: true });

    sseEventSource.addEventListener('session_terminated', (e) => {
      const data = safeJson(e.data);
      handleSessionTerminated(data, identityId);
    });

    sseEventSource.addEventListener('session_restricted', (e) => {
      const data = safeJson(e.data);
      handleSessionRestricted(data, identityId);
    });

    sseEventSource.addEventListener('mfa_challenge', (e) => {
      const data = safeJson(e.data);
      handleMfaChallenge(data, identityId);
    });

    sseEventSource.onerror = () => {
      // Auto-reconnects — no action needed
    };

    console.log('[SentinelX] SSE connected for identity:', identityId);
  } catch (err) {
    console.warn('[SentinelX] SSE connection failed:', err.message);
  }
}

function disconnectSSE() {
  sseEventSource?.close();
  sseEventSource = null;
}

function reconnectSSE() {
  if (currentIdentityId) connectSSE(currentIdentityId);
}

// ── Security event handlers ───────────────────────────────────────────────────

function handleSessionTerminated(data, identityId) {
  console.warn('[SentinelX] Session terminated for', identityId);

  // Notify all tabs associated with this identity
  broadcastToTabs({ type: 'SESSION_TERMINATED', data }, identityId);

  if (settings.notifyOnRevoke) {
    chrome.notifications.create(`revoke-${Date.now()}`, {
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'SentinelX — Session Terminated',
      message: `Your session was ended due to: ${data?.reason || 'security policy'}. Please sign in again.`,
      priority: 2,
    });
  }

  disconnectSSE();
  currentIdentityId = null;
}

function handleSessionRestricted(data, identityId) {
  console.warn('[SentinelX] Session restricted for', identityId);
  broadcastToTabs({ type: 'SESSION_RESTRICTED', data }, identityId);

  if (settings.notifyOnRestrict) {
    chrome.notifications.create(`restrict-${Date.now()}`, {
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'SentinelX — Security Notice',
      message: data?.message || 'Unusual activity detected on your account.',
      priority: 1,
    });
  }
}

function handleMfaChallenge(data, identityId) {
  console.warn('[SentinelX] MFA challenge for', identityId);
  broadcastToTabs({ type: 'MFA_CHALLENGE', data }, identityId);

  if (settings.notifyOnStepUp) {
    chrome.notifications.create(`mfa-${Date.now()}`, {
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'SentinelX — Verify Your Identity',
      message: 'Unusual activity detected. Please complete the security check on your portal.',
      priority: 2,
    });
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function broadcastToTabs(message, identityId) {
  for (const [tabId, session] of Object.entries(tabSessions)) {
    if (!identityId || session.identityId === identityId) {
      chrome.tabs.sendMessage(Number(tabId), message).catch(() => {});
    }
  }
}

function safeJson(str) {
  try { return JSON.parse(str); } catch { return {}; }
}

// Update badge when tab changes
chrome.tabs.onActivated.addListener(({ tabId }) => {
  const session = tabSessions[tabId];
  if (session) {
    const tier = session.tier || 'allow';
    const color = tier === 'revoke' ? '#ef4444'
      : tier === 'restrict' ? '#f59e0b'
      : tier === 'step_up'  ? '#6366f1'
      : '#22c55e';
    chrome.action.setBadgeBackgroundColor({ color, tabId });
    chrome.action.setBadgeText({ text: '🛡', tabId });
  } else {
    chrome.action.setBadgeText({ text: '', tabId });
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  delete tabSessions[tabId];
});
