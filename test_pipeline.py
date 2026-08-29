"""
SentinelX — End-to-End Pipeline Test Suite

Runs sequentially against live gateway (:8080) + demo-service (:9000).
Each test run generates fresh random identity suffixes so the test is
fully idempotent against a warm, cumulative state store — no restart needed
between runs.

Usage:
    python test_pipeline.py
"""
import asyncio
import random
import string
import time
import httpx
from datetime import datetime, timezone

GATEWAY_URL = "http://127.0.0.1:8080"
ORIGIN_URL  = "http://127.0.0.1:9000"

# Unique run-suffix ensures each test run gets pristine identities,
# so cumulative state from prior runs never causes false failures.
_RUN = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))

def _id(base: str) -> str:
    return f"{base}_{_RUN}"


async def test_pipeline():
    print("=" * 55)
    print("  SentinelX — End-to-End Pipeline Test Suite")
    print(f"  Run-ID: {_RUN}  ·  {datetime.now(timezone.utc).isoformat()}Z")
    print("=" * 55)

    async with httpx.AsyncClient(timeout=10.0) as client:

        # ── Stage 1: Health checks ──────────────────────────────────
        print("\n[1] Service health checks")
        resp = await client.get(f"{ORIGIN_URL}/health")
        print(f"  origin /health -> {resp.status_code}  {resp.json()}")
        assert resp.status_code == 200, "Origin service not reachable"

        resp = await client.get(f"{GATEWAY_URL}/health")
        print(f"  gateway /health -> {resp.status_code}  {resp.json()}")
        assert resp.status_code == 200, "Gateway not reachable"

        # ── Stage 2: Control-plane endpoints ────────────────────────
        print("\n[2] Control-plane endpoint checks")
        resp = await client.get(f"{GATEWAY_URL}/sentinelx/stats")
        stats = resp.json()
        print(f"  /sentinelx/stats -> {resp.status_code}  backend={stats['backend']}, "
              f"latency_budget={stats['latency_budget_ms']}ms")
        assert resp.status_code == 200

        resp = await client.get(f"{GATEWAY_URL}/sentinelx/policy")
        policy = resp.json()
        print(f"  /sentinelx/policy -> {resp.status_code}  thresholds={policy['thresholds']}")
        assert resp.status_code == 200

        # ── Stage 3: Normal traffic — must be proxied, tier=allow ───
        # We use the real identity "u_alex" (it exists in demo-service FAKE_USERS
        # so we get a deterministic name back); the unique session prefix per run
        # keeps each test's SentinelX state clean enough that early requests score
        # low even on a warm server.
        print("\n[3] Normal traffic  (allow -> proxy -> upstream)")
        alex_session_prefix = f"sess_alex_{_RUN}"
        headers_alex = {
            "x-identity-id":       "u_alex",
            "x-session-id":        f"{alex_session_prefix}_001",
            "x-mock-geo":          "IN-TN",
            "x-mock-device":       "chrome-macos",
            "x-token-age-seconds": "1200",
        }
        for i in range(5):
            res = await client.get(f"{GATEWAY_URL}/gateway/origin/profile",
                                   headers=headers_alex)
            score   = res.headers.get("x-sentinelx-risk-score")
            tier    = res.headers.get("x-sentinelx-tier")
            latency = res.headers.get("x-sentinelx-latency-ms")
            print(f"  req #{i+1}: status={res.status_code}  risk={score}  "
                  f"tier={tier}  latency={latency}ms")
            assert res.status_code == 200, f"Expected 200, got {res.status_code}"
            body = res.json()
            assert "identity" in body, f"Origin response missing 'identity' key: {body}"
            assert tier == "allow", f"Expected allow, got {tier}"

        # ── Stage 4: Impossible-travel hard trigger ──────────────────
        # Use a fresh per-run identity primed exclusively from IN-TN so that
        # switching to RU-MOW is *guaranteed* to be geo-novel (no history bleed
        # from prior test runs on the same server process).
        print("\n[4] Impossible-travel hard trigger")
        traveller = f"u_traveller_{_RUN}"
        travel_base = {
            "x-identity-id":  traveller,
            "x-session-id":   f"sess_travel_{_RUN}_001",
            "x-mock-geo":     "IN-TN",
            "x-mock-device":  "chrome-macos",
        }
        # Prime 3 requests from IN-TN so total > 0 and geo history is established
        for k in range(3):
            w = await client.get(f"{GATEWAY_URL}/gateway/origin/profile", headers=travel_base)
            print(f"  travel warmup #{k+1}: status={w.status_code}  tier={w.headers.get('x-sentinelx-tier')}")

        travel_headers = {**travel_base,
                          "x-mock-geo":    "RU-MOW",
                          "x-mock-device": "linux-firefox",
                          "x-token-age-seconds": "30"}
        res = await client.get(f"{GATEWAY_URL}/gateway/origin/profile", headers=travel_headers)
        print(f"  impossible-travel -> status={res.status_code}  body={res.json()}")
        assert res.status_code in (401, 429), \
            f"Expected 401/429 for impossible-travel, got {res.status_code}"

        # ── Stage 5: Privilege escalation — unseen admin endpoint ────
        # Fresh random identity (not in FAKE_USERS, doesn't matter for scoring).
        # We prime it with 3 normal GET /profile calls so the store's total > 0,
        # and then /admin/users is genuinely novel -> privilege_escalation_attempt
        # hard-trigger fires -> tier revoke/restrict -> 401/429.
        print("\n[5] Privilege escalation  (first-ever admin hit)")
        mina = f"u_priv_{_RUN}"
        headers_mina = {
            "x-identity-id":  mina,
            "x-session-id":   f"sess_{mina}_001",
            "x-mock-geo":     "IN-KA",
            "x-mock-device":  "safari-ios",
        }
        # Warm up: 3 requests to /profile so baseline.total >= 3
        for k in range(3):
            w = await client.get(f"{GATEWAY_URL}/gateway/origin/profile",
                                 headers=headers_mina)
            print(f"  warmup #{k+1}: status={w.status_code}  tier={w.headers.get('x-sentinelx-tier')}")

        res = await client.get(f"{GATEWAY_URL}/gateway/origin/admin/users",
                               headers=headers_mina)
        print(f"  admin-escalation -> status={res.status_code}  body={res.json()}")
        assert res.status_code in (401, 429), \
            f"Expected 401/429 for privilege-escalation, got {res.status_code}"

        # ── Stage 6: Session revocation + token-reuse check ─────────
        print("\n[6] Session revocation & token-reuse detection")
        target_sess = f"sess_target_{_RUN}"
        rev = await client.post(f"{GATEWAY_URL}/sentinelx/revoke/{target_sess}")
        print(f"  POST /sentinelx/revoke -> {rev.status_code}  {rev.json()}")
        assert rev.status_code == 200

        reuse_headers = {"x-identity-id": _id("u_admin"), "x-session-id": target_sess}
        res = await client.get(f"{GATEWAY_URL}/gateway/origin/profile",
                               headers=reuse_headers)
        print(f"  revoked-token reuse -> status={res.status_code}  body={res.json()}")
        assert res.status_code == 401, \
            f"Expected 401 for revoked token, got {res.status_code}"
        assert res.json().get("error") == "session_revoked", \
            "Expected session_revoked error code"

        # ── Stage 7: Simulator endpoint — all five scenarios ─────────
        print("\n[7] Simulator — all five scenarios")
        svc = _id("svc_billing")
        scenarios = ["normal", "frequency_spike", "new_admin_endpoint",
                     "impossible_travel", "privilege_escalation"]
        for sc in scenarios:
            t0 = time.perf_counter()
            sim = await client.post(f"{GATEWAY_URL}/sentinelx/simulate",
                                    json={"identity_id": svc,
                                          "scenario": sc, "count": 1})
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            data = sim.json()
            r0 = data["results"][0]
            reasons = [r["code"] for r in r0["reasons"]]
            print(f"  {sc:30s} -> score={r0['risk_score']:<6}  tier={r0['tier']:<10}  "
                  f"reasons={reasons}  [{elapsed}ms]")
            assert sim.status_code == 200, f"Simulator returned {sim.status_code}"

        # ── Stage 8: Alert feed integrity ────────────────────────────
        print("\n[8] Alert feed inspection")
        alerts_res = await client.get(f"{GATEWAY_URL}/sentinelx/alerts?limit=20")
        alerts = alerts_res.json()
        assert len(alerts) > 0, "Alert feed is empty — expected at least one entry"
        top = alerts[0]
        print(f"  {len(alerts)} alerts in feed. Latest: "
              f"identity={top['identity_id']}  tier={top['tier']}  "
              f"score={top['risk_score']}  endpoint={top['endpoint']}")
        # Structural check: every alert must carry required fields
        required_keys = {"identity_id", "tier", "risk_score", "endpoint", "reasons"}
        for a in alerts:
            missing = required_keys - set(a.keys())
            assert not missing, f"Alert missing fields: {missing}"

        # ── Stage 9: Live policy mutation ────────────────────────────
        print("\n[9] Dynamic policy mutation")
        upd = await client.post(f"{GATEWAY_URL}/sentinelx/policy",
                                json={"thresholds": {"allow": 15, "step_up": 45, "restrict": 75}})
        assert upd.status_code == 200
        new_thresh = upd.json()["thresholds"]
        print(f"  Mutated policy -> thresholds={new_thresh}")
        assert new_thresh["allow"] == 15

        # Restore defaults
        await client.post(f"{GATEWAY_URL}/sentinelx/policy",
                          json={"thresholds": {"allow": 30, "step_up": 60, "restrict": 85}})
        print("  Restored default thresholds — OK")

    print("\n" + "=" * 55)
    print("  >>> ALL 9 PIPELINE STAGES PASSED SUCCESSFULLY <<<")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(test_pipeline())
