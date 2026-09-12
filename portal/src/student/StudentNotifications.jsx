import { useState, useEffect } from 'react';
import { useAuth } from '../auth/AuthContext';
import { sentinelx as sxApi } from '../api/client';

function alertIcon(tier) {
  return { allow: '✅', step_up: '⚠️', restrict: '🚫', revoke: '🔴' }[tier] || '🔔';
}

export default function StudentNotifications() {
  const { user } = useAuth();
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAlerts = () => {
    sxApi.alerts(200)
      .then(data => {
        const myAlerts = (Array.isArray(data) ? data : []).filter(
          a => a.identity_id === user?.identity_id
        );
        setAlerts(myAlerts);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAlerts();
    const iv = setInterval(fetchAlerts, 8000);
    return () => clearInterval(iv);
  }, [user]);

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Notifications</div>
          <div className="topbar-subtitle">Security alerts for your account</div>
        </div>
        <div className="topbar-right">
          {alerts.length > 0 && (
            <div className="status-pill critical">
              <div className="status-dot critical" />
              {alerts.length} alert{alerts.length !== 1 ? 's' : ''}
            </div>
          )}
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {loading ? (
          <div className="loading-center"><div className="loading-spinner" /></div>
        ) : !alerts.length ? (
          <div className="empty-state" style={{ paddingTop: 80 }}>
            <div className="empty-state-icon">🛡️</div>
            <div className="empty-state-text">
              <strong style={{ color: 'var(--risk-safe)' }}>All clear!</strong><br />
              No security alerts for your account.
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="card-header">
              <span className="card-title">Security Alerts</span>
              <span className="card-subtitle">{alerts.length} total</span>
            </div>
            {alerts.map((alert, i) => {
              const reasons = alert.reasons || [];
              const topReason = typeof reasons[0] === 'string' ? reasons[0] : reasons[0]?.message;
              return (
                <div key={i} className="alert-item animate-slide-in" style={{ animationDelay: `${i * 0.05}s` }}>
                  <div className="alert-icon">{alertIcon(alert.tier)}</div>
                  <div className="alert-body">
                    <div className="alert-headline">
                      {alert.endpoint} — <span className={`tier-badge ${alert.tier}`} style={{ display: 'inline-flex', padding: '2px 8px' }}>{alert.tier?.toUpperCase()}</span>
                    </div>
                    <div className="alert-detail">{topReason || 'Security anomaly detected'}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      Risk Score: <strong style={{ color: 'var(--risk-critical)' }}>{Math.round(alert.risk_score ?? 0)}/100</strong>
                      {alert.timestamp && <> · {new Date(alert.timestamp).toLocaleString()}</>}
                    </div>
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
