"""CTA (Clinical Trial Agreement) type sub-module — table models only.

As of 2026-06-18 the legacy CTA *workflow* (routes, service, status hooks,
descriptor) was retired: the CTA signing/review flow now runs on the general
workflow engine. What remains here is ``models.py`` — the ``CTAAssignment``,
``CTAPlaceholderMapping`` and ``AgreementNegotiationRound`` SQLAlchemy models,
whose tables are still in use (the reviewer/sponsor-head assignment inbox reads
``cta_assignments`` via ``app.modules.agreements.routes.assignments``).

This ``__init__`` is intentionally minimal — it must remain safe to import
during SQLAlchemy model loading, because ``app/models/agreement.py`` re-imports
:class:`AgreementNegotiationRound` from ``.models``. Do NOT add imports here.
"""
