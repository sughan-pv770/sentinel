import { useState, useEffect } from 'react';
import { admin as adminApi, sentinelx as sxApi } from '../api/client';
import { ShieldAlert, Users, Activity, AlertTriangle, TrendingUp, Cpu } from 'lucide-react';
import RiskGauge from '../components/RiskGauge';

function StatCard({ icon: Icon, value, label, color, delta, deltaDir }) {
  return (
    <div className={`stat-card ${deltaDir === 'up' ? 'danger' : deltaDir === 'down' ? 'safe' : 'brand'}`}>
      <div className="stat-icon"><Icon size={22} color={color} /></div>
      <div className="stat-value" style={{ color }}>{value}</div>
      <div className="stat-label">{label}</div>
      {delta && <div className={`stat-delta ${deltaDir}`}>{delta}</div>}
    </div>
  );
}

function TierBadge({ tier }) {
  return <span className={`tier-badge ${tier}`}><div className="tier-dot" />{tier?.replace('_', '-').toUpperCase()}</span>;
}

export default function CommandCenter() {
  const [overview, setOverview] = useState(null);
  const [feed, setFeed]       = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = () => Promise.all([
    adminApi.overview(),
    adminApi.liveFeed(30),
    adminApi.analytics(),
  ]).then(([ov, f, an]) => {
    setOverview(ov);
    setFeed(f);
    setAnalytics(an);
  }).catch(console.error).finally(() => setLoading(false));

  useEffect(() => {
    fetchAll();
    const iv = setInterval(fetchAll, 8000);
    return () => clearInterval(iv);
  }, []);

  if (loading) return <div className="loading-center" style={{ height: '100%' }}><div className="loading-spinner" /></div>;

  const topIdentity = analytics?.identity_risks?.[0];
  const alertsByTier = overview?.alerts_by_tier || {};
  const recentAlerts = (feed?.alerts || []).slice(0, 8);

  return (
    <>
      {/* Topbar */}
      <div className="topbar">
        <div>
          <div className="topbar-title">Security Command Center</div>
          <div className="topbar-subtitle">Real-time threat overview · Auto-refreshing every 8s</div>
        </div>
        <div className="topbar-right">
          <div className={`status-pill ${overview?.system_health === 'HEALTHY' ? 'online' : overview?.system_health === 'ELEVATED' ? 'warning' : 'critical'}`}>
            <div className={`status-dot ${overview?.system_health === 'HEALTHY' ? 'online' : 'warning'}`} />
            System: {overview?.system_health || 'UNKNOWN'}
          </div>
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {/* KPI Row */}
        <div className="grid-4 mb-24">
          <StatCard
            icon={Users}
            value={overview?.users_total ?? 0}
            label="Registered Identities"
            color="var(--brand-primary)"
            delta={`${overview?.high_risk_identities ?? 0} high-risk`}
            deltaDir={overview?.high_risk_identities > 0 ? 'up' : 'neutral'}
          />
          <StatCard
            icon={AlertTriangle}
            value={overview?.incidents?.open_incidents ?? 0}
            label="Open Incidents"
            color={overview?.incidents?.open_incidents > 0 ? 'var(--risk-critical)' : 'var(--risk-safe)'}
            delta={`${overview?.incidents?.critical_incidents ?? 0} critical`}
            deltaDir={overview?.incidents?.critical_incidents > 0 ? 'up' : 'neutral'}
          />
          <StatCard
            icon={Activity}
            value={overview?.avg_risk_score ?? 0}
            label="Avg Risk Score"
            color={overview?.avg_risk_score >= 60 ? 'var(--risk-danger)' : overview?.avg_risk_score >= 30 ? 'var(--risk-warning)' : 'var(--risk-safe)'}
            delta="/100 composite"
            deltaDir="neutral"
          />
          <StatCard
            icon={ShieldAlert}
            value={overview?.alerts_total ?? 0}
            label="Total Alerts"
            color="var(--risk-warning)"
            delta={`${alertsByTier.revoke ?? 0} revoked sessions`}
            deltaDir={alertsByTier.revoke > 0 ? 'up' : 'neutral'}
          />
        </div>

        {/* Main grid */}
        <div className="grid-2 mb-16" style={{ gridTemplateColumns: '2fr 1fr' }}>
          {/* Recent alerts */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">⚡ Live Alert Feed</span>
              <span className="card-subtitle">{feed?.alerts?.length ?? 0} total</span>
            </div>
            {!recentAlerts.length ? (
              <div className="empty-state">
                <div className="empty-state-icon">🟢</div>
                <div className="empty-state-text">No alerts — system operating normally</div>
              </div>
            ) : (
              recentAlerts.map((alert, i) => {
                const reason = alert.reasons?.[0];
                const msg = typeof reason === 'string' ? reason : reason?.message || 'Anomaly detected';
                return (
                  <div key={i} className="alert-item">
                    <div className="alert-icon">
                      {alert.tier === 'revoke' ? '🔴' : alert.tier === 'restrict' ? '🟠' : '⚠️'}
                    </div>
                    <div className="alert-body">
                      <div className="alert-headline">
                        <span className="mono">{alert.identity_id}</span> → <span className="mono">{alert.endpoint}</span>
                      </div>
                      <div className="alert-detail">{msg}</div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                      <TierBadge tier={alert.tier} />
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {Math.round(alert.risk_score ?? 0)}/100
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Top risk identities */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">🎯 Top Risk Identities</span>
            </div>
            {!(analytics?.identity_risks?.length) ? (
              <div className="empty-state"><div className="empty-state-text">No data</div></div>
            ) : (
              analytics.identity_risks.slice(0, 5).map((id, i) => (
                <div key={i} className="flex items-center gap-12" style={{ padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--bg-hover)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, flexShrink: 0 }}>
                    {i + 1}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="mono truncate" style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {id.identity_id}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{id.name} · {id.role}</div>
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    <div style={{ fontWeight: 800, color: id.current_risk >= 60 ? 'var(--risk-critical)' : id.current_risk >= 30 ? 'var(--risk-warning)' : 'var(--risk-safe)' }}>
                      {Math.round(id.current_risk)}
                    </div>
                    <TierBadge tier={id.tier} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* User role breakdown */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>👥 User Distribution</div>
          <div className="flex gap-24">
            {Object.entries(overview?.users_by_role || {}).map(([role, count]) => (
              <div key={role} style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-primary)' }}>{count}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{role}s</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
