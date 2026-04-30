import logging
import json
from typing import Any, Dict, Optional
from datetime import datetime


class StructuredLogger:
    """Structured logging with JSON output for Elasticsearch/CloudWatch"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(message)s',
            datefmt='%Y-%m-%dT%H:%M:%SZ'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def info(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log info with structured context"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "INFO",
            "message": message,
            **(context or {}),
        }
        self.logger.info(json.dumps(log_entry))

    def error(
        self,
        message: str,
        error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log error with exception details"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "ERROR",
            "message": message,
            **(context or {}),
        }
        if error:
            log_entry["exception"] = str(error)
            log_entry["exception_type"] = type(error).__name__
        self.logger.error(json.dumps(log_entry))


def get_logger(name: str) -> StructuredLogger:
    """Get structured logger instance"""
    return StructuredLogger(name)
