"""Repair orphaned TMF hierarchy references on isf_documents.

Why this exists
---------------
Each ISF document stores ObjectId refs to its zone/section/artifact. Those
reference records can disappear (reseeded/deleted zones), leaving documents
pointing at ids that no longer exist. The ISF Document Browser then renders
fallback folders like "Zone 69b241a095633163d4354...".

Documents also store a `tmfReference` string like "01.05.01" (zone 01,
section 01.05, artifact 01.05.01). This script uses it to re-link every
document with a missing/orphaned ref to the canonical record, creating the
section/artifact rows (named from the TMF reference model) when absent —
the same find-or-create-by-number behaviour as
app/modules/isf/services/tmf_resolution.py.

Idempotency: re-linking resolves to the same canonical ids, so re-running is
a no-op. Before writing, the previous refs of every touched document are
saved to scripts/repair_isf_tmf_refs_backup_<timestamp>.json.

Run (from Backend-CRM, same env as the API):

    python -m scripts.repair_isf_tmf_refs --dry-run   # report only
    python -m scripts.repair_isf_tmf_refs             # apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from bson import ObjectId
from pymongo import MongoClient, ReturnDocument

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = (
    BACKEND_ROOT.parent / "Frontend-CRM" / "src" / "modules" / "isf" / "data" / "tmf_reference_model.json"
)

TMF_REF_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{1,2})$")


def load_env_mongodb_uri() -> str:
    uri = os.environ.get("MONGODB_URI")
    if uri:
        return uri
    env_path = BACKEND_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MONGODB_URI="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("MONGODB_URI not set and not found in Backend-CRM/.env")


def load_reference_model(path: Path) -> Dict[str, Dict[str, str]]:
    """Return artifact_number -> {zone_name, section_name, artifact_name, zone_number}."""
    if not path.exists():
        print(f"WARNING: TMF reference model not found at {path}; names will fall back to 'Unknown'")
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = next(iter(raw.values())) if isinstance(raw, dict) else raw
    by_artifact: Dict[str, Dict[str, str]] = {}
    for row in rows:
        art_num = str(row.get("Artifact #") or "").strip()
        if not art_num:
            continue
        by_artifact[art_num] = {
            "zone_number": row.get("Zone #"),
            "zone_name": str(row.get("Zone Name") or "Unknown").strip(),
            "section_name": str(row.get("Section Name") or "Unknown").strip(),
            "artifact_name": str(row.get("Artifact name") or "Unknown").strip(),
        }
    return by_artifact


def section_number_variants(section_str: str):
    """Canonical zero-padded string ("05.04") plus every representation seen in the DB.

    Mirrors _section_number_variants() in tmf_resolution.py: seeded reference data
    stores strings, older code inserted floats/ints. Returns (canonical, variants).
    """
    raw = (section_str or "00.00").strip() or "00.00"
    variants = [raw]
    try:
        canonical = ".".join(f"{int(p):02d}" for p in raw.split("."))
    except (ValueError, TypeError):
        return raw, variants
    variants.append(canonical)
    try:
        variants.append(float(raw) if "." in raw else int(raw))
    except (ValueError, TypeError):
        pass
    return canonical, variants


def ensure_zone(db, zone_number: int, zone_name: str) -> ObjectId:
    doc = db.zones.find_one_and_update(
        {"zoneNumber": zone_number},
        {"$setOnInsert": {"zoneName": zone_name, "isActive": True}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["_id"]


def ensure_section(db, section_str: str, section_name: str, zone_id: ObjectId) -> ObjectId:
    canonical, variants = section_number_variants(section_str)
    existing = db.sections.find_one({"sectionNumber": {"$in": variants}, "zone": zone_id})
    if existing:
        return existing["_id"]
    return db.sections.insert_one(
        {"sectionNumber": canonical, "sectionName": section_name, "zone": zone_id, "isRequired": True, "isActive": True}
    ).inserted_id


def merge_duplicate_sections(db, dry_run: bool) -> int:
    """Merge numeric-numbered section duplicates into their canonical string twin.

    For each zone, sections whose sectionNumber is a float/int and that have a
    string-numbered counterpart ("5.04" vs "05.04") are merged: artifacts and
    isf_documents pointing at the numeric one are re-pointed, then it is deleted.
    """
    merged = 0
    by_key: Dict[tuple, Dict[str, Any]] = {}
    numeric: list = []
    for s in db.sections.find({}):
        try:
            key = (str(s.get("zone")), f'{float(s.get("sectionNumber")):05.2f}')
        except (TypeError, ValueError):
            continue
        if isinstance(s.get("sectionNumber"), str):
            by_key[key] = s
        else:
            numeric.append((key, s))
    for key, dupe in numeric:
        keep = by_key.get(key)
        if not keep:
            continue
        print(f"  MERGE section {dupe['_id']} ({dupe.get('sectionNumber')!r}) -> {keep['_id']} ({keep.get('sectionNumber')!r})")
        if not dry_run:
            for art in db.artifacts.find({"section": dupe["_id"]}):
                twin = db.artifacts.find_one(
                    {"section": keep["_id"], "artifactNumber": art.get("artifactNumber"), "_id": {"$ne": art["_id"]}}
                )
                if twin:
                    # Same artifact number already exists under the kept section — collapse into it.
                    db.isf_documents.update_many({"artifact": art["_id"]}, {"$set": {"artifact": twin["_id"]}})
                    db.subartifacts.update_many({"artifact": art["_id"]}, {"$set": {"artifact": twin["_id"]}})
                    db.artifacts.delete_one({"_id": art["_id"]})
                else:
                    db.artifacts.update_one({"_id": art["_id"]}, {"$set": {"section": keep["_id"]}})
            db.isf_documents.update_many({"section": dupe["_id"]}, {"$set": {"section": keep["_id"]}})
            db.sections.delete_one({"_id": dupe["_id"]})
        merged += 1
    return merged


def ensure_artifact(db, artifact_number: str, artifact_name: str, section_id: ObjectId) -> ObjectId:
    doc = db.artifacts.find_one_and_update(
        {"artifactNumber": artifact_number, "section": section_id},
        {"$setOnInsert": {"artifactName": artifact_name, "isRequired": True, "isActive": True}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["_id"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing")
    parser.add_argument("--db-name", default="crm_db")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Path to tmf_reference_model.json")
    args = parser.parse_args()

    client = MongoClient(load_env_mongodb_uri())
    db = client[args.db_name]
    model = load_reference_model(args.model)

    zone_ids = {z["_id"] for z in db.zones.find({}, {"_id": 1})}
    section_ids = {s["_id"] for s in db.sections.find({}, {"_id": 1})}
    artifact_ids = {a["_id"] for a in db.artifacts.find({}, {"_id": 1})}

    backup: Dict[str, Dict[str, Any]] = {}
    fixed = skipped_ok = skipped_no_ref = 0

    for doc in db.isf_documents.find({}, {"zone": 1, "section": 1, "artifact": 1, "tmfReference": 1, "title": 1}):
        zone_ok = doc.get("zone") in zone_ids
        section_ok = doc.get("section") in section_ids
        artifact_ok = doc.get("artifact") in artifact_ids
        if zone_ok and section_ok and artifact_ok:
            skipped_ok += 1
            continue

        m = TMF_REF_RE.match(str(doc.get("tmfReference") or "").strip())
        if not m:
            skipped_no_ref += 1
            print(f"  SKIP {doc['_id']} ({doc.get('title')!r}): unparsable tmfReference={doc.get('tmfReference')!r}")
            continue

        zone_part, section_part, _ = m.groups()
        artifact_number = m.group(0)
        section_str = f"{zone_part}.{section_part}"
        zone_number = int(zone_part)
        names = model.get(artifact_number, {})

        print(
            f"  FIX  {doc['_id']} ({doc.get('title')!r}) tmfReference={artifact_number} "
            f"[zone_ok={zone_ok} section_ok={section_ok} artifact_ok={artifact_ok}]"
        )
        if args.dry_run:
            fixed += 1
            continue

        zid = ensure_zone(db, zone_number, names.get("zone_name", "Unknown"))
        sid = ensure_section(db, section_str, names.get("section_name", "Unknown"), zid)
        aid = ensure_artifact(db, artifact_number, names.get("artifact_name", "Unknown"), sid)

        backup[str(doc["_id"])] = {
            "zone": str(doc.get("zone")),
            "section": str(doc.get("section")),
            "artifact": str(doc.get("artifact")),
            "tmfReference": doc.get("tmfReference"),
        }
        db.isf_documents.update_one({"_id": doc["_id"]}, {"$set": {"zone": zid, "section": sid, "artifact": aid}})
        fixed += 1

    if backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = Path(__file__).with_name(f"repair_isf_tmf_refs_backup_{stamp}.json")
        backup_path.write_text(json.dumps(backup, indent=2), encoding="utf-8")
        print(f"\nPrevious refs of updated documents saved to {backup_path}")

    print("\nMerging duplicate sections (numeric vs string sectionNumber):")
    merged = merge_duplicate_sections(db, args.dry_run)

    mode = "DRY RUN — would fix" if args.dry_run else "fixed"
    print(
        f"\nDone: {mode} {fixed}; already consistent {skipped_ok}; "
        f"unparsable tmfReference {skipped_no_ref}; duplicate sections merged {merged}"
    )


if __name__ == "__main__":
    main()
