"""Regression test: `ConversationRepository.list` must push sort + skip +
limit to MongoDB.

The legacy fetch-all-then-sort-in-Python path was unbounded (band-aided
by a 5000-doc cap) and depended on a string-mess `is_pinned` field. The
new path uses a compound index `conversations_type_then_recent_idx` and
sorts by `conversation_type` (notice_board < thread alphabetically →
notice board pins to top naturally).

This test locks the cursor call shape so a future refactor can't quietly
re-introduce the Python sort.
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo import ASCENDING, DESCENDING

from app.modules.communications.repositories.mongo import ConversationRepository


class _FakeCursor:
    """Records the chained `.sort/.skip/.limit` calls so the test can
    assert the exact spec the repo sent to Mongo."""

    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs
        self.sort_call: tuple | None = None
        self.skip_call: int | None = None
        self.limit_call: int | None = None

    def sort(self, spec):
        self.sort_call = tuple(spec)
        return self

    def skip(self, n):
        self.skip_call = n
        return self

    def limit(self, n):
        self.limit_call = n
        return self

    async def to_list(self, length=None):
        return self._docs


@pytest.fixture
def fake_collection_and_cursor():
    docs = [
        {"id": "nb-1", "conversation_type": "notice_board", "title": "Public Notice Board"},
        {"id": "t-1", "conversation_type": "thread", "title": "Thread A"},
    ]
    cursor = _FakeCursor(docs)
    collection = MagicMock()
    collection.find = MagicMock(return_value=cursor)
    return collection, cursor


@pytest.mark.asyncio
async def test_list_pushes_sort_skip_limit_to_mongo(fake_collection_and_cursor):
    collection, cursor = fake_collection_and_cursor

    fake_db = {ConversationRepository.COLLECTION_NAME: collection}

    with patch(
        "app.modules.communications.repositories.mongo.get_mongo_db",
        new=AsyncMock(return_value=fake_db),
    ):
        result = await ConversationRepository.list(
            limit=25,
            offset=50,
            study_id="study-x",
            site_id="site-y",
        )

    # Exact sort spec: conversation_type ASC (notice_board < thread →
    # notice board comes first), then created_at DESC (newest first).
    assert cursor.sort_call == (
        ("conversation_type", ASCENDING),
        ("created_at", DESCENDING),
    ), f"Sort spec drifted from notice-board-first contract: {cursor.sort_call}"

    # Pagination is at the DB layer, not in Python.
    assert cursor.skip_call == 50
    assert cursor.limit_call == 25

    # Two docs back, in the order the cursor produced.
    assert [d["id"] for d in result] == ["nb-1", "t-1"]


@pytest.mark.asyncio
async def test_list_query_includes_notice_board_and_thread_types(fake_collection_and_cursor):
    """The repo must include BOTH notice_board and thread types — otherwise
    user-created threads disappear from the inbox (regression that already
    bit the team once)."""
    collection, _cursor = fake_collection_and_cursor
    fake_db = {ConversationRepository.COLLECTION_NAME: collection}

    with patch(
        "app.modules.communications.repositories.mongo.get_mongo_db",
        new=AsyncMock(return_value=fake_db),
    ):
        await ConversationRepository.list(
            limit=10,
            offset=0,
            study_id="study-x",
            site_id="site-y",
        )

    # The query passed to collection.find(...) is the first positional arg.
    query = collection.find.call_args.args[0]
    assert query["conversation_type"] == {"$in": ["notice_board", "thread"]}
    assert query["site_id"] == "site-y"
    assert query["study_id"] == "study-x"


@pytest.mark.asyncio
async def test_list_without_study_id_filters_site_level_only(fake_collection_and_cursor):
    """When `study_id` is omitted, the query must restrict to docs that have
    no study_id (or where the field doesn't exist) — keeps study-specific
    boards out of the site-level inbox."""
    collection, _cursor = fake_collection_and_cursor
    fake_db = {ConversationRepository.COLLECTION_NAME: collection}

    with patch(
        "app.modules.communications.repositories.mongo.get_mongo_db",
        new=AsyncMock(return_value=fake_db),
    ):
        await ConversationRepository.list(limit=10, offset=0, site_id="site-y")

    query = collection.find.call_args.args[0]
    assert "study_id" not in query  # not pinned to a specific study
    assert query["$or"] == [{"study_id": None}, {"study_id": {"$exists": False}}]
