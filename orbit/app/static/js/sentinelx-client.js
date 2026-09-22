/**
 * SentinelX Client Library v1.0
 * ==============================
 * Drop-in Zero Trust enforcement client for any SaaS frontend.
 *
 * Usage:
 *   1. Include this script in your HTML.
 *   2. Create a client: const sx = new SentinelXClient({ gatewayBase, identityId, sessionId });
 *   3. Use sx.call(endpoint, method, body) instead of raw fetch.
 *   4. Register handlers: sx.onStepUp(cb), sx.onRestrict(cb), sx.onRevoke(cb).
 *
 * See SENTINELX_INTEGRATION_GUIDE.md for full onboarding docs.
 */

class SentinelXClient {
    constructor({ gatewayBase, identityId, sessionId, spoofGeo = null, spoofDevice = null }) {
        this.gatewayBase = gatewayBase.replace(/\/$/, '');
        this.identityId = identityId;
        this.sessionId = sessionId;
        this.spoofGeo = spoofGeo;
        this.spoofDevice = spoofDevice;
        this._nonceBase = Date.now();
        this._pendingChallenge = null;  // { challenge_id, demo_otp }
        this._handlers = { stepUp: null, restrict: null, revoke: null };
    }

    /** Register a callback for STEP-UP (401 step_up_required) enforcement. */
    onStepUp(cb) { this._handlers.stepUp = cb; return this; }

    /** Register a callback for RESTRICT (429 restricted) enforcement. */
    onRestrict(cb) { this._handlers.restrict = cb; return this; }

    /** Register a callback for REVOKE (401 session_revoked) enforcement. */
    onRevoke(cb) { this._handlers.revoke = cb; return this; }

    _buildHeaders() {
        this._nonceBase++;
        const h = {
            'Content-Type': 'application/json',
            'x-identity-id': this.identityId,
            'x-session-id': this.sessionId,
            'x-nonce': `n_${this._nonceBase}_${Math.random().toString(36).slice(2)}`,
        };
        if (this.spoofGeo)    h['x-mock-geo']    = this.spoofGeo;
        if (this.spoofDevice) h['x-mock-device'] = this.spoofDevice;
        return h;
    }

    /**
     * Make an authenticated API call through the SentinelX gateway.
     * Automatically handles enforcement signals (step-up, restrict, revoke).
     * Returns { ok: bool, data: object, status: number } or null on network error.
     */
    async call(endpoint, method = 'GET', body = null) {
        const url = `${this.gatewayBase}${endpoint}`;
        try {
            const hasBody = body && !['GET', 'HEAD'].includes(method.toUpperCase());
            const reqHeaders = this._buildHeaders();
            if (body && body.dev_test) {
                reqHeaders['x-demo-burst'] = 'true';
            }
            const res = await fetch(url, {
                method,
                headers: reqHeaders,
                body: hasBody ? JSON.stringify(body) : null,
            });
            const data = await res.json();

            if (!res.ok) {
                this._handleEnforcement(res.status, data);
            }

            const headers = {
                riskScore: res.headers.get('x-sentinelx-risk-score'),
                tier: res.headers.get('x-sentinelx-tier'),
                latencyMs: res.headers.get('x-sentinelx-latency-ms')
            };

            return { ok: res.ok, data, status: res.status, headers };
        } catch (e) {
            console.error('[SentinelX] Network error:', e);
            return null;
        }
    }

    _handleEnforcement(status, data) {
        if (status === 401 && data.error === 'step_up_required') {
            this._pendingChallenge = data.challenge || null;
            if (this._handlers.stepUp) this._handlers.stepUp(data);
            return;
        }
        if (status === 429 && data.error === 'restricted') {
            if (this._handlers.restrict) this._handlers.restrict(data);
            return;
        }
        if (status === 401 && data.error === 'session_revoked') {
            if (this._handlers.revoke) this._handlers.revoke(data);
            return;
        }
    }

    /**
     * Verify an OTP against the SentinelX control plane.
     * Returns 'ok', 'expired', 'wrong', or 'used'.
     */
    async verifyOtp(code) {
        if (!this._pendingChallenge) return 'wrong';
        const challenge_id = this._pendingChallenge.challenge_id;
        try {
            const res = await fetch(
                this.gatewayBase.replace('/gateway/orbit', '').replace('/gateway/stub-service', '') + '/sentinelx/verify_otp',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ challenge_id, code: String(code) }),
                }
            );
            const data = await res.json();
            if (data.result === 'ok') this._pendingChallenge = null;
            return data.result;
        } catch (e) {
            console.error('[SentinelX] OTP verify error:', e);
            return 'wrong';
        }
    }

    getPendingChallenge() { return this._pendingChallenge; }
}

// UMD export so this works in both browser and Node (for tests)
if (typeof module !== 'undefined') module.exports = { SentinelXClient };
