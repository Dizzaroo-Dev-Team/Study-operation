"""
Placeholder for ``utils/policyEvaluationCache.js``.

The reference (Neurodoc) app keeps an in-process policy-evaluation cache and the
entity handlers invalidate it after each write. That cache is NOT part of this
bundle and this app has no policy-evaluation engine yet, so these are no-ops.

The call sites in the event handlers are kept 1:1 with the reference so that,
when a policy engine is added here, its cache invalidation can be wired in one
place without touching the handlers.
"""
from __future__ import annotations


def invalidate_expanded_subject_cache_for_user(user_id: str) -> None:  # noqa: D401
    """No-op (no policy-evaluation cache in this app)."""
    return None


def invalidate_policy_evaluation_caches() -> None:  # noqa: D401
    """No-op (no policy-evaluation cache in this app)."""
    return None
