import { useState, useEffect } from 'react';
import { incidents as incApi } from '../api/client';

const SEVERITY_COLORS = {
  CRITICAL: 'var(--risk-critical)', HIGH: 'var(--risk-danger)',
  MEDIUM: 'var(--risk-warning)', LOW: 'var(--risk-safe)',
};

export default function IncidentManager() {
  const [incidents, setIncidents] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [selected, setSelected] = useState(null);

  const fetchIncidents = () => {
    incApi.list(100, filter === 'all' ? null : filter)
      .then(d => { setIncidents(d.incidents || []); setStats(d.stats || {}); })
      .catch(console.error).finally(() => setLoading(false));
  };

  useEffect(() => { fetchIncidents(); }, [filter]);

  const handleStatusUpdate = async (id, newStatus) => {
    try {
      await incApi.updateStatus(id, newStatus, `Status changed to ${newStatus} via Portal`);
      fetchIncidents();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Incident Management</div>
          <div className="topbar-subtitle">
            {stats.open_incidents ?? 0} open · {stats.critical_incidents ?? 0} critical · {stats.total_incidents ?? 0} total
          </div>
        </div>
        <div className="topbar-right">
          {['all', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(f => (
            <button key={f} className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setFilter(f)}>
              {f === 'all' ? 'All' : f}
            </button>
          ))}
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {loading ? (
          <div className="loading-center"><div className="loading-spinner" /></div>
        ) : !incidents.length ? (
          <div className="empty-state" style={{ paddingTop: 60 }}>
            <div className="empty-state-icon">✅</div>
            <div className="empty-state-text">No incidents{filter !== 'all' ? ` with severity "${filter}"` : ''}</div>
          </div>
        ) : (
          <div className="grid-2" style={{ gridTemplateColumns: '1fr 1.2fr' }}>
            {/* List */}
            <div className="card scroll-y" style={{ maxHeight: 'calc(100vh - 160px)' }}>
              <div className="card-title" style={{ marginBottom: 14 }}>Incidents</div>
              {incidents.map(inc => (
                <div
                  key={inc.incident_id}
                  className={`incident-card ${inc.severity} ${selected?.incident_id === inc.incident_id ? 'active' : ''}`}
                  onClick={() => setSelected(inc)}
                  style={selected?.incident_id === inc.incident_id ? { borderColor: 'var(--brand-primary)', background: 'rgba(99,102,241,0.05)' } : {}}
                >
                  <div className="flex justify-between items-center" style={{ marginBottom: 6 }}>
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{inc.incident_id?.slice(0, 8)}</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: SEVERITY_COLORS[inc.severity] }}>{inc.severity}</span>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{inc.title}</div>
                  <div className="flex justify-between items-center">
                    <span className="mono" style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{inc.identity_id}</span>
                    <span className={`tier-badge ${inc.status === 'OPEN' ? 'revoke' : inc.status === 'MITIGATED' ? 'step_up' : inc.status === 'RESOLVED' ? 'allow' : 'restrict'}`} style={{ fontSize: 9 }}>
                      {inc.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Detail panel */}
            <div className="card">
              {!selected ? (
                <div className="empty-state" style={{ paddingTop: 80 }}>
                  <div className="empty-state-icon">🔍</div>
                  <div className="empty-state-text">Select an incident to view details</div>
                </div>
              ) : (
                <div className="animate-slide-in">
                  <div className="flex justify-between items-center mb-16">
                    <div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{selected.title}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>{selected.incident_id}</div>
                    </div>
                    <span style={{ fontSize: 14, fontWeight: 800, color: SEVERITY_COLORS[selected.severity] }}>
                      {selected.severity}
                    </span>
                  </div>

                  {/* Key fields */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
                    {[
                      { label: 'Identity', value: selected.identity_id },
                      { label: 'Endpoint', value: selected.endpoint },
                      { label: 'Status', value: selected.status },
                      { label: 'Trigger Score', value: `${Math.round(selected.trigger_score ?? 0)}/100` },
                      { label: 'Created', value: selected.created_at ? new Date(selected.created_at).toLocaleString() : '—' },
                      { label: 'Updated', value: selected.updated_at ? new Date(selected.updated_at).toLocaleString() : '—' },
                    ].map(f => (
                      <div key={f.label} style={{ padding: '8px 10px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)' }}>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 2 }}>{f.label}</div>
                        <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{f.value}</div>
                      </div>
                    ))}
                  </div>

                  {/* Status controls */}
                  <div style={{ marginBottom: 20 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Update Status:</div>
                    <div className="flex gap-8">
                      {['INVESTIGATING', 'MITIGATED', 'RESOLVED'].map(s => (
                        <button
                          key={s}
                          className={`btn btn-sm ${selected.status === s ? 'btn-primary' : 'btn-secondary'}`}
                          onClick={() => handleStatusUpdate(selected.incident_id, s)}
                          disabled={selected.status === s}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Timeline */}
                  {selected.timeline?.length > 0 && (
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>Timeline</div>
                      {selected.timeline.map((event, i) => (
                        <div key={i} className="flex gap-12" style={{ paddingBottom: 12, marginBottom: 12, borderBottom: '1px solid var(--border-subtle)' }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--brand-primary)', marginTop: 5, flexShrink: 0 }} />
                          <div>
                            <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>{event.note || event.action}</div>
                            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                              {event.timestamp ? new Date(event.timestamp).toLocaleString() : '—'}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
