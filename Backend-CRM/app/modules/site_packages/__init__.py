"""
Site Packages module (FastAPI).

Adds endpoints under /api/site-packages/* by mounting this module's router.
"""

from .routes import router  # noqa: F401

