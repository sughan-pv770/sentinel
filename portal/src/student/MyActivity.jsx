import { useState, useEffect } from 'react';
import { student as studentApi } from '../api/client';

function tierColor(tier) {
  return { allow: 'var(--risk-safe)', step_up: 'var(--risk-warning)', restrict: 'var(--risk-danger)', revoke: 'var(--risk-critical)' }[tier] || 'var(--text-secondary)';
}

export default function MyActivity() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    studentApi.activity(100).then(setData).catch(console.error).finally(() => setLoading(false));
  }, []);

  const activity = (data?.activity || []).filter(d =>
    filter === 'all' || d.tier === filter
  );

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">My Activity</div>
          <div className="topbar-subtitle">Complete API request history with risk scores</div>
        </div>
        <div className="topbar-right">
          {['all', 'allow', 'step_up', 'restrict', 'revoke'].map(f => (
            <button
              key={f}
              className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilter(f)}
              style={{ textTransform: 'capitalize' }}
            >
              {f.replace('_', '-')}
            </button>
          ))}
        </div>
      </div>

      <div className="page-content animate-fade-in">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Request Log</span>
            <span className="card-subtitle">{activity.length} records</span>
          </div>

          {loading ? (
            <div className="loading-center"><div className="loading-spinner" /></div>
          ) : !activity.length ? (
            <div className="empty-state">
              <div className="empty-state-icon">📭</div>
              <div className="empty-state-text">No activity found for this filter.</div>
            </div>
          ) : (
            <div className="scroll-x">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Timestamp</th>
                    <th>Endpoint</th>
                    <th>ML Score</th>
                    <th>Rule Score</th>
                    <th>Risk Score</th>
                    <th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.map((d, i) => (
                    <tr key={i}>
                      <td className="mono text-muted">{i + 1}</td>
                      <td className="mono" style={{ fontSize: 11 }}>
                        {d.timestamp ? new Date(d.timestamp).toLocaleString() : '—'}
                      </td>
                      <td className="mono">{d.endpoint || '—'}</td>
                      <td><span style={{ color: 'var(--brand-accent)', fontWeight: 600 }}>{Math.round(d.ml_score ?? 0)}</span></td>
                      <td><span style={{ color: 'var(--brand-secondary)', fontWeight: 600 }}>{Math.round(d.rule_score ?? 0)}</span></td>
                      <td>
                        <span style={{ fontWeight: 800, color: tierColor(d.tier) }}>
                          {Math.round(d.risk_score ?? 0)}
                        </span>
                        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>/100</span>
                      </td>
                      <td>
                        <span className={`tier-badge ${d.tier}`}>
                          <div className="tier-dot" />
                          {d.tier?.replace('_', '-').toUpperCase()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
