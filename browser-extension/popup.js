// popup.js — SentinelX Extension Popup Logic

const TIER_COLORS = {
  allow:     { dot: '#22c55e', pill: 'rgba(34,197,94,0.06)',    border: 'rgba(34,197,94,0.3)',    label: '#4ade80',  text: 'Monitoring Active',    sub: 'Your session is being protected' },
  step_up:   { dot: '#6366f1', pill: 'rgba(99,102,241,0.06)',   border: 'rgba(99,102,241,0.3)',   label: '#a5b4fc',  text: 'Verification Required', sub: 'Complete the MFA check in the portal' },
  restrict:  { dot: '#f59e0b', pill: 'rgba(245,158,11,0.06)',   border: 'rgba(245,158,11,0.3)',   label: '#fbbf24',  text: 'Access Restricted',     sub: 'Unusual activity detected on this session' },
  revoke:    { dot: '#ef4444', pill: 'rgba(239,68,68,0.06)',    border: 'rgba(239,68,68,0.3)',    label: '#f87171',  text: 'Session Terminated',    sub: 'This session was ended by security policy' },
  inactive:  { dot: '#64748b', pill: 'rgba(100,116,139,0.06)',  border: 'rgba(100,116,139,0.2)', label: '#94a3b8',  text: 'Not Active',             sub: 'No protected session on this tab' },
};

const RISK_GRADIENT = (score) => {
  if (score < 30) return 'linear-gradient(90deg,#22c55e,#4ade80)';
  if (score < 60) return 'linear-gradient(90deg,#f59e0b,#fbbf24)';
  return 'linear-gradient(90deg,#ef4444,#f87171)';
};

async function init() {
  // Get current tab status from background
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const statusRes = await new Promise(res =>
    chrome.runtime.sendMessage({ type: 'GET_STATUS' }, res)
  );

  const session  = statusRes?.session;
  const settings = statusRes?.settings;
  const gatewayUrl = settings?.gatewayUrl || statusRes?.gatewayUrl || 'http://localhost:8080';

  // Update gateway link
  document.getElementById('gateway-link').href = `${gatewayUrl}/portal/admin`;

  // Ping gateway for connection indicator
  chrome.runtime.sendMessage({ type: 'PING_GATEWAY' }, (res) => {
    const connected = res?.ok;
    const dot  = document.getElementById('conn-indicator');
    const text = document.getElementById('conn-text');
    dot.style.background  = connected ? '#22c55e' : '#ef4444';
    text.textContent = connected ? 'Gateway connected' : 'Gateway offline';
  });

  if (session) {
    // Show session card
    document.getElementById('no-session').style.display = 'none';
    document.getElementById('session-card').style.display = 'block';

    document.getElementById('sx-identity').textContent = session.identityId || '—';
    document.getElementById('sx-host').textContent     = session.host || new URL(tab?.url || 'http://unknown').hostname;
    const score = Math.round(session.riskScore || 0);
    document.getElementById('sx-risk').textContent     = `${score}/100`;
    document.getElementById('sx-risk-bar').style.width      = `${score}%`;
    document.getElementById('sx-risk-bar').style.background = RISK_GRADIENT(score);

    applyTierStyle(session.tier || 'allow');
  } else {
    document.getElementById('no-session').style.display = 'block';
    document.getElementById('session-card').style.display = 'none';
    applyTierStyle('inactive');
  }

  // Buttons
  document.getElementById('open-portal').addEventListener('click', () => {
    chrome.tabs.create({ url: gatewayUrl + '/portal/' });
    window.close();
  });
  document.getElementById('open-settings').addEventListener('click', () => {
    chrome.runtime.openOptionsPage();
    window.close();
  });
}

function applyTierStyle(tier) {
  const s = TIER_COLORS[tier] || TIER_COLORS.inactive;
  const pill  = document.getElementById('status-pill');
  const dot   = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  const sub   = document.getElementById('status-sub');

  pill.style.background  = s.pill;
  pill.style.borderColor = s.border;
  dot.style.background   = s.dot;
  label.style.color      = s.label;
  label.textContent      = s.text;
  sub.textContent        = s.sub;
}

init().catch(console.error);
