"""
Port of ``utils/iamConfig.js``.

Application-id and attribute-allowlist resolution helpers used by the routing
guard and the event handlers. Reads the same env vars as the reference; in this
app they are surfaced through ``app.config.settings`` (which maps the Data
Platform contract names DATA_PLATFORM_APP_ID / SUBJECT_ROLE_KEY / … 1:1).
"""
from __future__ import annotations

from app.config import settings


def _pick_string(*candidates) -> str:
    for c in candidates:
        if c is not None and str(c).strip() != "":
            return str(c).strip()
    return ""


def parse_csv_env(raw) -> list[str]:
    return [s.strip().lower() for s in str(raw or "").split(",") if s.strip()]


def resolve_default_app_id() -> str:
    """Primary application id (DATA_PLATFORM_APP_ID). '' when unset."""
    return _pick_string(settings.data_platform_app_id)


def get_application_id_aliases() -> set[str]:
    """Set containing DATA_PLATFORM_APP_ID when configured; empty otherwise."""
    configured = _pick_string(settings.data_platform_app_id).lower()
    expected: set[str] = set()
    if configured:
        expected.add(configured)
    return expected


def resolve_subject_role_key() -> str:
    """Subject role attribute key used in policy conditions (SUBJECT_ROLE_KEY)."""
    return _pick_string(settings.subject_role_key)


def resolve_subject_access_key() -> str:
    """Subject access-list key (SUBJECT_ACCESS_KEY)."""
    return _pick_string(settings.subject_access_key)


def get_allowed_app_attribute_names(default_names: list[str] | None = None) -> set[str]:
    configured = parse_csv_env(getattr(settings, "iam_app_attribute_names", None))
    if configured:
        return set(configured)
    return {str(n).lower() for n in (default_names or [])}
