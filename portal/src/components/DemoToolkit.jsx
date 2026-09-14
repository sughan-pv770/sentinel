import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Rocket, ShieldAlert, ChevronUp, ChevronDown, Zap, Lock, Globe, AlertTriangle } from 'lucide-react';

const SCENARIOS = [
  {
    id: 'frequency_spike',
    label: '⚡ Frequency Burst / DDoS',
    desc: 'High-frequency request spike to test burst detection',
    icon: Zap
  },
  {
    id: 'privilege_escalation',
    label: '🔓 Privilege Escalation',
    desc: 'Unauthorized access attempt to /payments/transfer',
    icon: Lock
  },
  {
    id: 'new_admin_endpoint',
    label: '🚨 Admin Route Intrusion',
    desc: 'Non-admin accessing restricted /admin/users path',
    icon: AlertTriangle
  },
  {
    id: 'impossible_travel',
    label: '🌍 Impossible Travel Anomaly',
    desc: 'Session location jump to Moscow (RU-MOW) in <60s',
    icon: Globe
  }
];

const PRESETS = [50, 100, 250, 500];

export default function DemoToolkit() {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [scenario, setScenario] = useState('frequency_spike');
  const [count, setCount] = useState(250);
  const [result, setResult] = useState(null);

  if (!user) return null;

  const handleSimulate = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch('/sentinelx/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identity_id: user.identity_id,
          count: Number(count) || 100,
          scenario: scenario
        })
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Simulation failed');

      setResult({ 
        status: 'success', 
        tier: data.tier || 'step_up',
        count: data.count || count,
        scenario: scenario
      });

      // Dispatch live update event so all open dashboards refresh automatically
      window.dispatchEvent(new Event('sentinelx-risk-updated'));

    } catch (err) {
      setResult({ status: 'error', message: err.message });
    } finally {
      setLoading(false);
      setTimeout(() => setResult(null), 6000);
    }
  };

  return (
    <div className="demo-toolkit-wrapper">
      <div className={`demo-toolkit-panel ${isOpen ? 'open' : ''}`} style={{ maxWidth: '380px', width: '100%' }}>
        <div className="demo-toolkit-header" onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Rocket size={16} className="text-brand" />
            <span style={{ fontWeight: 600, fontSize: '13px' }}>⚡ Live Attack Simulation Toolkit</span>
          </div>
          {isOpen ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </div>
        
        {isOpen && (
          <div className="demo-toolkit-body" style={{ padding: '16px' }}>
            {/* Scenario selector */}
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '6px' }}>
              Select Attack Vector
            </label>
            <select
              value={scenario}
              onChange={e => setScenario(e.target.value)}
              className="input"
              style={{ width: '100%', marginBottom: '14px', fontSize: '12px', padding: '8px' }}
            >
              {SCENARIOS.map(s => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>

            {/* Request Count Selector */}
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '6px' }}>
              Request Burst Count
            </label>
            
            <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
              {PRESETS.map(p => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setCount(p)}
                  style={{
                    flex: 1,
                    padding: '6px 0',
                    fontSize: '12px',
                    fontWeight: count === p ? 700 : 500,
                    borderRadius: '6px',
                    border: '1px solid ' + (count === p ? 'var(--brand-primary)' : 'var(--border-subtle)'),
                    background: count === p ? 'rgba(59, 130, 246, 0.2)' : 'var(--bg-card)',
                    color: count === p ? 'white' : 'var(--text-secondary)',
                    cursor: 'pointer'
                  }}
                >
                  {p}
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Custom:</span>
              <input
                type="number"
                min="1"
                max="5000"
                value={count}
                onChange={e => setCount(Math.max(1, parseInt(e.target.value) || 1))}
                className="input"
                style={{ flex: 1, padding: '6px 10px', fontSize: '12px' }}
              />
            </div>

            {/* Trigger Button */}
            <button 
              className="btn btn-danger" 
              style={{ width: '100%', justifyContent: 'center', padding: '10px', fontSize: '13px', fontWeight: 600 }}
              onClick={handleSimulate}
              disabled={loading}
            >
              <ShieldAlert size={16} />
              {loading ? 'Executing Simulation...' : `Launch Attack (${count} Requests)`}
            </button>

            {/* Result Toast */}
            {result && (
              <div style={{
                marginTop: '12px',
                fontSize: '12px',
                padding: '10px',
                borderRadius: '6px',
                background: result.status === 'success' ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)',
                border: '1px solid ' + (result.status === 'success' ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'),
                color: result.status === 'success' ? 'var(--risk-safe)' : 'var(--risk-critical)'
              }}>
                {result.status === 'success' ? (
                  <>
                    ✓ Fired <strong>{result.count}</strong> requests! Adaptive Tier shifted to <strong>{result.tier.toUpperCase()}</strong>. Portal updated real-time!
                  </>
                ) : (
                  <>❌ Error: {result.message}</>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
