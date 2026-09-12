import { useState, useEffect } from 'react';
import { sentinelx as sxApi } from '../api/client';

export default function PolicyControl() {
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  const [allow, setAllow] = useState(30);
  const [stepUp, setStepUp] = useState(60);
  const [restrict, setRestrict] = useState(85);

  useEffect(() => {
    sxApi.policy().then(p => {
      setPolicy(p);
      const t = p.thresholds || {};
      setAllow(t.allow ?? 30);
      setStepUp(t.step_up ?? 60);
      setRestrict(t.restrict ?? 85);
    }).catch(console.error).finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMsg('');
    try {
      const updated = await sxApi.updatePolicy({ thresholds: { allow, step_up: stepUp, restrict } });
      setPolicy(updated);
      setMsg('✅ Policy updated — changes applied immediately');
    } catch (err) {
      setMsg(`❌ ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const tierColor = (val) =>
    val >= 85 ? 'var(--risk-critical)' : val >= 60 ? 'var(--risk-danger)' : val >= 30 ? 'var(--risk-warning)' : 'var(--risk-safe)';

  if (loading) return <><div className="topbar"><div className="topbar-title">Policy Control</div></div><div className="loading-center" style={{height:'80%'}}><div className="loading-spinner"/></div></>;

  return (
    <>
      <div className="topbar">
        <div>
          <div className="topbar-title">Policy Control</div>
          <div className="topbar-subtitle">Adjust enforcement thresholds in real time — no restart needed</div>
        </div>
      </div>

      <div className="page-content animate-fade-in">
        <div className="grid-2">
          {/* Threshold Sliders */}
          <div className="card">
            <div className="card-title" style={{ marginBottom: 20 }}>⚙️ Enforcement Thresholds</div>

            {[
              { label: 'Allow ≤', value: allow, setter: setAllow, color: 'var(--risk-safe)', desc: 'Requests below this score are proxied normally' },
              { label: 'Step-Up ≤', value: stepUp, setter: setStepUp, color: 'var(--risk-warning)', desc: 'Requests in this range trigger MFA challenge' },
              { label: 'Restrict ≤', value: restrict, setter: setRestrict, color: 'var(--risk-danger)', desc: 'Requests above this → read-only / rate-limited' },
            ].map(s => (
              <div key={s.label} style={{ marginBottom: 24 }}>
                <div className="flex justify-between items-center" style={{ marginBottom: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{s.label}</span>
                  <span className="mono" style={{ fontSize: 18, fontWeight: 800, color: s.color }}>{s.value}</span>
                </div>
                <input
                  type="range" min="0" max="100" value={s.value}
                  onChange={e => s.setter(Number(e.target.value))}
                  style={{ width: '100%', accentColor: s.color, height: 6, cursor: 'pointer' }}
                />
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{s.desc}</div>
              </div>
            ))}

            <div style={{ padding: '12px', background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: 'var(--radius-md)', marginBottom: 16 }}>
              <span style={{ fontSize: 12, color: 'var(--risk-critical)', fontWeight: 600 }}>
                🔴 Above {restrict} → REVOKE (session terminated)
              </span>
            </div>

            <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ width: '100%', justifyContent: 'center' }}>
              {saving ? 'Applying…' : 'Apply Policy'}
            </button>

            {msg && <div style={{ marginTop: 12, fontSize: 13, color: msg.startsWith('✅') ? 'var(--risk-safe)' : 'var(--risk-critical)' }}>{msg}</div>}
          </div>

          {/* Visual Preview */}
          <div className="card">
            <div className="card-title" style={{ marginBottom: 20 }}>📊 Threshold Visualization</div>

            <div style={{ position: 'relative', height: 320, background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
              {/* Allow zone */}
              <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: `${allow}%`, background: 'rgba(16,185,129,0.12)', borderTop: '2px solid var(--risk-safe)' }}>
                <div style={{ position: 'absolute', top: 4, left: 10, fontSize: 11, fontWeight: 700, color: 'var(--risk-safe)' }}>
                  ALLOW (0–{allow})
                </div>
              </div>

              {/* Step-up zone */}
              <div style={{ position: 'absolute', bottom: `${allow}%`, left: 0, right: 0, height: `${stepUp - allow}%`, background: 'rgba(245,158,11,0.1)', borderTop: '2px solid var(--risk-warning)' }}>
                <div style={{ position: 'absolute', top: 4, left: 10, fontSize: 11, fontWeight: 700, color: 'var(--risk-warning)' }}>
                  STEP-UP ({allow + 1}–{stepUp})
                </div>
              </div>

              {/* Restrict zone */}
              <div style={{ position: 'absolute', bottom: `${stepUp}%`, left: 0, right: 0, height: `${restrict - stepUp}%`, background: 'rgba(249,115,22,0.1)', borderTop: '2px solid var(--risk-danger)' }}>
                <div style={{ position: 'absolute', top: 4, left: 10, fontSize: 11, fontWeight: 700, color: 'var(--risk-danger)' }}>
                  RESTRICT ({stepUp + 1}–{restrict})
                </div>
              </div>

              {/* Revoke zone */}
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: `${100 - restrict}%`, background: 'rgba(239,68,68,0.12)', borderBottom: '2px solid var(--risk-critical)' }}>
                <div style={{ position: 'absolute', top: 4, left: 10, fontSize: 11, fontWeight: 700, color: 'var(--risk-critical)' }}>
                  REVOKE ({restrict + 1}–100)
                </div>
              </div>
            </div>

            {/* Hard Triggers */}
            <div style={{ marginTop: 20 }}>
              <div className="card-title" style={{ marginBottom: 10 }}>⚡ Hard Triggers</div>
              {(policy?.hard_triggers || []).map(t => (
                <div key={t} className="flex items-center gap-8" style={{ padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <span style={{ color: 'var(--risk-critical)', fontSize: 14 }}>●</span>
                  <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{t.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
