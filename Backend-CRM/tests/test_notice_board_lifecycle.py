"""Regression tests for the notice-board lifecycle hardening.

Layer 1 (auto-heal in /conversations route) and Layer 3 (eager-create in
`get_or_create_study_site`) must both make the notice board impossible to
silently lose. These tests lock the call-pattern so a future refactor
can't quietly remove the safety nets.

NOTE: Like the other backend tests in this repo on Python 3.13, this
file will fail at COLLECTION if SQLAlchemy < 2.0.30 is pinned (the
`TypingOnly` mixin breaks on `__static_attributes__`). Bump SQLAlchemy
in requirements.txt to run.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.clinical_workflow.services import study_site_service


# ─── Layer 3: get_or_create_study_site eagerly creates the notice board ──

@pytest.mark.asyncio
async def test_eager_create_on_existing_mapping():
    """Calling get_or_create_study_site for an already-existing mapping
    must STILL trigger `_ensure_notice_board_for`. Legacy mappings may
    not have a board yet; the hook heals them lazily on first hit."""
    study_id = uuid4()
    site_id = uuid4()
    existing_mapping = SimpleNamespace(id=uuid4(), study_id=study_id, site_id=site_id)

    fake_result = SimpleNamespace(scalar_one_or_none=lambda: existing_mapping)
    db = SimpleNamespace(execute=AsyncMock(return_value=fake_result))

    with patch.object(
        study_site_service, "_ensure_notice_board_for", new=AsyncMock(),
    ) as mock_ensure:
        result = await study_site_service.get_or_create_study_site(db, study_id, site_id)

    assert result is existing_mapping
    mock_ensure.assert_awaited_once_with(study_id, site_id)


@pytest.mark.asyncio
async def test_eager_create_on_new_mapping():
    """Brand-new (study, site) mapping path must also trigger the hook."""
    study_id = uuid4()
    site_id = uuid4()

    # First select returns None, then add+flush+refresh succeed.
    fake_select_result = SimpleNamespace(scalar_one_or_none=lambda: None)
    db = SimpleNamespace(
        execute=AsyncMock(return_value=fake_select_result),
        add=lambda obj: None,
        flush=AsyncMock(),
        refresh=AsyncMock(),
    )

    with patch.object(
        study_site_service, "_ensure_notice_board_for", new=AsyncMock(),
    ) as mock_ensure:
        result = await study_site_service.get_or_create_study_site(db, study_id, site_id)

    assert result.study_id == study_id
    assert result.site_id == site_id
    mock_ensure.assert_awaited_once_with(study_id, site_id)


@pytest.mark.asyncio
async def test_ensure_notice_board_swallows_repo_failures():
    """The hook is best-effort: if the repository raises, we log and
    return — we must NEVER block a get_or_create_study_site call on a
    transient Mongo hiccup. The inbox-open path is the second guarantee."""
    study_id = uuid4()
    site_id = uuid4()

    with patch(
        "app.modules.communications.repositories.ConversationRepository."
        "find_or_create_pinned_notice_board",
        new=AsyncMock(side_effect=RuntimeError("mongo down")),
    ):
        # Must NOT raise.
        await study_site_service._ensure_notice_board_for(study_id, site_id)


# ─── Layer 3: race-recovery path also triggers the hook ─────────────────

@pytest.mark.asyncio
async def test_eager_create_on_race_recovery():
    """If a concurrent request created the mapping between our select and
    insert (IntegrityError → re-select), the race-winner path must still
    fire the notice-board hook."""
    study_id = uuid4()
    site_id = uuid4()
    race_winner_mapping = SimpleNamespace(id=uuid4(), study_id=study_id, site_id=site_id)

    # First select: None (no existing mapping). Second select (after race):
    # returns the mapping the other request created.
    initial_result = SimpleNamespace(scalar_one_or_none=lambda: None)
    recovery_result = SimpleNamespace(scalar_one_or_none=lambda: race_winner_mapping)

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=[initial_result, recovery_result]),
        add=lambda obj: None,
        flush=AsyncMock(side_effect=Exception("duplicate key value violates unique constraint uq_study_site")),
        refresh=AsyncMock(),
        rollback=AsyncMock(),
    )

    with patch.object(
        study_site_service, "_ensure_notice_board_for", new=AsyncMock(),
    ) as mock_ensure:
        result = await study_site_service.get_or_create_study_site(db, study_id, site_id)

    assert result is race_winner_mapping
    mock_ensure.assert_awaited_once_with(study_id, site_id)
