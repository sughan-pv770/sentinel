import { useState, useEffect } from 'react';
import { sentinelx as sxApi } from '../api/client';

const STAGES = [
  { id: 1, label: 'Request Intake', icon: '📥', desc: 'Headers parsed into RequestContext' },
  { id: 2, label: 'Feature Extraction', icon: '🧠', desc: '7-signal behavioral vector built' },
  { id: '3A', label: 'Rule Engine', icon: '📏', desc: 'Deterministic hard triggers evaluated', parallel: true },
  { id: '3B', label: 'ML Isolation Forest', icon: '🤖', desc: 'Unsupervised anomaly detection', parallel: true },
  { id: 4, label: 'Score Blending', icon: '⚖️', desc: 'Rules×45% + ML×55% composite' },
  { id: 5, label: 'Policy Enforcement', icon: '🛡️', desc: 'ALLOW / STEP-UP / RESTRICT / REVOKE' },
];

const SIGNALS = [
  { key: 'request_frequency_per_min', label: 'Req Frequency', max: 30 },
  { key: 'endpoint_novelty',          label: 'Endpoint Novelty', max: 1 },
  { key: 'geo_change',                label: 'Geo Change', max: 1 },
  { key: 'device_change',             label: 'Device Change', max: 1 },
  { key: 'time_of_day_deviation',     label: 'Time Deviation', max: 1 },
  { key: 'payload_size_zscore',       label: 'Payload Z-Score', max: 5 },
  { key: 'token_age_seconds',         label: 'Token Age (s)', max: 3600 },
];

function signalColor(ratio) {
  if (ratio >= 0.75) return 'var(--risk-critical)';
  if (ratio >= 0.5)  return 'var(--risk-danger)';
  if (ratio >= 0.25) return 'var(--risk-warning)';
  return 'var(--risk-safe)';
}

export default function PipelineMonitor() {
  const [lastDecision, setLastDecision] = useState(null);
  const [activeStage, setActiveStage] = useState(null);
  const [animating, setAnimating] = useState(false);
  const [stats, setStats] = useState(null);

  const fetchLatest = async () => {
    try {
      const alerts = await sxApi.alerts(5);
      const s = await sxApi.stats();
      setStats(s);
      if (alerts?.length > 0) {
        setLastDecision(alerts[0]);
      }
    } catch {}
  };

  useEffect(() => {
    fetchLatest();
    const iv = setInterval(fetchLatest, 5000);
    return () => clearInterval(iv);
  }, []);

  const animatePipeline = () => {
    if (animating) return;
    setAnimating(true);
    const stages = [1, 2, '3A', '3B', 4, 5];
    stages.forEach((s, i) => {
      setTimeout(() => {
        setActiveStage(s);
        if (i === stages.length - 1) {
          setTimeout(() => { setAnimating(false); setActiveStage(null); }, 800);
        }
      }, i * 500);
    });
  };

  const features = lastDecision?.feature_details || {};
  const tier = lastDecision?.tier;
  const tierColors = { allow: 'var(--risk-safe)', step_up: 'var(--risk-warning)', restrict: 'var(--risk-danger)', revoke: 'var(--risk-critical)' };

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">ML Pipeline Monitor</div>
          <div className="topbar-subtitle">5-stage Zero Trust scoring pipeline · Live visualization</div>
        </div>
        <div className="topbar-right">
          <button className="btn btn-primary btn-sm" onClick={animatePipeline} disabled={animating}>
            {animating ? '▶ Animating…' : '▶ Animate Pipeline'}
          </button>
          {stats && <span className="mono" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {stats.identities_tracked} identities · {stats.backend}
          </span>}
        </div>
      </div>

      <div className="page-content animate-fade-in">
        {/* Pipeline visualization */}
        <div className="card mb-16">
          <div className="card-title" style={{ marginBottom: 20 }}>5-Stage Request Lifecycle</div>

          {/* Linear stages 1–2 */}
          <div className="flex items-center" style={{ gap: 0, marginBottom: 16 }}>
            {[1, 2].map((id, i) => {
              const stage = STAGES.find(s => s.id === id);
              const isActive = activeStage === id;
              return (
                <>
                  <div key={id} className={`pipeline-stage-box ${isActive ? 'active' : (animating && activeStage > id ? 'done' : '')}`} style={{ flex: 1 }}>
                    <div style={{ fontSize: 24, marginBottom: 6 }}>{stage.icon}</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 3 }}>
                      Stage {stage.id}
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--brand-primary)' }}>{stage.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{stage.desc}</div>
                  </div>
                  {i < 1 && <div className={`pipeline-connector ${isActive || (animating && activeStage > id) ? 'active' : ''}`} style={{ minWidth: 32 }} />}
                </>
              );
            })}

            {/* Connector to split */}
            <div className={`pipeline-connector ${activeStage === '3A' || activeStage === '3B' || (animating && [4,5].includes(activeStage)) ? 'active' : ''}`} style={{ minWidth: 32 }} />

            {/* Parallel stages */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>
                Parallel Scoring
              </div>
              {['3A', '3B'].map(id => {
                const stage = STAGES.find(s => s.id === id);
                const isActive = activeStage === id;
                return (
                  <div key={id} className={`pipeline-stage-box ${isActive ? 'active' : ''}`} style={{ textAlign: 'left', display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ fontSize: 20 }}>{stage.icon}</span>
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-primary)' }}>Stage {stage.id}</div>
                      <div style={{ fontSize: 10, color: 'var(--brand-primary)' }}>{stage.label}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Connector to 4 & 5 */}
            <div className={`pipeline-connector ${[4,5].includes(activeStage) ? 'active' : ''}`} style={{ minWidth: 32 }} />

            {/* Stages 4–5 */}
            {[4, 5].map((id, i) => {
              const stage = STAGES.find(s => s.id === id);
              const isActive = activeStage === id;
              return (
                <>
                  <div key={id} className={`pipeline-stage-box ${isActive ? 'active' : ''}`} style={{ flex: 1 }}>
                    <div style={{ fontSize: 24, marginBottom: 6 }}>{stage.icon}</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 3 }}>Stage {stage.id}</div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--brand-primary)' }}>{stage.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{stage.desc}</div>
                    {id === 5 && lastDecision && (
                      <div className={`tier-badge ${tier}`} style={{ marginTop: 8 }}>
                        <div className="tier-dot" />
                        {tier?.toUpperCase()}
                      </div>
                    )}
                  </div>
                  {i < 1 && <div className={`pipeline-connector ${activeStage === 5 ? 'active' : ''}`} style={{ minWidth: 32 }} />}
                </>
              );
            })}
          </div>
        </div>

        {/* Score breakdown */}
        {lastDecision && (
          <div className="grid-2 mb-16">
            <div className="card">
              <div className="card-title" style={{ marginBottom: 12 }}>📊 Last Scored Request</div>
              <div className="flex flex-col gap-8">
                {[
                  { label: 'Identity', value: lastDecision.identity_id, mono: true },
                  { label: 'Endpoint', value: lastDecision.endpoint, mono: true },
                  { label: 'ML Score', value: `${Math.round(lastDecision.ml_score ?? 0)} / 100` },
                  { label: 'Rule Score', value: `${Math.round(lastDecision.rule_score ?? 0)} / 100` },
                  { label: 'Final Risk', value: `${Math.round(lastDecision.risk_score ?? 0)} / 100`, bold: true },
                  { label: 'Verdict', value: lastDecision.tier?.toUpperCase() },
                ].map(r => (
                  <div key={r.label} className="flex justify-between items-center" style={{ padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{r.label}</span>
                    <span className={r.mono ? 'mono' : ''} style={{ fontSize: 13, fontWeight: r.bold ? 800 : 600, color: r.bold ? tierColors[tier] : 'var(--text-primary)' }}>
                      {r.value}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="card-title" style={{ marginBottom: 12 }}>📈 Alert Reasons</div>
              {(lastDecision.reasons || []).length === 0 ? (
                <div className="empty-state" style={{ padding: 24 }}>
                  <div className="empty-state-text">No alert reasons (normal request)</div>
                </div>
              ) : (
                (lastDecision.reasons || []).map((r, i) => (
                  <div key={i} className="alert-item" style={{ marginBottom: 6 }}>
                    <div className="alert-icon">⚠️</div>
                    <div className="alert-body">
                      <div className="alert-detail">{typeof r === 'string' ? r : r?.message}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* 7-signal feature vector */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">🧬 Live Feature Vector</span>
            <span className="card-subtitle">Last scored request · 7-signal behavioral dimensions</span>
          </div>

          {Object.keys(features).length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">📡</div>
              <div className="empty-state-text">Fire a scenario in API Sandbox to populate the feature vector</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {SIGNALS.map(sig => {
                const val = features[sig.key] ?? 0;
                const ratio = Math.min(val / sig.max, 1);
                const color = signalColor(ratio);
                return (
                  <div key={sig.key} className="flex items-center gap-12">
                    <div style={{ width: 140, fontSize: 12, color: 'var(--text-secondary)', flexShrink: 0 }}>{sig.label}</div>
                    <div className="feature-bar-track" style={{ flex: 1 }}>
                      <div className="feature-bar-fill" style={{ width: `${ratio * 100}%`, background: color }} />
                    </div>
                    <span className="mono" style={{ fontSize: 12, fontWeight: 700, color, width: 60, textAlign: 'right', flexShrink: 0 }}>
                      {typeof val === 'number' ? val.toFixed(3) : val}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
