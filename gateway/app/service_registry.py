"""
Service registry loader — reads services.json and provides a clean API
for the gateway to look up upstream URLs and endpoint sensitivity tiers
without any per-service hardcoding.

This is what makes SentinelX a template: new services are onboarded by
editing services.json alone. No gateway code changes required.
"""
from __future__ import annotations
import json
import os
from functools import lru_cache
from typing import Optional

_SERVICES_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "services.json")


@lru_cache(maxsize=1)
def _load_registry() -> dict:
    path = os.path.abspath(_SERVICES_JSON_PATH)
    with open(path, "r") as f:
        return json.load(f)["services"]


def get_service_config(service: str) -> Optional[dict]:
    """Return the full config block for a service, or None if unknown."""
    return _load_registry().get(service)


def get_upstream_url(service: str) -> Optional[str]:
    """
    Return the correct upstream base URL for the given service name.
    Prefers docker_base_url when SENTINELX_ENVIRONMENT=docker-compose,
    falls back to base_url for local dev.
    """
    cfg = get_service_config(service)
    if not cfg:
        return None
    is_docker = os.environ.get("SENTINELX_ENVIRONMENT", "") == "docker-compose"
    return cfg["docker_base_url"] if is_docker else cfg["base_url"]


def get_endpoint_sensitivity(service: str, path: str, method: str = "GET") -> str:
    """
    Return the sensitivity tier for an endpoint path within a service.
    Matching rules (in order):
      1. Exact match on the path
      2. Prefix match (longest prefix wins)
      3. Default: 'normal'
    """
    cfg = get_service_config(service)
    if not cfg:
        return "normal"

    endpoints: dict = cfg.get("endpoints", {})
    normalized = f"/{path.lstrip('/')}"
    
    def _extract_sensitivity(ep_cfg: dict) -> str:
        methods = ep_cfg.get("methods", {})
        if method in methods:
            return methods[method].get("sensitivity", ep_cfg.get("sensitivity", "normal"))
        return ep_cfg.get("sensitivity", "normal")

    # Exact match
    if normalized in endpoints:
        return _extract_sensitivity(endpoints[normalized])

    # Longest-prefix match
    best_match = ""
    for ep_path in endpoints:
        if normalized.startswith(ep_path) and len(ep_path) > len(best_match):
            best_match = ep_path

    if best_match:
        return _extract_sensitivity(endpoints[best_match])

    return "normal"


def is_auth_required(service: str, path: str, method: str = "GET") -> bool:
    """
    Returns False for pre-auth endpoints (e.g. /signup, /login) that
    should bypass identity-based scoring.
    """
    cfg = get_service_config(service)
    if not cfg:
        return True

    endpoints: dict = cfg.get("endpoints", {})
    normalized = f"/{path.lstrip('/')}"
    
    def _extract_auth(ep_cfg: dict) -> bool:
        methods = ep_cfg.get("methods", {})
        if method in methods:
            return methods[method].get("auth_required", ep_cfg.get("auth_required", True))
        return ep_cfg.get("auth_required", True)

    if normalized in endpoints:
        return _extract_auth(endpoints[normalized])

    # Longest prefix
    best_match = ""
    for ep_path in endpoints:
        if normalized.startswith(ep_path) and len(ep_path) > len(best_match):
            best_match = ep_path

    if best_match:
        return _extract_auth(endpoints[best_match])

    return True


def list_services() -> list[dict]:
    """Return summary info for all registered services."""
    registry = _load_registry()
    return [
        {"name": name, "description": cfg.get("description", ""), "endpoint_count": len(cfg.get("endpoints", {}))}
        for name, cfg in registry.items()
    ]
