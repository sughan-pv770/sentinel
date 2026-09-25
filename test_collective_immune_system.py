import pytest
import hashlib
import httpx
import asyncio
import os
import sys

# Add gateway to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "gateway"))
from app.main import app


@pytest.mark.asyncio
async def test_collective_threat_signal_lifecycle():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        # 1. Clear any old signals
        res = await client.post("/sentinelx/threat-signals/clear")
        assert res.status_code == 200

        # 2. Get initial risk for u_alex on benign endpoint /profile (should be benign / low)
        res = await client.post(
            "/sentinelx/simulate",
            json={"identity_id": "u_alex", "scenario": "custom", "endpoint": "/profile", "method": "GET", "count": 1}
        )
        assert res.status_code == 200
        data = res.json()
        initial_score = data["results"][0]["risk_score"]
        assert initial_score <= 30, f"Initial risk score should be benign, got {initial_score}"

        # 3. Simulate peer gateway (Gateway Alpha - Nexus ERP) revoking u_alex
        sim_res = await client.post(
            "/sentinelx/threat-signals/simulate-peer",
            json={
                "identity_id": "u_alex",
                "peer_gateway_id": "gateway-nexus-erp",
                "peer_gateway_name": "Gateway Alpha (Nexus ERP)",
                "verdict_tier": "REVOKE",
                "reason_category": "credential_stuffing_detected"
            }
        )
        assert sim_res.status_code == 200
        sim_data = sim_res.json()
        assert sim_data["status"] == "published"
        expected_hash = hashlib.sha256("u_alex".encode("utf-8")).hexdigest()
        assert sim_data["identity_hash"] == expected_hash

        # 4. Check threat signal listing
        signals_res = await client.get("/sentinelx/threat-signals")
        assert signals_res.status_code == 200
        signals = signals_res.json().get("signals", [])
        assert len(signals) >= 1
        assert signals[0]["identity_hash"] == expected_hash
        assert signals[0]["verdict_tier"] == "REVOKE"

        # 5. Check threat mesh stats
        stats_res = await client.get("/sentinelx/threat-mesh/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["mesh_status"] == "SYNCHRONIZED"
        assert stats["active_threat_signals"] >= 1

        # 6. Now Alex Rao sends a normal benign request to SentinelX (/profile)
        # SentinelX checks the collective mesh, finds the hash match, and elevates Alex's score!
        eval_res = await client.post(
            "/sentinelx/simulate",
            json={"identity_id": "u_alex", "scenario": "custom", "endpoint": "/profile", "method": "GET", "count": 1}
        )
        assert eval_res.status_code == 200
        eval_data = eval_res.json()
        eval_decision = eval_data["results"][0]

        elevated_score = eval_decision["risk_score"]
        assert elevated_score >= 45, f"Expected risk score to be elevated to >= 45, got {elevated_score}"
        
        # Check reasons include collective_immune_threat_match
        reason_codes = [r.get("code") if isinstance(r, dict) else r for r in eval_decision.get("reasons", [])]
        assert "collective_immune_threat_match" in reason_codes, f"Expected collective_immune_threat_match in {reason_codes}"

        print("\n[OK] Collective Immune System Test PASSED!")
        print(f"  - Initial Alex Score: {initial_score}")
        print(f"  - Post-Peer Signal Alex Score: {elevated_score} (Tier: {eval_decision['tier']})")
        print(f"  - Triggered Reason: {eval_decision['reasons'][0]['message']}")


if __name__ == "__main__":
    asyncio.run(test_collective_threat_signal_lifecycle())
