import { useState, useEffect } from 'react';
import { useAuth } from './AuthContext';
import { Shield, QrCode, Copy, Check, ArrowLeft } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

/**
 * MFA Enrollment Page — TOTP setup flow.
 *
 * Steps:
 *   1. Generate TOTP secret (GET QR code + secret + backup codes)
 *   2. User scans QR code with authenticator app
 *   3. User enters first valid TOTP code to confirm enrollment
 */
export default function MFAEnrollPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1=setup, 2=verify, 3=done
  const [enrollment, setEnrollment] = useState(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copiedSecret, setCopiedSecret] = useState(false);
  const [copiedBackup, setCopiedBackup] = useState(false);

  // Fetch enrollment on mount
  useEffect(() => {
    loadEnrollment();
  }, []);

  const loadEnrollment = async () => {
    setLoading(true);
    try {
      const { mfa } = await import('../api/client');
      const data = await mfa.enrollTotp();
      setEnrollment(data);
      if (data.already_enrolled) {
        setStep(3);
      }
    } catch (err) {
      setError('Failed to generate TOTP enrollment. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e) => {
    e.preventDefault();
    if (verifyCode.length < 6) {
      setError('Enter the 6-digit code from your authenticator app');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const { mfa } = await import('../api/client');
      await mfa.verifyTotp(verifyCode, `enroll_${user.identity_id}`, false);
      setStep(3);
    } catch (err) {
      setError(err.data?.detail || 'Invalid code. Make sure you scanned the QR code correctly.');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = async (text, setCopied) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  if (loading && !enrollment) {
    return (
      <div className="login-page">
        <div className="loading-center"><div className="loading-spinner" /></div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-card animate-fade-in" style={{ maxWidth: 480 }}>
        {/* Header */}
        <div className="login-logo">
          <div className="login-logo-icon" style={{ background: 'linear-gradient(135deg, #10b981, #059669)' }}>
            <Shield size={24} color="white" strokeWidth={1.5} />
          </div>
          <div className="login-logo-text">
            <h1 style={{ fontSize: '20px' }}>
              {step === 3 ? 'MFA Enabled ✓' : 'Set Up Two-Factor Authentication'}
            </h1>
            <span>{step === 3 ? 'Your account is now secured with TOTP' : 'Protect your account with an authenticator app'}</span>
          </div>
        </div>

        {/* Step 1: QR Code + Secret */}
        {step === 1 && enrollment && !enrollment.already_enrolled && (
          <>
            {/* QR Code area */}
            <div style={{
              background: 'white', borderRadius: '12px', padding: '20px',
              textAlign: 'center', marginBottom: '16px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 12 }}>
                <QrCode size={20} color="#333" />
                <span style={{ fontSize: '13px', color: '#333', fontWeight: 600 }}>
                  Scan with your authenticator app
                </span>
              </div>
              {/* QR code would be rendered here from provisioning_uri */}
              <div style={{
                background: '#f0f0f0', borderRadius: 8, padding: '40px 20px',
                fontFamily: 'monospace', fontSize: '10px', wordBreak: 'break-all',
                color: '#666',
              }}>
                {enrollment.provisioning_uri}
              </div>
            </div>

            {/* Manual entry secret */}
            <div style={{
              background: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              borderRadius: '10px', padding: '14px 16px', marginBottom: '16px',
            }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 6 }}>
                Or enter this secret manually:
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <code style={{
                  flex: 1, fontSize: '14px', letterSpacing: '0.1em',
                  fontWeight: 600, color: 'var(--text-primary)',
                }}>
                  {enrollment.secret}
                </code>
                <button
                  onClick={() => copyToClipboard(enrollment.secret, setCopiedSecret)}
                  style={{
                    background: 'transparent', border: 'none', cursor: 'pointer',
                    color: 'var(--text-muted)', padding: 4,
                  }}
                >
                  {copiedSecret ? <Check size={16} color="#10b981" /> : <Copy size={16} />}
                </button>
              </div>
            </div>

            {/* Backup codes */}
            {enrollment.backup_codes && (
              <div style={{
                background: 'rgba(245, 158, 11, 0.1)',
                border: '1px solid rgba(245, 158, 11, 0.3)',
                borderRadius: '10px', padding: '14px 16px', marginBottom: '20px',
              }}>
                <div style={{
                  fontSize: '13px', fontWeight: 600,
                  color: '#f59e0b', marginBottom: 8,
                }}>
                  ⚠️ Save Your Backup Codes
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: 10 }}>
                  These codes can be used if you lose access to your authenticator app.
                  Each code works once. Store them securely.
                </div>
                <div style={{
                  display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: 6, fontFamily: 'monospace', fontSize: '12px',
                }}>
                  {enrollment.backup_codes.map((code, i) => (
                    <div key={i} style={{
                      background: 'rgba(0,0,0,0.2)', padding: '4px 8px',
                      borderRadius: 4, textAlign: 'center', color: 'var(--text-primary)',
                    }}>
                      {code}
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => copyToClipboard(enrollment.backup_codes.join('\n'), setCopiedBackup)}
                  style={{
                    marginTop: 8, fontSize: '11px', background: 'transparent',
                    border: '1px solid var(--border)', borderRadius: 6,
                    padding: '4px 10px', cursor: 'pointer', color: 'var(--text-secondary)',
                  }}
                >
                  {copiedBackup ? '✓ Copied' : 'Copy all codes'}
                </button>
              </div>
            )}

            <button
              className="btn btn-primary"
              onClick={() => setStep(2)}
              style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
            >
              I've saved my backup codes — Continue →
            </button>
          </>
        )}

        {/* Step 2: Verify first code */}
        {step === 2 && (
          <form onSubmit={handleVerify}>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: 16, lineHeight: 1.6 }}>
              Enter the 6-digit code currently showing in your authenticator app
              to confirm enrollment.
            </p>
            <input
              className="input"
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={verifyCode}
              onChange={e => setVerifyCode(e.target.value.replace(/\D/g, ''))}
              placeholder="000000"
              autoComplete="one-time-code"
              style={{
                textAlign: 'center', fontSize: '24px', letterSpacing: '0.3em',
                fontFamily: 'monospace', padding: '14px', marginBottom: 16,
              }}
            />
            {error && <div className="login-error">{error}</div>}
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading}
              style={{ width: '100%', justifyContent: 'center', padding: '12px' }}
            >
              {loading ? 'Verifying…' : 'Verify & Enable MFA →'}
            </button>
            <button
              type="button"
              onClick={() => { setStep(1); setError(''); }}
              style={{
                width: '100%', marginTop: 10, padding: 10,
                background: 'transparent', border: '1px solid var(--border)',
                borderRadius: 8, color: 'var(--text-secondary)',
                cursor: 'pointer', fontSize: '13px',
              }}
            >
              <ArrowLeft size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              Back to QR code
            </button>
          </form>
        )}

        {/* Step 3: Success */}
        {step === 3 && (
          <div style={{ textAlign: 'center' }}>
            <div style={{
              width: 64, height: 64, borderRadius: '50%',
              background: 'rgba(16, 185, 129, 0.15)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px',
            }}>
              <Check size={32} color="#10b981" />
            </div>
            <p style={{ fontSize: '14px', color: 'var(--text-primary)', marginBottom: 8 }}>
              Two-factor authentication is active.
            </p>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: 24 }}>
              You'll be prompted for a code when the security system detects elevated risk.
            </p>
            <button
              className="btn btn-primary"
              onClick={() => navigate(-1)}
              style={{ padding: '10px 24px' }}
            >
              Done — Return to Dashboard
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
