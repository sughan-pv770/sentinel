/**
 * MFAEnrollPage — TOTP setup with QR code scan.
 *
 * Flow:
 *  Step 1 — Show QR code → user scans with Google Authenticator / Authy / any TOTP app
 *  Step 2 — Live 30-second window ring + 6-digit verification (confirm the app is linked)
 *  Step 3 — Done: show backup codes, mark enrolled
 *
 * The TOTP standard (RFC 6238): every 30 seconds, the authenticator derives
 * a new 6-digit code from the shared secret + current Unix time ÷ 30.
 * User just enters whatever code their app is currently showing.
 */
import { useState, useEffect, useRef } from 'react';
import { useAuth } from './AuthContext';
import { Shield, Copy, Check, ArrowLeft, ArrowRight, Download, RefreshCw } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { mfa as mfaApi } from '../api/client';

// ── Live TOTP window ring (pure math — no backend needed) ─────────────────────
// Returns seconds remaining in the current 30-second TOTP window.
function useTotpWindow() {
  const [secsLeft, setSecsLeft] = useState(() => 30 - (Math.floor(Date.now() / 1000) % 30));
  useEffect(() => {
    const tick = () => setSecsLeft(30 - (Math.floor(Date.now() / 1000) % 30));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return secsLeft;
}

// SVG ring countdown — shows the current TOTP window visually
function TotpWindowRing({ size = 64, strokeWidth = 4 }) {
  const secsLeft = useTotpWindow();
  const r = (size - strokeWidth * 2) / 2;
  const circ = 2 * Math.PI * r;
  const pct = secsLeft / 30;
  const color = secsLeft <= 5 ? '#ef4444' : secsLeft <= 10 ? '#f59e0b' : '#6366f1';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r}
          fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={strokeWidth} />
        <circle cx={size/2} cy={size/2} r={r}
          fill="none" stroke={color} strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - pct)}
          style={{ transition: 'stroke-dashoffset 0.9s linear, stroke 0.3s ease' }}
        />
      </svg>
      <div style={{
        fontSize: 11, fontWeight: 600, color,
        marginTop: -size - 2, marginBottom: size - 4,
        fontFamily: 'monospace',
      }}>
        {secsLeft}s
      </div>
    </div>
  );
}

export default function MFAEnrollPage() {
  const { user } = useAuth();
  const navigate  = useNavigate();
  const [step, setStep]         = useState(1);   // 1=QR, 2=verify, 3=done
  const [enrollment, setEnroll] = useState(null);
  const [digits, setDigits]     = useState(Array(6).fill(''));
  const [loading, setLoading]   = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]       = useState('');
  const [shake, setShake]       = useState(false);
  const [copied, setCopied]     = useState('');
  const inputRefs = useRef([]);

  useEffect(() => { fetchEnrollment(); }, []);
  useEffect(() => { if (step === 2) setTimeout(() => inputRefs.current[0]?.focus(), 100); }, [step]);

  const fetchEnrollment = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await mfaApi.enrollTotp();
      setEnroll(data);
      if (data.already_enrolled) setStep(3);
    } catch {
      setError('Could not load enrollment. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const copyText = async (text, key) => {
    await navigator.clipboard.writeText(text).catch(() => {});
    setCopied(key);
    setTimeout(() => setCopied(''), 2000);
  };

  const downloadBackupCodes = () => {
    const txt = [
      'SentinelX — TOTP Backup Codes',
      `Account: ${user?.identity_id}`,
      `Generated: ${new Date().toLocaleString()}`,
      '',
      'Each code can only be used once.',
      '',
      ...(enrollment?.backup_codes || []),
    ].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([txt], { type: 'text/plain' }));
    a.download = 'sentinelx-backup-codes.txt';
    a.click();
  };

  // 6-box digit entry
  const handleDigit = (idx, val) => {
    const ch = val.replace(/\D/g, '').slice(-1);
    const next = [...digits]; next[idx] = ch; setDigits(next); setError('');
    if (ch && idx < 5) inputRefs.current[idx + 1]?.focus();
    if (ch && next.every(d => d)) submitVerify(next.join(''));
  };
  const handleKeyDown = (idx, e) => {
    if (e.key === 'Backspace' && !digits[idx] && idx > 0) inputRefs.current[idx - 1]?.focus();
    if (e.key === 'ArrowLeft'  && idx > 0) inputRefs.current[idx - 1]?.focus();
    if (e.key === 'ArrowRight' && idx < 5) inputRefs.current[idx + 1]?.focus();
  };
  const handlePaste = (e) => {
    e.preventDefault();
    const paste = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (!paste) return;
    const next = Array(6).fill('');
    paste.split('').forEach((c, i) => { next[i] = c; });
    setDigits(next);
    inputRefs.current[Math.min(paste.length - 1, 5)]?.focus();
    if (paste.length === 6) submitVerify(paste);
  };

  const submitVerify = async (code) => {
    if (submitting) return;
    setSubmitting(true); setError('');
    try {
      await mfaApi.verifyTotp(code, 'enroll', true);
      setStep(3);
    } catch (err) {
      setError(err?.data?.detail || 'Incorrect code. Check your authenticator app and try again.');
      setShake(true); setTimeout(() => setShake(false), 600);
      setDigits(Array(6).fill(''));
      setTimeout(() => inputRefs.current[0]?.focus(), 50);
    } finally {
      setSubmitting(false);
    }
  };

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <div style={{ width: 40, height: 40, border: '3px solid rgba(99,102,241,0.2)', borderTopColor: '#6366f1', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
    </div>
  );

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg, #0d0d1a)',
      padding: 24,
    }}>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes shake {
          0%,100% { transform: translateX(0); }
          20% { transform: translateX(-8px); }
          40% { transform: translateX(8px); }
          60% { transform: translateX(-5px); }
          80% { transform: translateX(5px); }
        }
        .enroll-shake { animation: shake 0.55s ease; }
        .mfa-digit-enroll {
          width: 46px; height: 56px;
          background: rgba(255,255,255,0.05);
          border: 1.5px solid rgba(255,255,255,0.1);
          border-radius: 10px;
          font-size: 22px; font-weight: 700; font-family: monospace;
          color: #fff; text-align: center;
          outline: none; caret-color: transparent;
          transition: border-color 0.15s, box-shadow 0.15s;
        }
        .mfa-digit-enroll:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.2); }
        .mfa-digit-enroll.filled { border-color: rgba(99,102,241,0.5); }
      `}</style>

      <div style={{ maxWidth: 460, width: '100%' }}>
        {/* Back link */}
        <Link to="/student" style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          color: 'rgba(255,255,255,0.4)', fontSize: 13, textDecoration: 'none',
          marginBottom: 24,
        }}>
          <ArrowLeft size={14} /> Back to dashboard
        </Link>

        {/* Card */}
        <div style={{
          background: 'var(--surface, #1e1e2e)',
          border: '1px solid rgba(255,255,255,0.07)',
          borderRadius: 20,
          overflow: 'hidden',
          boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
        }}>
          {/* Progress bar */}
          <div style={{ height: 3, background: 'rgba(255,255,255,0.05)' }}>
            <div style={{
              height: '100%',
              width: step === 1 ? '33%' : step === 2 ? '66%' : '100%',
              background: 'linear-gradient(90deg,#6366f1,#8b5cf6)',
              transition: 'width 0.5s ease',
            }} />
          </div>

          <div style={{ padding: 32 }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
              <div style={{
                width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                background: 'linear-gradient(135deg,#6366f1,#4f46e5)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 6px 20px rgba(99,102,241,0.3)',
              }}>
                <Shield size={20} color="white" strokeWidth={1.5} />
              </div>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#fff' }}>
                  {step === 1 ? 'Set Up Authenticator App' :
                   step === 2 ? 'Confirm Your Code' : 'Authenticator Linked!'}
                </div>
                <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginTop: 2 }}>
                  Step {Math.min(step, 3)} of 3
                </div>
              </div>
            </div>

            {/* ── STEP 1: QR Code ─────────────────────────────────────────── */}
            {step === 1 && enrollment && (
              <div>
                <p style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', lineHeight: 1.6, marginBottom: 20 }}>
                  Open <strong style={{ color: '#fff' }}>Google Authenticator</strong>, <strong style={{ color: '#fff' }}>Authy</strong>, or any TOTP app,
                  then scan this QR code to link your account.
                </p>

                {/* QR Code */}
                <div style={{
                  background: '#fff', borderRadius: 14,
                  padding: 12, display: 'inline-block',
                  marginBottom: 20, display: 'flex',
                  justifyContent: 'center',
                }}>
                  {enrollment.qr_code_png ? (
                    <img
                      src={enrollment.qr_code_png}
                      alt="TOTP QR Code"
                      style={{ width: 180, height: 180, display: 'block', imageRendering: 'pixelated' }}
                    />
                  ) : (
                    <div style={{
                      width: 180, height: 180, background: '#f1f5f9',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexDirection: 'column', gap: 8, color: '#64748b', fontSize: 12,
                    }}>
                      <span>QR unavailable</span>
                      <span>Use manual entry below</span>
                    </div>
                  )}
                </div>

                {/* Manual entry secret */}
                <div style={{ marginBottom: 20 }}>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginBottom: 8, fontWeight: 500 }}>
                    CAN'T SCAN? ENTER THIS KEY MANUALLY
                  </div>
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 10, padding: '10px 14px',
                  }}>
                    <code style={{
                      flex: 1, fontFamily: 'monospace', fontSize: 14,
                      letterSpacing: '0.12em', color: '#a5b4fc',
                      wordBreak: 'break-all',
                    }}>
                      {enrollment.secret}
                    </code>
                    <button onClick={() => copyText(enrollment.secret, 'secret')} style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: copied === 'secret' ? '#22c55e' : 'rgba(255,255,255,0.4)',
                      padding: 4, flexShrink: 0,
                    }}>
                      {copied === 'secret' ? <Check size={15} /> : <Copy size={15} />}
                    </button>
                  </div>
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.25)', marginTop: 6 }}>
                    Account: <strong style={{ color: 'rgba(255,255,255,0.4)' }}>{user?.name}</strong>
                    {' · '}Issuer: SentinelX
                    {' · '}Time-based · 30-second window
                  </div>
                </div>

                <button
                  onClick={() => setStep(2)}
                  style={{
                    width: '100%', padding: 13,
                    background: 'linear-gradient(135deg,#6366f1,#4f46e5)',
                    border: 'none', borderRadius: 12,
                    color: '#fff', fontSize: 14, fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    boxShadow: '0 4px 15px rgba(99,102,241,0.3)',
                  }}
                >
                  I've scanned the code <ArrowRight size={16} />
                </button>
              </div>
            )}

            {/* ── STEP 2: Verify first code ──────────────────────────────── */}
            {step === 2 && (
              <div>
                <div style={{ textAlign: 'center', marginBottom: 24 }}>
                  {/* Live TOTP window ring */}
                  <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
                    <TotpWindowRing size={72} strokeWidth={5} />
                  </div>
                  <p style={{ fontSize: 13, color: 'rgba(255,255,255,0.5)', lineHeight: 1.6, margin: 0 }}>
                    Open your authenticator app and enter the <strong style={{ color: '#fff' }}>6-digit code</strong> currently displayed.
                    The ring shows how many seconds until the code refreshes.
                  </p>
                </div>

                <div className={shake ? 'enroll-shake' : ''}>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 16 }}>
                    {digits.map((d, i) => (
                      <input
                        key={i}
                        ref={el => inputRefs.current[i] = el}
                        className={`mfa-digit-enroll${d ? ' filled' : ''}`}
                        type="text"
                        inputMode="numeric"
                        maxLength={1}
                        value={d}
                        onChange={e => handleDigit(i, e.target.value)}
                        onKeyDown={e => handleKeyDown(i, e)}
                        onPaste={i === 0 ? handlePaste : undefined}
                        disabled={submitting}
                        autoComplete="one-time-code"
                      />
                    ))}
                  </div>
                </div>

                {error && (
                  <div style={{
                    fontSize: 13, color: '#f87171', textAlign: 'center',
                    marginBottom: 12, padding: '8px 12px',
                    background: 'rgba(239,68,68,0.08)', borderRadius: 8,
                  }}>
                    {error}
                  </div>
                )}

                <button
                  onClick={() => submitVerify(digits.join(''))}
                  disabled={submitting || digits.join('').length < 6}
                  style={{
                    width: '100%', padding: 13,
                    background: 'linear-gradient(135deg,#6366f1,#4f46e5)',
                    border: 'none', borderRadius: 12,
                    color: '#fff', fontSize: 14, fontWeight: 600,
                    cursor: submitting ? 'wait' : 'pointer',
                    opacity: digits.join('').length < 6 ? 0.5 : 1,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    boxShadow: '0 4px 15px rgba(99,102,241,0.3)',
                  }}
                >
                  {submitting ? 'Verifying…' : 'Confirm & Enable MFA'}
                </button>

                <button onClick={() => setStep(1)} style={{
                  width: '100%', marginTop: 10, padding: 11,
                  background: 'transparent', border: '1px solid rgba(255,255,255,0.08)',
                  borderRadius: 12, color: 'rgba(255,255,255,0.4)', fontSize: 13, cursor: 'pointer',
                }}>
                  ← Go back to QR code
                </button>
              </div>
            )}

            {/* ── STEP 3: Done + backup codes ───────────────────────────── */}
            {step === 3 && (
              <div>
                <div style={{
                  textAlign: 'center', marginBottom: 24,
                  padding: 20, background: 'rgba(34,197,94,0.06)',
                  border: '1px solid rgba(34,197,94,0.15)', borderRadius: 14,
                }}>
                  <div style={{
                    width: 52, height: 52, borderRadius: 14,
                    background: 'linear-gradient(135deg,#22c55e,#16a34a)',
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    marginBottom: 12,
                    boxShadow: '0 6px 20px rgba(34,197,94,0.3)',
                  }}>
                    <Shield size={24} color="white" strokeWidth={1.5} />
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#4ade80' }}>
                    {enrollment?.already_enrolled ? 'Already Enrolled' : 'Authenticator Linked!'}
                  </div>
                  <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.4)', marginTop: 6 }}>
                    {enrollment?.already_enrolled
                      ? 'Your account already has TOTP enabled.'
                      : 'Your account is now protected with TOTP.'}
                  </div>
                </div>

                {enrollment?.backup_codes && !enrollment.already_enrolled && (
                  <div style={{ marginBottom: 20 }}>
                    <div style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      marginBottom: 10,
                    }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'rgba(255,255,255,0.5)' }}>
                        BACKUP CODES — SAVE THESE NOW
                      </div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button onClick={downloadBackupCodes} style={{
                          background: 'none', border: 'none', cursor: 'pointer',
                          color: 'rgba(255,255,255,0.4)', fontSize: 11,
                          display: 'flex', alignItems: 'center', gap: 4,
                        }}>
                          <Download size={12} /> Download
                        </button>
                        <button onClick={() => copyText(enrollment.backup_codes.join('\n'), 'backup')} style={{
                          background: 'none', border: 'none', cursor: 'pointer',
                          color: copied === 'backup' ? '#22c55e' : 'rgba(255,255,255,0.4)',
                          fontSize: 11, display: 'flex', alignItems: 'center', gap: 4,
                        }}>
                          {copied === 'backup' ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy all</>}
                        </button>
                      </div>
                    </div>
                    <div style={{
                      display: 'grid', gridTemplateColumns: '1fr 1fr',
                      gap: 6,
                    }}>
                      {enrollment.backup_codes.map((code, i) => (
                        <div key={i} style={{
                          fontFamily: 'monospace', fontSize: 13, fontWeight: 600,
                          padding: '7px 12px', textAlign: 'center',
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          borderRadius: 8, color: 'rgba(255,255,255,0.7)',
                          letterSpacing: '0.1em',
                        }}>
                          {code}
                        </div>
                      ))}
                    </div>
                    <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.25)', marginTop: 8 }}>
                      Each code can only be used once. Store these somewhere safe — they won't be shown again.
                    </div>
                  </div>
                )}

                <button onClick={() => navigate('/student')} style={{
                  width: '100%', padding: 13,
                  background: 'linear-gradient(135deg,#6366f1,#4f46e5)',
                  border: 'none', borderRadius: 12,
                  color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  boxShadow: '0 4px 15px rgba(99,102,241,0.3)',
                }}>
                  Return to Dashboard
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
