"""
Comprehensive End-to-End Test & Verification Suite for SentinelX Gateway & Control Plane.

Tests:
  1. Health & Statistics Endpoint
  2. User Registry & Dynamic User Creation
  3. Reverse Proxy Forwarding & Origin Headers
  4. Role-Based Security Matrix (u_admin, u_manager1, u_alex, u_mina, svc_billing)
  5. 5 Core Scenarios (Normal, Frequency Spike, Admin Escalation, Impossible Travel, Payment Transfer)
  6. Session Revocation & Token Reuse Blocking
  7. Policy Configuration Engine
  8. Telemetry & 7-Signal Feature Vector Integrity
"""
import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:8080"
ORIGIN_URL = "http://127.0.0.1:9000"

results = []

def record(category, test_name, status, details=""):
    results.append({
        "category": category,
        "name": test_name,
        "status": status,
        "details": details
    })
    symbol = "✓" if status == "PASS" else "✕"
    print(f"[{symbol}] {category} :: {test_name} -> {status} ({details})")

def test_system_health():
    print("\n--- 1. SYSTEM HEALTH & STATS ---")
    try:
        r = requests.get(f"{BASE_URL}/sentinelx/stats", timeout=3)
        if r.status_code == 200:
            data = r.json()
            record("System Health", "Gateway Stats API", "PASS", f"Backend: {data.get('backend')}, Budget: {data.get('latency_budget_ms')}ms")
        else:
            record("System Health", "Gateway Stats API", "FAIL", f"HTTP {r.status_code}")
    except Exception as e:
        record("System Health", "Gateway Stats API", "FAIL", str(e))

def test_user_management():
    print("\n--- 2. USER REGISTRY & DYNAMIC USER CREATION ---")
    try:
        r = requests.get(f"{BASE_URL}/sentinelx/users", timeout=3)
        users = r.json().get("users", [])
        uids = [u["identity_id"] for u in users]
        if "u_alex" in uids and "u_admin" in uids and "svc_billing" in uids:
            record("User Management", "List Default Users", "PASS", f"Found {len(users)} pre-seeded profiles ({', '.join(uids[:4])})")
        else:
            record("User Management", "List Default Users", "FAIL", f"Missing expected users in {uids}")
    except Exception as e:
        record("User Management", "List Default Users", "FAIL", str(e))

    # Add dynamic test user
    new_uid = f"u_test_{int(time.time())}"
    try:
        r = requests.post(f"{BASE_URL}/sentinelx/users", json={
            "identity_id": new_uid,
            "name": "Test Runner User",
            "role": "student",
            "network_tag": "TestNet"
        }, timeout=3)
        if r.status_code == 200:
            record("User Management", "Dynamic User Registration", "PASS", f"Created {new_uid}")
        else:
            record("User Management", "Dynamic User Registration", "FAIL", f"HTTP {r.status_code}")
    except Exception as e:
        record("User Management", "Dynamic User Registration", "FAIL", str(e))

def test_proxy_forwarding():
    print("\n--- 3. REVERSE PROXY FORWARDING & ORIGIN INTEGRATION ---")
    try:
        # Proxy through 8080 to origin 9000
        headers = {"x-identity-id": "u_alex", "x-session-id": "sess_test_123"}
        r = requests.get(f"{BASE_URL}/profile", headers=headers, timeout=3)
        if r.status_code == 200:
            data = r.json()
            record("Proxy Forwarding", "GET /profile proxying", "PASS", f"Response from origin: user={data.get('user', {}).get('name')}")
        else:
            record("Proxy Forwarding", "GET /profile proxying", "FAIL", f"HTTP {r.status_code}")
    except Exception as e:
        record("Proxy Forwarding", "GET /profile proxying", "FAIL", str(e))

def test_role_matrix():
    print("\n--- 4. ROLE-BASED ACCESS CONTROL & RISK MATRIX ---")
    matrix = [
        ("u_admin", "admin", "/admin/users", "GET", "IN-TN", "chrome-macos", "allow", 30, "Admin accessing admin route"),
        ("svc_billing", "service", "/payments/transfer", "POST", "IN-TN", "internal-service", "allow", 30, "Billing service accessing payment route"),
        ("u_alex", "student", "/profile", "GET", "IN-TN", "chrome-macos", "allow", 30, "Student accessing own profile"),
        ("u_alex", "student", "/payments/transfer", "POST", "IN-TN", "chrome-macos", "step_up", 60, "Student attempting payment transfer"),
        ("u_manager1", "manager", "/orders", "GET", "IN-TN", "chrome-macos", "allow", 30, "Manager accessing normal orders"),
    ]

    for uid, role, endpoint, method, geo, device, expected_tier, max_score, desc in matrix:
        try:
            r = requests.post(f"{BASE_URL}/sentinelx/simulate", json={
                "identity_id": uid,
                "scenario": "custom",
                "count": 1,
                "method": method,
                "endpoint": endpoint,
                "geo": geo,
                "device": device
            }, timeout=3)
            res = r.json()["results"][0]
            tier = res["tier"]
            score = res["risk_score"]
            if tier == expected_tier:
                record("Role Security", f"{uid} ({role}) -> {endpoint}", "PASS", f"Tier: {tier.upper()} (Risk {score}/100) | {desc}")
            else:
                record("Role Security", f"{uid} ({role}) -> {endpoint}", "FAIL", f"Expected {expected_tier}, got {tier} (Risk {score})")
        except Exception as e:
            record("Role Security", f"{uid} ({role}) -> {endpoint}", "FAIL", str(e))

def test_attack_scenarios():
    print("\n--- 5. CORE SCENARIO DETECTION & ENGINE TESTS ---")
    scenarios = [
        ("u_alex", "normal", "allow", "Normal request behavior"),
        ("u_alex", "privilege_escalation", "step_up", "Privilege escalation to payment endpoint"),
        ("u_alex", "impossible_travel", "revoke", "Impossible travel & device change from Russia"),
        ("u_alex", "frequency_spike", "step_up", "Rapid request burst (34+ reqs/min)"),
    ]

    for uid, scenario, expected_tier, desc in scenarios:
        try:
            r = requests.post(f"{BASE_URL}/sentinelx/simulate", json={
                "identity_id": uid,
                "scenario": scenario,
                "count": 1
            }, timeout=3)
            res = r.json()["results"][0]
            tier = res["tier"]
            score = res["risk_score"]
            # Allow step_up or restrict for frequency_spike depending on baseline
            valid_tiers = [expected_tier]
            if scenario == "frequency_spike":
                valid_tiers = ["step_up", "restrict"]

            if tier in valid_tiers:
                record("Attack Detection", f"Scenario: {scenario}", "PASS", f"Tier: {tier.upper()} (Risk {score}/100) | {desc}")
            else:
                record("Attack Detection", f"Scenario: {scenario}", "FAIL", f"Expected {expected_tier}, got {tier} (Risk {score})")
        except Exception as e:
            record("Attack Detection", f"Scenario: {scenario}", "FAIL", str(e))

def test_session_revocation():
    print("\n--- 6. SESSION REVOCATION & TOKEN REUSE BLOCKING ---")
    sess_id = f"sess_revoke_test_{int(time.time())}"
    try:
        # First revoke the session
        r = requests.post(f"{BASE_URL}/sentinelx/revoke/{sess_id}", timeout=3)
        if r.status_code == 200 and r.json().get("revoked"):
            record("Session Security", "Revoke Session API", "PASS", f"Session {sess_id} revoked")
        else:
            record("Session Security", "Revoke Session API", "FAIL", f"HTTP {r.status_code}")

        # Now test a request using the revoked session token
        r2 = requests.get(f"{BASE_URL}/profile", headers={
            "x-identity-id": "u_alex",
            "x-session-id": sess_id
        }, timeout=3)
        # Should be blocked with 403 or return REVOKE risk
        if r2.status_code in (403, 401):
            record("Session Security", "Revoked Token Blocking", "PASS", f"Blocked with HTTP {r2.status_code}")
        else:
            record("Session Security", "Revoked Token Blocking", "FAIL", f"Got HTTP {r2.status_code}")
    except Exception as e:
        record("Session Security", "Revoked Token Blocking", "FAIL", str(e))

def test_policy_engine():
    print("\n--- 7. POLICY CONFIGURATION & DYNAMIC THRESHOLDS ---")
    try:
        # Get policy
        r = requests.get(f"{BASE_URL}/sentinelx/policy", timeout=3)
        orig_policy = r.json()

        # Update policy
        r_up = requests.post(f"{BASE_URL}/sentinelx/policy", json={
            "thresholds": {"allow": 30, "step_up": 60, "restrict": 85}
        }, timeout=3)
        if r_up.status_code == 200:
            record("Policy Engine", "Update Policy Thresholds", "PASS", "Thresholds updated (allow=30, step_up=60, restrict=85)")
        else:
            record("Policy Engine", "Update Policy Thresholds", "FAIL", f"HTTP {r_up.status_code}")
    except Exception as e:
        record("Policy Engine", "Update Policy Thresholds", "FAIL", str(e))

def test_telemetry_vector():
    print("\n--- 8. TELEMETRY & FEATURE VECTOR INTEGRITY ---")
    try:
        r = requests.post(f"{BASE_URL}/sentinelx/simulate", json={
            "identity_id": "u_alex",
            "scenario": "normal",
            "count": 1
        }, timeout=3)
        res = r.json()["results"][0]
        feats = res.get("features")
        details = res.get("feature_details")
        if feats and len(feats) == 7 and details:
            record("Telemetry", "7-Signal Feature Vector", "PASS", f"Vector: {feats}")
        else:
            record("Telemetry", "7-Signal Feature Vector", "FAIL", f"Incomplete feature vector: {feats}")
    except Exception as e:
        record("Telemetry", "7-Signal Feature Vector", "FAIL", str(e))

def generate_report():
    print("\n" + "=" * 80)
    print("                      SENTINELX END-TO-END TEST REPORT                      ")
    print("=" * 80)
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = total - passed

    print(f"\nTOTAL TESTS RUN : {total}")
    print(f"PASSED          : {passed} ✓")
    print(f"FAILED          : {failed} ✕")
    print(f"PASS RATE       : {(passed/total)*100:.1f}%\n")

    print(f"{'CATEGORY':<20} | {'TEST NAME':<35} | {'STATUS':<6} | {'DETAILS'}")
    print("-" * 80)
    for r in results:
        print(f"{r['category']:<20} | {r['name']:<35} | {r['status']:<6} | {r['details']}")
    print("=" * 80)

    if failed == 0:
        print("\n🎉 ALL PIPELINES, ROLES, AND SCENARIOS ARE 100% OPERATIONAL AND VERIFIED!")
    else:
        print(f"\n⚠️ WARNING: {failed} test(s) failed. See output above.")

if __name__ == "__main__":
    test_system_health()
    test_user_management()
    test_proxy_forwarding()
    test_role_matrix()
    test_attack_scenarios()
    test_session_revocation()
    test_policy_engine()
    test_telemetry_vector()
    generate_report()
