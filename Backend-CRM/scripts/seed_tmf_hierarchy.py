"""
Seed TMF reference hierarchy into MongoDB from the JSON exports in the repo DB/ folder.

Clears zones, sections, artifacts, and subartifacts, then reloads from the JSON exports.

Collections: zones, sections, artifacts, subartifacts

Usage (from Backend-CRM/):
    python -m scripts.seed_tmf_hierarchy

Optional env:
    TMF_SEED_DIR  — path to folder containing new_neurdoc.*.json files
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from bson import ObjectId
from bson.json_util import object_hook

# Allow running as `python -m scripts.seed_tmf_hierarchy` from Backend-CRM/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.mongo import get_mongo_db, close_mongo_client
from app.modules.isf.services.tmf_resolution import (
    ARTIFACTS_COLLECTION,
    SECTIONS_COLLECTION,
    SUBARTIFACTS_COLLECTION,
    ZONES_COLLECTION,
)


def _repo_db_dir() -> Path:
    custom = os.environ.get("TMF_SEED_DIR")
    if custom:
        return Path(custom)
    # Backend-CRM/scripts -> repo root -> DB/
    return Path(__file__).resolve().parents[2] / "DB"


def _load_extended_json(filename: str) -> List[Dict[str, Any]]:
    path = _repo_db_dir() / filename
    if not path.exists():
        raise FileNotFoundError(f"TMF seed file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh, object_hook=object_hook)
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON array in {path}")
    return raw


async def _clear_collections(db) -> None:
    """Remove all documents from the four TMF reference collections."""
    collections = [
        (SUBARTIFACTS_COLLECTION, "subartifacts"),
        (ARTIFACTS_COLLECTION, "artifacts"),
        (SECTIONS_COLLECTION, "sections"),
        (ZONES_COLLECTION, "zones"),
    ]
    for name, label in collections:
        result = await db[name].delete_many({})
        print(f"[TMF SEED] Cleared {label}: deleted {result.deleted_count} document(s)")


async def seed_tmf_hierarchy() -> None:
    db = await get_mongo_db()
    db_dir = _repo_db_dir()
    print(f"[TMF SEED] Loading from {db_dir}")

    zones = _load_extended_json("new_neurdoc.zones.json")
    sections = _load_extended_json("new_neurdoc.sections.json")
    artifacts = _load_extended_json("new_neurdoc.artifacts.json")
    subartifacts = _load_extended_json("new_neurdoc.subartifacts.json")

    await _clear_collections(db)

    zone_coll = db[ZONES_COLLECTION]
    section_coll = db[SECTIONS_COLLECTION]
    artifact_coll = db[ARTIFACTS_COLLECTION]
    sub_coll = db[SUBARTIFACTS_COLLECTION]

    zone_docs = []
    for doc in zones:
        oid = doc.get("_id")
        if not isinstance(oid, ObjectId):
            continue
        zone_docs.append(doc)
    if zone_docs:
        await zone_coll.insert_many(zone_docs)

    section_docs = []
    for doc in sections:
        oid = doc.get("_id")
        if not isinstance(oid, ObjectId):
            continue
        section_docs.append(doc)
    if section_docs:
        await section_coll.insert_many(section_docs)

    artifact_docs = []
    for doc in artifacts:
        oid = doc.get("_id")
        if not isinstance(oid, ObjectId):
            continue
        artifact_docs.append(doc)
    if artifact_docs:
        await artifact_coll.insert_many(artifact_docs)

    sub_docs = []
    for doc in subartifacts:
        oid = doc.get("_id")
        if not isinstance(oid, ObjectId):
            continue
        sub_docs.append(doc)
    if sub_docs:
        await sub_coll.insert_many(sub_docs)

    print(
        f"[TMF SEED] Done — zones={len(zone_docs)}, sections={len(section_docs)}, "
        f"artifacts={len(artifact_docs)}, subartifacts={len(sub_docs)}"
    )


async def _main() -> None:
    try:
        await seed_tmf_hierarchy()
    finally:
        await close_mongo_client()


if __name__ == "__main__":
    asyncio.run(_main())
