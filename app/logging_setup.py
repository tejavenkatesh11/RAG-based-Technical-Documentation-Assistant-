"""Structured logging setup.

Single configuration point so the LangGraph pipeline can emit traceable, parseable
events for every node transition and external call.
"""
from __future__ import annotations

import logging
import sys

from app.config import settings


_FMT = "%(asctime)s %(levelname)-7s %(name)-22s | %(message)s"
_DATEFMT = "%H:%M:%S"
_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # Quiet noisy libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
