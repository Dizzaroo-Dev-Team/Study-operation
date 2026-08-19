"""Agreement type registry.

Each agreement type (CDA, CTA, future BUDGET/NDA/...) registers itself here so
the shared agreements infrastructure can:

* mount the type's router with safe-import semantics — if one type's module
  fails to import (syntax error, missing dep), the others still mount;
* dispatch type-specific hooks (on_create, on_status_change, ...) without the
  shared services having to know about every type at compile time.

Adding a new agreement type:
1. Create app/modules/agreements/types/<code_lower>/ with routes.py, service.py,
   schemas.py, models.py (optional), __init__.py.
2. The type's __init__.py must expose a module-level ``descriptor`` of type
   :class:`AgreementTypeDescriptor`.
3. Add an import for it at the bottom of this file (see CDA/CTA below). That's
   it — no changes to shared routes or services required.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)


@dataclass
class AgreementTypeDescriptor:
    """Describes a single agreement type and the hooks the shared layer can call."""

    code: str
    label: str
    router: Optional[APIRouter] = None
    on_create: Optional[Callable] = None
    on_status_change: Optional[Callable] = None
    allowed_transitions: Dict[str, List[str]] = field(default_factory=dict)


_registry: Dict[str, AgreementTypeDescriptor] = {}


def register(descriptor: AgreementTypeDescriptor) -> None:
    code = descriptor.code.upper()
    if code in _registry:
        logger.warning("AgreementType %s already registered — overwriting", code)
    _registry[code] = descriptor


def get(code: str) -> Optional[AgreementTypeDescriptor]:
    return _registry.get(code.upper()) if code else None


def all_descriptors() -> List[AgreementTypeDescriptor]:
    return list(_registry.values())


def safe_import_type(module_path: str) -> Optional[AgreementTypeDescriptor]:
    """Import a type sub-package, returning its descriptor or None on failure.

    If the import fails (syntax error, missing dependency, broken sub-module),
    we log loudly and return None. The caller — typically the aggregator —
    skips mounting the type's router but continues with the remaining types,
    so one broken type cannot take down the whole Agreements module.
    """
    try:
        mod = importlib.import_module(module_path)
    except Exception:  # noqa: BLE001 — broad on purpose: we never want one type to kill the app
        logger.exception("Failed to import agreement type module %s — type will be unavailable", module_path)
        return None

    descriptor = getattr(mod, "descriptor", None)
    if descriptor is None:
        logger.error("Module %s has no `descriptor` attribute — type will be unavailable", module_path)
        return None
    if not isinstance(descriptor, AgreementTypeDescriptor):
        logger.error("Module %s `descriptor` is not an AgreementTypeDescriptor — type will be unavailable", module_path)
        return None

    register(descriptor)
    return descriptor


# Registered type descriptor modules. Add new types here.
#
# IMPORTANT: point at a descriptor sub-module — never the package __init__ —
# because the package __init__ must stay safe to import during SQLAlchemy model
# loading. Descriptor modules pull in routes/, which transitively imports
# app.models, and can only be safely loaded once the model graph is done.
# Empty since 2026-06-18: the legacy CDA/CTA type modules were retired (both
# signing flows now run on the general workflow engine). Add a descriptor
# sub-module path here only if a future type genuinely needs registry-mounted
# routes + status hooks.
TYPE_MODULES: List[str] = []


def load_all_types() -> List[AgreementTypeDescriptor]:
    """Import every registered type sub-module via safe_import_type."""
    loaded: List[AgreementTypeDescriptor] = []
    for mod_path in TYPE_MODULES:
        descriptor = safe_import_type(mod_path)
        if descriptor is not None:
            loaded.append(descriptor)
    return loaded
