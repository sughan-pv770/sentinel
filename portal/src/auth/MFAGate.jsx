/**
 * MFAGate — Production adaptive MFA interceptor.
 *
 * For TOTP (enrolled users): shows a live 30-second window ring —
 * same visual that the authenticator app shows, so user knows exactly
 * when their code refreshes without any guessing.
 *
 * For Email OTP: shows code inline in dev mode as a subtle hint.
 *
 * Triggered two ways:
 *  1. secureCall(fn) — wraps any API call; intercepts step_up_required 401
 *  2. mfa_challenge SSE event — AuthContext sets pendingMfaChallenge
 */
import {
  createContext, useContext, useState, useCallback,
  useRef, useEffect,
} from 'react';
import { mfa as mfaApi, retryPendingRequest } from '../api/client';
import { useAuth } from './AuthContext';
import { ShieldCheck, KeyRound, Clock, ArrowRight, RotateCcw, Smartphone } from 'lucide-react';

const MFAGateContext = createContext(null);

// ── Live TOTP window countdown (pure client-side math) ────────────────────────
// TOTP codes refresh every 30 seconds aligned to Unix time.
// This hook tells you how many seconds are left in the CURRENT window.
function useTotpWindow() {
  const [secsLeft, setSecsLeft] = useState(
    () => 30 - (Math.floor(Date.now() / 1000) % 30)
  );
  useEffect(() => {
    const tick = () => setSecsLeft(30 - (Math.floor(Date.now() / 1000) % 30));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return secsLeft;
}

// SVG ring — matches the visual language of Google Authenticator
function TotpRing({ size = 52 }) {
  const secsLeft = useTotpWindow();
  const sw = 4;
  const r  = (size - sw * 2) / 2;
  const circ = 2 * Math.PI * r;
  const pct  = secsLeft / 30;
  const color = secsLeft <= 5 ? '#ef4444' : secsLeft <= 10 ? '#f59e0b' : '#6366f1';

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r}
          fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth={sw} />
        <circle cx={size/2} cy={size/2} r={r}
          fill="none" stroke={color} strokeWidth={sw}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - pct)}
          style={{ transition: 'stroke-dashoffset 0.9s linear, stroke 0.3s ease' }}
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 13, fontWeight: 700, color, fontFamily: 'monospace',
      }}>
        {secsLeft}
      </div>
    </div>
  );
}


// ── Provider ──────────────────────────────────────────────────────────────────

export function MFAGateProvider({ children }) {
  const { logout, pendingMfaChallenge, clearMfaChallenge } = useAuth();
  const [mfaState, setMfaState] = useState(null);
  const resolveRef = useRef(null);
  const rejectRef  = useRef(null);

  // Watch for SSE-pushed mfa_challenge (simulator step_up → immediate modal)
  useEffect(() => {
    if (pendingMfaChallenge && !mfaState) {
      setMfaState({ challenge: pendingMfaChallenge, pendingError: null });
    }
  }, [pendingMfaChallenge]); // eslint-disable-line

  /** Wrap any API call. If it 401s with step_up_required, show modal + retry. */
  const secureCall = useCallback(async (fn) => {
    try {
      return await fn();
    } catch (err) {
      if (err.mfaRequired) {
        return new Promise((resolve, reject) => {
          resolveRef.current = resolve;
          rejectRef.current  = reject;
          setMfaState({ challenge: err.challenge, pendingError: err });
        });
      }
      throw err;
    }
  }, []);

  const handleVerified = useCallback(async (pendingError) => {
    setMfaState(null);
    clearMfaChallenge();
    if (pendingError) {
      try { resolveRef.current?.(await retryPendingRequest(pendingError)); }
      catch (err) { rejectRef.current?.(err); }
    } else {
      resolveRef.current?.(null);
    }
  }, [clearMfaChallenge]);

  const handleCancel = useCallback(async () => {
    setMfaState(null);
    clearMfaChallenge();
    rejectRef.current?.(new Error('MFA cancelled'));
    await logout();
  }, [logout, clearMfaChallenge]);

  return (
    <MFAGateContext.Provider value={{ secureCall }}>
      {children}
      {mfaState && (
        <MFAModal
          challenge={mfaState.challenge}
          pendingError={mfaState.pendingError}
          onVerified={handleVerified}
          onCancel={handleCancel}
        />
      )}
    </MFAGateContext.Provider>
  );
}

export function useMFAGate() {
  const ctx = useContext(MFAGateContext);
  if (!ctx) throw new Error('useMFAGate must be used within MFAGateProvider');
  return ctx;
}


// ── MFA Modal ─────────────────────────────────────────────────────────────────

function MFAModal({ challenge, pendingError, onVerified, onCancel }) {
  const NUM   = 6;
  const method    = challenge?.method || 'totp';
  const sessionId = challenge?.session_id
    || pendingError?.data?.challenge?.session_id || '';
  const devOtp    = challenge?._dev_otp || null;
  const isTotp    = method === 'totp';

  const [digits, setDigits]   = useState(Array(NUM).fill(''));
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');
  const [shake, setShake]     = useState(false);
  const [success, setSuccess] = useState(false);
  const inputRefs = useRef([]);

  // Countdown only relevant for email OTP
  const [emailTtl, setEmailTtl] = useState(challenge?.ttl_seconds || 300);
  useEffect(() => {
    if (isTotp) return;
    if (emailTtl <= 0) return;
    const t = setInterval(() => setEmailTtl(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [isTotp]);

  useEffect(() => { setTimeout(() => inputRefs.current[0]?.focus(), 80); }, []);

  const fmt = s => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`;

  const handleDigit = (idx, val) => {
    const ch = val.replace(/\D/g, '').slice(-1);
    const next = [...digits]; next[idx] = ch;
    setDigits(next); setError('');
    if (ch && idx < NUM - 1) inputRefs.current[idx + 1]?.focus();
    if (ch && next.every(d => d)) submit(next.join(''));
  };

  const handleKey = (idx, e) => {
    if (e.key === 'Backspace' && !digits[idx] && idx > 0) inputRefs.current[idx - 1]?.focus();
    if (e.key === 'ArrowLeft'  && idx > 0) inputRefs.current[idx - 1]?.focus();
    if (e.key === 'ArrowRight' && idx < NUM - 1) inputRefs.current[idx + 1]?.focus();
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const p = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, NUM);
    if (!p) return;
    const next = Array(NUM).fill('');
    p.split('').forEach((c, i) => { next[i] = c; });
    setDigits(next);
    inputRefs.current[Math.min(p.length - 1, NUM - 1)]?.focus();
    if (p.length === NUM) submit(p);
  };

  const submit = async (code) => {
    if (loading) return;
    setLoading(true); setError('');
    try {
      if (isTotp) await mfaApi.verifyTotp(code, sessionId, false);
      else        await mfaApi.verifyOtp(code, sessionId);
      setSuccess(true);
      setTimeout(() => onVerified(pendingError), 900);
    } catch (err) {
      setError(err?.data?.detail || 'Incorrect code. Please try again.');
      setShake(true); setTimeout(() => setShake(false), 600);
      setDigits(Array(NUM).fill(''));
      setTimeout(() => inputRefs.current[0]?.focus(), 50);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @keyframes mfg-in {
          from { opacity:0; transform:translateY(24px) scale(0.97); }
          to   { opacity:1; transform:translateY(0) scale(1); }
        }
        @keyframes mfg-bd { from{opacity:0}to{opacity:1} }
        @keyframes mfg-shake {
          0%,100%{transform:translateX(0)} 20%{transform:translateX(-8px)}
          40%{transform:translateX(8px)} 60%{transform:translateX(-5px)} 80%{transform:translateX(5px)}
        }
        @keyframes mfg-success-pulse {
          0%{box-shadow:0 0 0 0 rgba(34,197,94,.4)} 70%{box-shadow:0 0 0 12px rgba(34,197,94,0)} 100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}
        }
        .mfg-digit {
          width:46px; height:56px;
          background:rgba(255,255,255,0.05);
          border:1.5px solid rgba(255,255,255,0.1);
          border-radius:10px;
          font-size:22px; font-weight:700; font-family:monospace;
          color:#fff; text-align:center; outline:none; caret-color:transparent;
          transition:border-color .15s, box-shadow .15s;
        }
        .mfg-digit:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.2);}
        .mfg-digit.filled{border-color:rgba(99,102,241,.5);}
        .mfg-digit.ok{border-color:#22c55e!important;box-shadow:0 0 0 3px rgba(34,197,94,.2)!important;}
        .mfg-shake{animation:mfg-shake .55s ease;}
      `}</style>

      {/* Backdrop */}
      <div style={{
        position:'fixed', inset:0, zIndex:9999,
        background:'rgba(0,0,0,0.65)', backdropFilter:'blur(18px)',
        display:'flex', alignItems:'center', justifyContent:'center', padding:16,
        animation:'mfg-bd .25s ease',
      }}>
        {/* Card */}
        <div style={{
          background:'var(--surface,#1e1e2e)',
          border:'1px solid rgba(255,255,255,0.08)',
          borderRadius:20, padding:'32px 28px',
          width:'100%', maxWidth:400,
          boxShadow:'0 32px 80px rgba(0,0,0,0.6)',
          animation:'mfg-in .3s cubic-bezier(.16,1,.3,1)',
        }}>
          {/* Header icon */}
          <div style={{ display:'flex', alignItems:'center', gap:14, marginBottom:20 }}>
            <div style={{
              width:50, height:50, borderRadius:14, flexShrink:0,
              background: success
                ? 'linear-gradient(135deg,#22c55e,#16a34a)'
                : 'linear-gradient(135deg,#6366f1,#4f46e5)',
              display:'flex', alignItems:'center', justifyContent:'center',
              boxShadow: success
                ? '0 6px 20px rgba(34,197,94,.3)'
                : '0 6px 20px rgba(99,102,241,.3)',
              transition:'all .4s ease',
              animation: success ? 'mfg-success-pulse .8s ease' : 'none',
            }}>
              {success
                ? <ShieldCheck size={24} color="white" strokeWidth={1.5} />
                : isTotp
                  ? <Smartphone size={24} color="white" strokeWidth={1.5} />
                  : <KeyRound   size={24} color="white" strokeWidth={1.5} />
              }
            </div>
            <div>
              <div style={{fontSize:16,fontWeight:700,color:'#fff'}}>
                {success ? 'Verified!' : 'Quick Security Check'}
              </div>
              <div style={{fontSize:12,color:'rgba(255,255,255,.4)',marginTop:3}}>
                {success
                  ? 'Resuming your session…'
                  : isTotp
                    ? 'Enter the code from your authenticator app'
                    : 'Enter the code sent to your email'}
              </div>
            </div>
          </div>

          {!success && (<>
            {/* TOTP: ring + hint row */}
            {isTotp && (
              <div style={{
                display:'flex', alignItems:'center', gap:12,
                padding:'12px 14px',
                background:'rgba(99,102,241,0.07)',
                border:'1px solid rgba(99,102,241,0.15)',
                borderRadius:12, marginBottom:18,
              }}>
                <TotpRing size={52} />
                <div>
                  <div style={{fontSize:13,fontWeight:600,color:'rgba(255,255,255,.85)'}}>
                    Code refreshes every 30 seconds
                  </div>
                  <div style={{fontSize:12,color:'rgba(255,255,255,.35)',marginTop:3}}>
                    Open Google Authenticator or Authy and enter the current 6-digit code
                  </div>
                </div>
              </div>
            )}

            {/* Email OTP: dev hint + timer */}
            {!isTotp && (<>
              {devOtp && (
                <div style={{
                  padding:'9px 13px', marginBottom:14, textAlign:'center',
                  background:'rgba(234,179,8,0.07)',
                  border:'1px dashed rgba(234,179,8,0.3)', borderRadius:10,
                }}>
                  <span style={{fontSize:11,color:'#92400e',fontWeight:500}}>Dev code: </span>
                  <span style={{fontFamily:'monospace',fontSize:20,fontWeight:700,letterSpacing:'0.2em',color:'#fbbf24'}}>
                    {devOtp}
                  </span>
                </div>
              )}
              <div style={{
                display:'flex', justifyContent:'space-between', alignItems:'center',
                marginBottom:14, fontSize:12,
                color: emailTtl <= 30 ? '#f87171' : 'rgba(255,255,255,.35)',
              }}>
                <span style={{display:'flex',alignItems:'center',gap:5}}>
                  <Clock size={12} />
                  {emailTtl > 0 ? `Expires in ${fmt(emailTtl)}` : 'Code expired — request a new one'}
                </span>
                <button type="button" onClick={onCancel} style={{
                  background:'none',border:'none',cursor:'pointer',
                  color:'#6366f1',fontSize:12,display:'flex',alignItems:'center',gap:4,
                }}>
                  <RotateCcw size={11} /> Resend
                </button>
              </div>
            </>)}

            {/* 6-digit boxes */}
            <form onSubmit={e=>{e.preventDefault();submit(digits.join(''))}}>
              <div
                className={shake ? 'mfg-shake' : ''}
                style={{display:'flex',gap:8,justifyContent:'center',margin:'0 0 16px'}}
              >
                {digits.map((d,i) => (
                  <input
                    key={i}
                    ref={el=>inputRefs.current[i]=el}
                    className={`mfg-digit ${d?'filled':''} ${success?'ok':''}`}
                    type="text" inputMode="numeric" maxLength={1}
                    value={d}
                    onChange={e=>handleDigit(i,e.target.value)}
                    onKeyDown={e=>handleKey(i,e)}
                    onPaste={i===0?handlePaste:undefined}
                    disabled={loading}
                    autoComplete="one-time-code"
                  />
                ))}
              </div>

              {error && (
                <div style={{
                  fontSize:13,color:'#f87171',textAlign:'center',
                  padding:'8px 12px',marginBottom:12,
                  background:'rgba(239,68,68,.08)',borderRadius:8,
                }}>
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading || digits.join('').length < NUM}
                style={{
                  width:'100%', padding:13,
                  background:'linear-gradient(135deg,#6366f1,#4f46e5)',
                  border:'none', borderRadius:12,
                  color:'#fff', fontSize:14, fontWeight:600,
                  cursor:loading?'wait':'pointer',
                  display:'flex', alignItems:'center', justifyContent:'center', gap:8,
                  opacity:digits.join('').length<NUM?0.5:1,
                  transition:'opacity .2s',
                  boxShadow:'0 4px 15px rgba(99,102,241,.3)',
                }}
              >
                {loading
                  ? <><Spinner />Verifying…</>
                  : <><span>Verify</span><ArrowRight size={16}/></>
                }
              </button>

              <button
                type="button"
                onClick={onCancel}
                style={{
                  width:'100%', marginTop:10, padding:11,
                  background:'transparent', border:'1px solid rgba(255,255,255,.08)',
                  borderRadius:12, color:'rgba(255,255,255,.35)',
                  fontSize:13, cursor:'pointer',
                }}
              >
                Sign out instead
              </button>
            </form>
          </>)}
        </div>
      </div>
    </>
  );
}

function Spinner() {
  return (
    <span style={{
      width:15,height:15,
      border:'2px solid rgba(255,255,255,.25)',
      borderTopColor:'#fff', borderRadius:'50%',
      display:'inline-block',
      animation:'spin .7s linear infinite',
    }}/>
  );
}
