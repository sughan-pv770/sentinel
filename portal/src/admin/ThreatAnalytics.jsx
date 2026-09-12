import { useState, useEffect } from 'react';
import { admin as adminApi } from '../api/client';

export default function ThreatAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    adminApi.analytics().then(setData).catch(console.error).finally(() => setLoading(false));
  }, []);

  if (loading) return <><div className="topbar"><div className="topbar-title">Threat Analytics</div></div><div className="loading-center" style={{height:'80%'}}><div className="loading-spinner"/></div></>;

  const identities = data?.identity_risks || [];
  const endpoints = data?.top_endpoints || [];
  const tierBreakdown = data?.tier_breakdown || {};

  const maxEpCount = endpoints.length ? endpoints[0][1] : 1;

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Threat Analytics</div>
          <div className="topbar-subtitle">Risk distribution, endpoint heatmap, and identity analysis</div>
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {/* Tier Breakdown */}
        <div className="card mb-16">
          <div className="card-title" style={{ marginBottom: 16 }}>📊 Alert Tier Breakdown</div>
          <div className="flex gap-24" style={{ flexWrap: 'wrap' }}>
            {[
              { tier: 'step_up', label: 'Step-Up', color: 'var(--risk-warning)', icon: '⚠️' },
              { tier: 'restrict', label: 'Restrict', color: 'var(--risk-danger)', icon: '🚫' },
              { tier: 'revoke', label: 'Revoke', color: 'var(--risk-critical)', icon: '🔴' },
            ].map(t => (
              <div key={t.tier} style={{ textAlign: 'center', flex: '1 1 120px' }}>
                <div style={{ fontSize: 32, marginBottom: 4 }}>{t.icon}</div>
                <div style={{ fontSize: 36, fontWeight: 800, color: t.color }}>{tierBreakdown[t.tier] ?? 0}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{t.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Top endpoints bar chart */}
        <div className="card mb-16">
          <div className="card-header">
            <span className="card-title">🔥 Top Alert Endpoints</span>
            <span className="card-subtitle">Most frequently flagged API paths</span>
          </div>
          {!endpoints.length ? (
            <div className="empty-state"><div className="empty-state-text">No endpoint data yet</div></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {endpoints.map(([ep, count]) => (
                <div key={ep} className="flex items-center gap-12">
                  <span className="mono" style={{ width: 180, fontSize: 12, flexShrink: 0, textAlign: 'right', color: 'var(--text-secondary)' }}>{ep}</span>
                  <div className="feature-bar-track" style={{ flex: 1 }}>
                    <div className="feature-bar-fill" style={{ width: `${(count / maxEpCount) * 100}%`, background: 'linear-gradient(90deg, var(--brand-primary), var(--risk-critical))' }} />
                  </div>
                  <span className="mono" style={{ width: 40, fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', textAlign: 'right' }}>{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Identity risk table */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">🎯 Identity Risk Matrix</span>
            <span className="card-subtitle">All identities ranked by current risk score</span>
          </div>
          <div className="scroll-x">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Identity</th>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Current Risk</th>
                  <th>Avg Risk</th>
                  <th>Tier</th>
                  <th>Requests</th>
                </tr>
              </thead>
              <tbody>
                {identities.map((id, i) => (
                  <tr key={id.identity_id}>
                    <td style={{ fontWeight: 700, color: 'var(--text-muted)' }}>{i + 1}</td>
                    <td className="mono" style={{ fontWeight: 600 }}>{id.identity_id}</td>
                    <td>{id.name}</td>
                    <td>
                      <span className={`tier-badge ${id.role === 'admin' ? 'revoke' : id.role === 'manager' ? 'step_up' : 'allow'}`} style={{ fontSize: 10 }}>
                        {id.role}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontWeight: 800, color: id.current_risk >= 60 ? 'var(--risk-critical)' : id.current_risk >= 30 ? 'var(--risk-warning)' : 'var(--risk-safe)' }}>
                        {Math.round(id.current_risk)}
                      </span>/100
                    </td>
                    <td>{id.avg_risk}</td>
                    <td><span className={`tier-badge ${id.tier}`}><div className="tier-dot" />{id.tier?.replace('_','-').toUpperCase()}</span></td>
                    <td>{id.request_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
