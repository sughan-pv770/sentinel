"""
Structured JSON logging (§4.6 / §5 "Observability" -- feeds the
explainability layer and could feed a SOC dashboard / SIEM via a log sink).
"""
from __future__ import annotations
import logging
import json
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)  # type: ignore[attr-defined]
        return json.dumps(payload)


def get_logger(name: str = "sentinelx") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_decision(logger: logging.Logger, decision_dict: dict):
    record = logger.makeRecord(
        logger.name, logging.INFO, __file__, 0,
        f"decision tier={decision_dict.get('tier')} score={decision_dict.get('risk_score')}",
        (), None,
    )
    record.extra_fields = decision_dict  # type: ignore[attr-defined]
    logger.handle(record)
