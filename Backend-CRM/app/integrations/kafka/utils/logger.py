"""
Port of ``utils/logger.js``.

The reference uses pino child loggers keyed by module name. The Python analogue
is a stdlib ``logging`` logger namespaced per module, so log lines carry the same
``module`` identity the Node code attached.
"""
from __future__ import annotations

import logging


def create_module_logger(module: str) -> logging.Logger:
    """Return a logger named ``kafka.<module>`` (mirrors pino ``logger.child({module}))``."""
    return logging.getLogger(f"kafka.{module}")
