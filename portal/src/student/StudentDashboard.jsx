import { useState, useEffect } from 'react';
import { useAuth } from '../auth/AuthContext';
import { student as studentApi, sentinelx as sxApi } from '../api/client';
import RiskGauge from '../components/RiskGauge';
import { TrendingUp, TrendingDown, Minus, Activity, Globe, Monitor, Zap } from 'lucide-react';

function TrendIcon({ trend }) {
  if (trend === 'rising') return <TrendingUp size={16} style={{ color: 'var(--risk-critical)' }} />;
  if (trend === 'falling') return <TrendingDown size={16} style={{ color: 'var(--risk-safe)' }} />;
  return <Minus size={16} style={{ color: 'var(--text-secondary)' }} />;
}

function tierLabel(tier) {
  const map = { allow: '🟢 ALLOW', step_up: '🟡 STEP-UP', restrict: '🟠 RESTRICT', revoke: '🔴 REVOKE' };
  return map[tier] || tier?.toUpperCase();
}

export default function StudentDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => {
      studentApi.overview()
        .then(setData)
        .catch(console.error)
        .finally(() => setLoading(false));
    };

    load();

    // Auto-refresh on custom simulation event or timer
    const handleUpdate = () => load();
    window.addEventListener('sentinelx-risk-updated', handleUpdate);

    const iv = setInterval(load, 5000);
    return () => {
      clearInterval(iv);
      window.removeEventListener('sentinelx-risk-updated', handleUpdate);
    };
  }, []);

  if (loading) return (
    <div className="loading-center" style={{ height: '100%' }}>
      <div className="loading-spinner" />
    </div>
  );

  const risk = data?.risk_score ?? 0;
  const tier = data?.tier ?? 'allow';

  return (
    <>
      {/* Topbar */}
      <div className="topbar">
        <div>
          <div className="topbar-title">My Security Dashboard</div>
          <div className="topbar-subtitle">{user?.name || user?.identity_id} · {user?.network_tag || 'Student'}</div>
        </div>
        <div className="topbar-right">
          <div className={`status-pill ${risk < 30 ? 'online' : risk < 60 ? 'warning' : 'critical'}`}>
            <div className={`status-dot ${risk < 30 ? 'online' : risk < 60 ? 'warning' : 'critical'}`} />
            {risk < 30 ? 'Low Risk' : risk < 60 ? 'Moderate Risk' : 'High Risk'}
          </div>
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {/* Top row: gauge + quick stats */}
        <div className="flex gap-16 mb-24" style={{ alignItems: 'stretch' }}>
          {/* Risk Gauge Card */}
          <div className="card" style={{ minWidth: 280, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
            <div className="card-title" style={{ alignSelf: 'flex-start' }}>Your Risk Score</div>
            <RiskGauge score={risk} size={160} />
            <div className={`tier-badge ${tier}`}>
              <div className="tier-dot" />
              {tier.replace('_', '-').toUpperCase()}
            </div>
            {data?.trend && (
              <div className="flex items-center gap-8" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                <TrendIcon trend={data.trend} />
                {data.trend === 'stable' ? 'Risk is stable' : `Risk trending ${data.trend}`}
              </div>
            )}
          </div>

          {/* Quick stats grid */}
          <div style={{ flex: 1, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
            <div className={`stat-card ${data?.alert_count > 0 ? 'warning' : 'safe'}`}>
              <div className="stat-icon"><Zap size={22} color={data?.alert_count > 0 ? 'var(--risk-warning)' : 'var(--risk-safe)'} /></div>
              <div className="stat-value">{data?.alert_count ?? 0}</div>
              <div className="stat-label">Security Alerts</div>
              <div className={`stat-delta ${data?.alert_count > 0 ? 'up' : 'neutral'}`}>
                {data?.alert_count > 0 ? '⚠ Requires attention' : '✓ No active alerts'}
              </div>
            </div>

            <div className="stat-card brand">
              <div className="stat-icon"><Activity size={22} color="var(--brand-primary)" /></div>
              <div className="stat-value">{data?.total_requests ?? 0}</div>
              <div className="stat-label">Total API Requests</div>
              <div className="stat-delta neutral">Across all sessions</div>
            </div>

            <div className="stat-card safe">
              <div className="stat-icon"><Globe size={22} color="var(--risk-safe)" /></div>
              <div className="stat-value" style={{ fontSize: 18 }}>{data?.primary_geo ?? '—'}</div>
              <div className="stat-label">Primary Location</div>
              <div className="stat-delta neutral">Your usual geo</div>
            </div>

            <div className="stat-card brand">
              <div className="stat-icon"><Monitor size={22} color="var(--brand-accent)" /></div>
              <div className="stat-value" style={{ fontSize: 14 }}>{data?.unique_endpoints ?? 0}</div>
              <div className="stat-label">Endpoints Accessed</div>
              <div className="stat-delta neutral">Unique API paths</div>
            </div>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Recent Activity</span>
            <span className="card-subtitle">Last {data?.recent_decisions?.length ?? 0} requests</span>
          </div>
          {!data?.recent_decisions?.length ? (
            <div className="empty-state">
              <div className="empty-state-icon">📭</div>
              <div className="empty-state-text">No activity yet. Make some API requests to see your history.</div>
            </div>
          ) : (
            <div className="scroll-x">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Endpoint</th>
                    <th>Risk Score</th>
                    <th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_decisions.map((d, i) => (
                    <tr key={i}>
                      <td className="mono" style={{ fontSize: 11 }}>
                        {d.timestamp ? new Date(d.timestamp).toLocaleTimeString() : '—'}
                      </td>
                      <td className="mono">{d.endpoint || '—'}</td>
                      <td>
                        <span style={{ fontWeight: 700, color: d.risk_score >= 60 ? 'var(--risk-critical)' : d.risk_score >= 30 ? 'var(--risk-warning)' : 'var(--risk-safe)' }}>
                          {Math.round(d.risk_score ?? 0)}
                        </span>
                        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>/100</span>
                      </td>
                      <td><span className={`tier-badge ${d.tier}`}><div className="tier-dot" />{d.tier?.replace('_', '-').toUpperCase()}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Security Health Tips */}
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title" style={{ marginBottom: 16 }}>🛡️ Security Health</div>
          <div className="flex gap-12" style={{ flexWrap: 'wrap' }}>
            {[
              { icon: '✅', text: 'Always access APIs from your registered network', ok: true },
              { icon: '⚠️', text: 'Avoid accessing payment or admin endpoints', ok: risk < 30 },
              { icon: '🔒', text: 'Don\'t share your API tokens or credentials', ok: true },
              { icon: '📍', text: 'Only connect from known locations (India)', ok: (data?.primary_geo || '').includes('IN') },
            ].map((tip, i) => (
              <div key={i} style={{
                flex: '1 1 200px',
                background: tip.ok ? 'rgba(16,185,129,0.06)' : 'rgba(245,158,11,0.06)',
                border: `1px solid ${tip.ok ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.2)'}`,
                borderRadius: 'var(--radius-md)',
                padding: '12px 14px',
                fontSize: 12,
                color: 'var(--text-secondary)',
              }}>
                <span style={{ marginRight: 8 }}>{tip.icon}</span>{tip.text}
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
