"""Logging utilities for the job verifier application."""

import logging
from typing import Optional

_LOGGING_CONFIGURED = False


def configure_logging(level: int = logging.INFO, formatter: Optional[str] = None) -> None:
    """Ensure logging is configured once for the process."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    config = {"level": level}
    if formatter:
        config["format"] = formatter
    else:
        config["format"] = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(**config)
    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger bound to the global logging configuration."""
    configure_logging()
    return logging.getLogger(name)
