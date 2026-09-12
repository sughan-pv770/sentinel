import { useState, useEffect } from 'react';
import { sentinelx as sxApi } from '../api/client';

export default function AlertFeed() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  const fetch = () => {
    sxApi.alerts(200).then(d => setAlerts(Array.isArray(d) ? d : [])).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => { fetch(); const iv = setInterval(fetch, 5000); return () => clearInterval(iv); }, []);

  const filtered = filter === 'all' ? alerts : alerts.filter(a => a.tier === filter);

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Alert Feed</div>
          <div className="topbar-subtitle">{alerts.length} total alerts · auto-refreshing</div>
        </div>
        <div className="topbar-right">
          {['all', 'step_up', 'restrict', 'revoke'].map(f => (
            <button key={f} className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setFilter(f)} style={{ textTransform: 'capitalize' }}>
              {f === 'all' ? 'All' : f.replace('_', '-')}
            </button>
          ))}
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {loading ? (
          <div className="loading-center"><div className="loading-spinner" /></div>
        ) : !filtered.length ? (
          <div className="empty-state" style={{ paddingTop: 60 }}>
            <div className="empty-state-icon">🟢</div>
            <div className="empty-state-text">No alerts to show{filter !== 'all' ? ` for "${filter}" filter` : ''}</div>
          </div>
        ) : (
          <div className="card">
            {filtered.map((alert, i) => {
              const reason = alert.reasons?.[0];
              const msg = typeof reason === 'string' ? reason : reason?.message || 'Anomaly detected';
              return (
                <div key={i} className="alert-item animate-slide-in" style={{ animationDelay: `${Math.min(i * 0.03, 0.5)}s` }}>
                  <div className="alert-icon" style={{ fontSize: 20 }}>
                    {alert.tier === 'revoke' ? '🔴' : alert.tier === 'restrict' ? '🟠' : '⚠️'}
                  </div>
                  <div className="alert-body">
                    <div className="alert-headline">
                      <span className="mono" style={{ fontWeight: 700 }}>{alert.identity_id}</span>
                      <span style={{ margin: '0 6px', color: 'var(--text-muted)' }}>→</span>
                      <span className="mono">{alert.endpoint}</span>
                    </div>
                    <div className="alert-detail">{msg}</div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                    <span className={`tier-badge ${alert.tier}`}>
                      <div className="tier-dot" />{alert.tier?.replace('_', '-').toUpperCase()}
                    </span>
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      Risk: {Math.round(alert.risk_score ?? 0)}/100
                    </span>
                    {alert.timestamp && (
                      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                        {new Date(alert.timestamp).toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
