"""Job B STEP 3 — orphan attachment-file reconciler.

Uses a real temp upload_dir (tmp_path) and the local Mongo `attachments`
collection (test DB) for the referenced-file lookup. `asyncio_mode = auto`.
"""
import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import app.modules.communications.services.attachment_cleanup as cleanup_mod
from app.config import settings

TEST_DB = "crm_jobb_test"


@pytest.fixture
async def env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=3000)
    db = client[TEST_DB]
    await db["attachments"].delete_many({})
    async def _get():
        return db
    monkeypatch.setattr(cleanup_mod, "get_mongo_db", _get)
    yield db, tmp_path
    await db["attachments"].delete_many({})
    client.close()


async def _ref_row(db, name):
    await db["attachments"].insert_one(
        {"id": str(uuid.uuid4()), "file_path": f"uploads/{name}"})


async def test_dry_run_lists_but_does_not_delete(env, monkeypatch):
    db, tmp = env
    (tmp / "ref.pdf").write_text("x")
    (tmp / "orphan.pdf").write_text("y")
    await _ref_row(db, "ref.pdf")

    report = await cleanup_mod.reconcile_orphan_attachment_files(dry_run=True)
    assert "orphan.pdf" in report["orphans"]
    assert "orphan.pdf" in report["would_delete"]
    assert report["deleted"] == []
    assert (tmp / "orphan.pdf").exists() and (tmp / "ref.pdf").exists()


async def test_deletes_orphan_keeps_referenced(env, monkeypatch):
    db, tmp = env
    (tmp / "ref.pdf").write_text("x")
    (tmp / "orphan.pdf").write_text("y")
    await _ref_row(db, "ref.pdf")

    report = await cleanup_mod.reconcile_orphan_attachment_files(dry_run=False)
    assert "orphan.pdf" in report["deleted"]
    assert not (tmp / "orphan.pdf").exists()
    assert (tmp / "ref.pdf").exists()  # referenced file kept


async def test_missing_referenced_file_tolerated(env, monkeypatch):
    db, tmp = env
    # A referenced row whose file is already gone → not an orphan, no crash.
    await _ref_row(db, "ghost.pdf")
    (tmp / "orphan.pdf").write_text("y")
    report = await cleanup_mod.reconcile_orphan_attachment_files(dry_run=False)
    assert "orphan.pdf" in report["deleted"]
    assert "ghost.pdf" not in report["orphans"]   # missing referenced file ignored, no error
    assert not (tmp / "orphan.pdf").exists()
