import { useState } from 'react';
import { sentinelx as sxApi } from '../api/client';

const SCENARIOS = [
  { name: 'Normal Request', desc: 'Legitimate student accessing GET /users', identity_id: 'u_alex', endpoint: '/users', method: 'GET', geo: 'IN', device: 'Chrome/macOS' },
  { name: 'Impossible Travel', desc: 'Same user suddenly from Russia', identity_id: 'u_alex', endpoint: '/users/2', method: 'GET', geo: 'RU', device: 'Firefox/Linux' },
  { name: 'Admin Probing', desc: 'Student accessing admin-only endpoint', identity_id: 'u_mina', endpoint: '/admin/delete-all', method: 'DELETE', geo: 'IN', device: 'Chrome/macOS' },
  { name: 'Burst Attack', desc: 'Rapid-fire requests (high frequency)', identity_id: 'u_alex', endpoint: '/orders', method: 'POST', geo: 'IN', device: 'Chrome/macOS', burst: true },
  { name: 'Device Switch', desc: 'Known user on unknown device', identity_id: 'u_mina', endpoint: '/orders', method: 'GET', geo: 'IN', device: 'Unknown/Unknown' },
  { name: 'Payment Fraud', desc: 'Student attempting high-value payment', identity_id: 'u_alex', endpoint: '/payments', method: 'POST', geo: 'IN', device: 'Chrome/macOS', payload_size: 50000 },
];

export default function ApiSandbox() {
  const [results, setResults] = useState([]);
  const [running, setRunning] = useState(null);

  const runScenario = async (scenario) => {
    setRunning(scenario.name);
    try {
      const data = await sxApi.simulate({
        identity_id: scenario.identity_id,
        session_id: `session_sandbox_${Date.now()}`,
        endpoint: scenario.endpoint,
        method: scenario.method,
        geo: scenario.geo,
        device: scenario.device,
        payload_size: scenario.payload_size,
        headers: {},
      });
      setResults(prev => [{
        scenario: scenario.name,
        ...data,
        timestamp: new Date().toLocaleTimeString(),
      }, ...prev].slice(0, 20));
    } catch (err) {
      setResults(prev => [{
        scenario: scenario.name,
        error: err.data?.detail || err.message,
        timestamp: new Date().toLocaleTimeString(),
      }, ...prev].slice(0, 20));
    } finally {
      setRunning(null);
    }
  };

  const tierColors = { allow: 'var(--risk-safe)', step_up: 'var(--risk-warning)', restrict: 'var(--risk-danger)', revoke: 'var(--risk-critical)' };

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">API Sandbox</div>
          <div className="topbar-subtitle">Penetration test simulator — fire scenarios and watch the pipeline react</div>
        </div>
        <div className="topbar-right">
          <button className="btn btn-secondary btn-sm" onClick={() => setResults([])}>Clear Results</button>
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {/* Scenario cards */}
        <div className="card mb-16">
          <div className="card-title" style={{ marginBottom: 16 }}>🧪 Attack Scenarios</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            {SCENARIOS.map(s => (
              <button
                key={s.name}
                className="card"
                onClick={() => runScenario(s)}
                disabled={running === s.name}
                style={{
                  cursor: 'pointer', textAlign: 'left',
                  border: '1px solid var(--border-default)',
                  transition: 'all 0.2s',
                  opacity: running && running !== s.name ? 0.5 : 1,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                  {running === s.name ? '⏳ Running…' : s.name}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>{s.desc}</div>
                <div className="flex gap-8" style={{ flexWrap: 'wrap' }}>
                  <span className="mono" style={{ fontSize: 10, background: 'var(--bg-hover)', padding: '2px 6px', borderRadius: 4 }}>
                    {s.method} {s.endpoint}
                  </span>
                  <span className="mono" style={{ fontSize: 10, background: 'var(--bg-hover)', padding: '2px 6px', borderRadius: 4 }}>
                    {s.identity_id}
                  </span>
                  <span className="mono" style={{ fontSize: 10, background: 'var(--bg-hover)', padding: '2px 6px', borderRadius: 4 }}>
                    {s.geo}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Results */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">📋 Results</span>
            <span className="card-subtitle">{results.length} runs</span>
          </div>

          {!results.length ? (
            <div className="empty-state">
              <div className="empty-state-icon">🎯</div>
              <div className="empty-state-text">Click a scenario above to fire it through the ML pipeline</div>
            </div>
          ) : (
            <div className="scroll-x">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Scenario</th>
                    <th>Identity</th>
                    <th>ML</th>
                    <th>Rule</th>
                    <th>Final</th>
                    <th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={i} className="animate-slide-in" style={{ animationDelay: '0s' }}>
                      <td className="mono" style={{ fontSize: 11 }}>{r.timestamp}</td>
                      <td style={{ fontWeight: 600 }}>{r.scenario}</td>
                      <td className="mono">{r.identity_id ?? '—'}</td>
                      {r.error ? (
                        <td colSpan={4} style={{ color: 'var(--risk-critical)' }}>{r.error}</td>
                      ) : (
                        <>
                          <td><span style={{ color: 'var(--brand-accent)', fontWeight: 600 }}>{Math.round(r.ml_score ?? 0)}</span></td>
                          <td><span style={{ color: 'var(--brand-secondary)', fontWeight: 600 }}>{Math.round(r.rule_score ?? 0)}</span></td>
                          <td>
                            <span style={{ fontWeight: 800, color: tierColors[r.tier] || 'var(--text-primary)' }}>
                              {Math.round(r.risk_score ?? 0)}
                            </span>/100
                          </td>
                          <td>
                            <span className={`tier-badge ${r.tier}`}>
                              <div className="tier-dot" />{r.tier?.replace('_', '-').toUpperCase()}
                            </span>
                          </td>
                        </>
                      )}
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
