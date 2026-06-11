"""Safe logging configuration for Larpwing.

Logs request metadata without leaking API keys, message content,
or Authorization headers.
"""

from __future__ import annotations

import logging
import sys


def setup_logging() -> logging.Logger:
    """Configure and return the application logger.

    Logs at INFO level to stderr with a format suitable for
    request-level observability.
    """
    logger = logging.getLogger("larpwing")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    # Avoid duplicate handlers on reload
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


# Module-level convenience
log = setup_logging()
