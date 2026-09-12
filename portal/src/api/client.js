/**
 * SentinelX API Client
 * Thin wrapper around fetch() with base URL handling.
 * All auth is via httpOnly cookie — no tokens in JS.
 */

const BASE = import.meta.env.DEV ? '' : '';

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(err.detail || 'Request failed'), { status: res.status, data: err });
  }
  return res.json();
}

// ─── Auth ────────────────────────────────────────────────────────────────────
export const auth = {
  login: (identity_id, password) =>
    req('/api/auth/login', { method: 'POST', body: JSON.stringify({ identity_id, password }) }),
  logout: () => req('/api/auth/logout', { method: 'POST' }),
  me: () => req('/api/auth/me'),
};

// ─── Student Dashboard ────────────────────────────────────────────────────────
export const student = {
  overview: () => req('/api/dashboard/student/overview'),
  activity: (limit = 50) => req(`/api/dashboard/student/activity?limit=${limit}`),
  riskProfile: () => req('/api/dashboard/student/risk-profile'),
};

// ─── Admin Dashboard ──────────────────────────────────────────────────────────
export const admin = {
  overview: () => req('/api/dashboard/admin/overview'),
  analytics: () => req('/api/dashboard/admin/analytics'),
  incidents: (limit = 50, severity = null) =>
    req(`/api/dashboard/admin/incidents?limit=${limit}${severity ? `&severity=${severity}` : ''}`),
  liveFeed: (limit = 100) => req(`/api/dashboard/admin/live-feed?limit=${limit}`),
};

// ─── SentinelX Control Plane ──────────────────────────────────────────────────
export const sentinelx = {
  stats: () => req('/sentinelx/stats'),
  policy: () => req('/sentinelx/policy'),
  updatePolicy: (data) => req('/sentinelx/policy', { method: 'POST', body: JSON.stringify(data) }),
  risk: (id) => req(`/sentinelx/risk/${id}`),
  alerts: (limit = 50) => req(`/sentinelx/alerts?limit=${limit}`),
  users: () => req('/sentinelx/users'),
  addUser: (data) => req('/sentinelx/users', { method: 'POST', body: JSON.stringify(data) }),
  revoke: (session_id) => req(`/sentinelx/revoke/${session_id}`, { method: 'POST' }),
  simulate: (data) => req('/sentinelx/simulate', { method: 'POST', body: JSON.stringify(data) }),
};

// ─── Incidents ────────────────────────────────────────────────────────────────
export const incidents = {
  list: (limit = 50, severity = null) =>
    req(`/sentinelx/incidents?limit=${limit}${severity ? `&severity=${severity}` : ''}`),
  updateStatus: (id, status, note = '') =>
    req(`/sentinelx/incidents/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, note }),
    }),
};
