import { useState, useEffect } from 'react';
import { student as studentApi } from '../api/client';

const SIGNALS = [
  { key: 'request_frequency_per_min', label: 'Request Frequency', max: 30, unit: 'req/min', normal: '1-10' },
  { key: 'endpoint_novelty',          label: 'Endpoint Novelty',  max: 1,  unit: '',        normal: '0.0' },
  { key: 'geo_change',                label: 'Geo Change',        max: 1,  unit: '',        normal: '0.0' },
  { key: 'device_change',             label: 'Device Change',     max: 1,  unit: '',        normal: '0.0' },
  { key: 'time_of_day_deviation',     label: 'Time Deviation',    max: 1,  unit: '',        normal: '< 0.2' },
  { key: 'payload_size_zscore',       label: 'Payload Z-Score',   max: 5,  unit: '',        normal: '< 1.5' },
  { key: 'token_age_seconds',         label: 'Token Age',         max: 3600, unit: 's',    normal: '300-3600' },
];

function signalColor(ratio) {
  if (ratio >= 0.75) return 'var(--risk-critical)';
  if (ratio >= 0.5) return 'var(--risk-warning)';
  if (ratio >= 0.25) return 'var(--risk-danger)';
  return 'var(--risk-safe)';
}

export default function MyRiskProfile() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => {
      studentApi.riskProfile().then(setData).catch(console.error).finally(() => setLoading(false));
    };
    load();

    window.addEventListener('sentinelx-risk-updated', load);
    return () => window.removeEventListener('sentinelx-risk-updated', load);
  }, []);

  const features = data?.last_features || {};
  const profile = data?.profile || {};

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Risk Profile</div>
          <div className="topbar-subtitle">Your behavioral fingerprint — 7-signal baseline</div>
        </div>
        <div className="topbar-right">
          <div className={`status-pill ${data?.confidence === 'HIGH' ? 'online' : 'warning'}`}>
            <div className={`status-dot ${data?.confidence === 'HIGH' ? 'online' : 'warning'}`} />
            Confidence: {data?.confidence || 'LOW'}
          </div>
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {loading ? (
          <div className="loading-center"><div className="loading-spinner" /></div>
        ) : (
          <>
            {/* 7-Signal Feature Bars */}
            <div className="card mb-16">
              <div className="card-header">
                <span className="card-title">🧠 7-Signal Behavioral Feature Vector</span>
                <span className="card-subtitle">From last request · Higher = more anomalous</span>
              </div>

              {Object.keys(features).length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon">📊</div>
                  <div className="empty-state-text">No feature data yet. Fire a request via the API Sandbox to populate this.</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {SIGNALS.map(sig => {
                    const val = features[sig.key] ?? 0;
                    const ratio = Math.min(val / sig.max, 1);
                    const color = signalColor(ratio);
                    return (
                      <div key={sig.key}>
                        <div className="flex justify-between items-center" style={{ marginBottom: 5 }}>
                          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                            {sig.label}
                          </span>
                          <div className="flex items-center gap-8">
                            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                              Normal: {sig.normal}
                            </span>
                            <span className="mono" style={{ fontSize: 13, fontWeight: 700, color, minWidth: 50, textAlign: 'right' }}>
                              {typeof val === 'number' ? val.toFixed(2) : val}{sig.unit}
                            </span>
                          </div>
                        </div>
                        <div className="feature-bar-track">
                          <div
                            className="feature-bar-fill"
                            style={{ width: `${ratio * 100}%`, background: color }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Behavioral Summary */}
            <div className="grid-2 mb-16">
              <div className="card">
                <div className="card-title" style={{ marginBottom: 14 }}>📍 Location History</div>
                {Object.keys(profile.geos || {}).length === 0 ? (
                  <div className="empty-state" style={{ padding: 24 }}>
                    <div className="empty-state-text">No location data</div>
                  </div>
                ) : (
                  Object.entries(profile.geos || {}).map(([geo, count]) => (
                    <div key={geo} className="flex justify-between items-center" style={{ padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                      <span className="mono" style={{ fontSize: 13 }}>{geo}</span>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{count} requests</span>
                    </div>
                  ))
                )}
              </div>

              <div className="card">
                <div className="card-title" style={{ marginBottom: 14 }}>💻 Device History</div>
                {Object.keys(profile.devices || {}).length === 0 ? (
                  <div className="empty-state" style={{ padding: 24 }}>
                    <div className="empty-state-text">No device data</div>
                  </div>
                ) : (
                  Object.entries(profile.devices || {}).map(([device, count]) => (
                    <div key={device} className="flex justify-between items-center" style={{ padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                      <span className="mono" style={{ fontSize: 12 }}>{device}</span>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{count} requests</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Endpoint History */}
            <div className="card">
              <div className="card-title" style={{ marginBottom: 14 }}>🔗 Endpoint Access History</div>
              {Object.keys(profile.endpoints || {}).length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-text">No endpoint data yet</div>
                </div>
              ) : (
                <div className="scroll-x">
                  <table className="data-table">
                    <thead><tr><th>Endpoint</th><th>Request Count</th><th>Frequency</th></tr></thead>
                    <tbody>
                      {Object.entries(profile.endpoints || {})
                        .sort((a, b) => b[1] - a[1])
                        .map(([ep, count]) => {
                          const total = profile.total_requests || 1;
                          const pct = Math.round((count / total) * 100);
                          return (
                            <tr key={ep}>
                              <td className="mono">{ep}</td>
                              <td><span style={{ fontWeight: 700 }}>{count}</span></td>
                              <td>
                                <div className="flex items-center gap-8">
                                  <div className="feature-bar-track" style={{ width: 80 }}>
                                    <div className="feature-bar-fill" style={{ width: `${pct}%`, background: 'var(--brand-primary)' }} />
                                  </div>
                                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{pct}%</span>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
