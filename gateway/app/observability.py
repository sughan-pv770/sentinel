"""
OpenTelemetry + Prometheus observability setup.

Metrics exposed at GET /metrics (Prometheus text format).

Custom metrics:
  sentinelx_requests_total        — counter, labels: tier, endpoint_group
  sentinelx_request_latency_ms    — histogram (ms)
  sentinelx_ml_inference_latency_ms — histogram (ms)
  sentinelx_ml_circuit_state      — gauge (0=CLOSED, 1=HALF_OPEN, 2=OPEN)
  sentinelx_active_sse_connections — gauge
  sentinelx_mfa_verifications_total — counter, labels: method, result
  sentinelx_rate_limit_hits_total — counter, labels: key_type
  sentinelx_sessions_revoked_total — counter, labels: triggered_by
"""
from __future__ import annotations
from prometheus_client import Counter, Histogram, Gauge, REGISTRY, make_asgi_app
from app.utils.logger import get_logger

logger = get_logger("sentinelx.observability")

# ── Counters ───────────────────────────────────────────────────────────────────

requests_total = Counter(
    "sentinelx_requests_total",
    "Total gateway requests processed",
    ["tier", "endpoint_group"],
)

mfa_verifications_total = Counter(
    "sentinelx_mfa_verifications_total",
    "MFA verification attempts",
    ["method", "result"],  # result: success | failure | expired
)

rate_limit_hits_total = Counter(
    "sentinelx_rate_limit_hits_total",
    "Rate limit exceeded events",
    ["key_type"],  # identity | ip
)

sessions_revoked_total = Counter(
    "sentinelx_sessions_revoked_total",
    "Total sessions forcibly revoked",
    ["triggered_by"],  # ml_engine | rule_engine | admin_manual
)

# ── Histograms ─────────────────────────────────────────────────────────────────

request_latency_ms = Histogram(
    "sentinelx_request_latency_ms",
    "End-to-end gateway request latency in milliseconds",
    buckets=[1, 5, 10, 15, 25, 50, 100, 200, 500, 1000],
)

ml_inference_latency_ms = Histogram(
    "sentinelx_ml_inference_latency_ms",
    "ML engine scoring latency in milliseconds",
    buckets=[0.5, 1, 2, 5, 10, 20, 50, 100],
)

# ── Gauges ─────────────────────────────────────────────────────────────────────

active_sse_connections = Gauge(
    "sentinelx_active_sse_connections",
    "Number of active SSE connections",
)

ml_circuit_state = Gauge(
    "sentinelx_ml_circuit_state",
    "ML circuit breaker state: 0=CLOSED, 1=HALF_OPEN, 2=OPEN",
)


def _endpoint_group(path: str) -> str:
    """Bucket raw endpoint paths into labeled groups for cardinality control."""
    if path.startswith("/admin"):
        return "admin"
    if path.startswith("/payments"):
        return "payments"
    if path.startswith("/gateway"):
        return "gateway"
    if path.startswith("/api/auth"):
        return "auth"
    if path.startswith("/api/dashboard"):
        return "dashboard"
    if path.startswith("/api/mfa"):
        return "mfa"
    if path.startswith("/api/events"):
        return "sse"
    if path.startswith("/sentinelx"):
        return "control_plane"
    if path in ("/health", "/metrics", "/"):
        return "infra"
    return "other"


def get_metrics_app():
    """Return a Prometheus ASGI metrics app for mounting at /metrics."""
    return make_asgi_app()
