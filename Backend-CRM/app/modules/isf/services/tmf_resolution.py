"""
TMF hierarchy resolution - find or create Zone, Section, Artifact, SubArtifact in MongoDB.
Mirrors Node.js behavior in isfReference.routes (findOneAndUpdate with upsert).
MongoDB collection names match Mongoose: zones, sections, artifacts, subartifacts.
"""
import logging
from typing import Optional, Tuple

from bson import ObjectId
from pymongo import ReturnDocument

logger = logging.getLogger(__name__)

ZONES_COLLECTION = "zones"
SECTIONS_COLLECTION = "sections"
ARTIFACTS_COLLECTION = "artifacts"
SUBARTIFACTS_COLLECTION = "subartifacts"


async def ensure_zone(db, zone_number: int, zone_name: str) -> ObjectId:
    """Find or create Zone by zoneNumber. Returns _id."""
    try:
        zone_number = int(zone_number)
    except (TypeError, ValueError):
        zone_number = 0
    zone_name = (zone_name or "Unknown").strip() or "Unknown"
    result = await db[ZONES_COLLECTION].find_one_and_update(
        {"zoneNumber": zone_number},
        {"$setOnInsert": {"zoneName": zone_name, "isActive": True}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return result["_id"] if result else (await db[ZONES_COLLECTION].insert_one({"zoneNumber": zone_number, "zoneName": zone_name, "isActive": True})).inserted_id


def _section_number_variants(section_number: str):
    """Canonical zero-padded string ("05.04") plus every representation stored in the DB.

    Seeded reference data stores sectionNumber as zero-padded strings, but older
    code inserted floats/ints — matching all forms prevents duplicate sections.
    Returns (canonical, variants).
    """
    raw = (section_number or "00.00").strip() or "00.00"
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


async def ensure_section(db, section_number: str, section_name: str, zone_id: ObjectId) -> ObjectId:
    """Find or create Section by sectionNumber and zone. Returns _id."""
    canonical, variants = _section_number_variants(section_number)
    section_name = (section_name or "Unknown").strip() or "Unknown"
    existing = await db[SECTIONS_COLLECTION].find_one({"sectionNumber": {"$in": variants}, "zone": zone_id})
    if existing:
        return existing["_id"]
    return (await db[SECTIONS_COLLECTION].insert_one(
        {"sectionNumber": canonical, "sectionName": section_name, "zone": zone_id, "isRequired": True, "isActive": True}
    )).inserted_id


async def ensure_artifact(db, artifact_number: str, artifact_name: str, section_id: ObjectId) -> ObjectId:
    """Find or create Artifact by artifactNumber and section. Returns _id."""
    artifact_number = (artifact_number or "00.00.00").strip() or "00.00.00"
    artifact_name = (artifact_name or "Unknown").strip() or "Unknown"
    result = await db[ARTIFACTS_COLLECTION].find_one_and_update(
        {"artifactNumber": artifact_number, "section": section_id},
        {"$setOnInsert": {"artifactName": artifact_name, "isRequired": True, "isActive": True}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if result:
        return result["_id"]
    return (await db[ARTIFACTS_COLLECTION].insert_one(
        {"artifactNumber": artifact_number, "artifactName": artifact_name, "section": section_id, "isRequired": True, "isActive": True}
    )).inserted_id


async def ensure_sub_artifact(db, sub_artifact_name: str, artifact_id: ObjectId) -> ObjectId:
    """Find or create SubArtifact by subArtifactName and artifact. Returns _id."""
    sub_artifact_name = (sub_artifact_name or "").strip()
    if not sub_artifact_name:
        raise ValueError("sub_artifact_name required")
    result = await db[SUBARTIFACTS_COLLECTION].find_one_and_update(
        {"subArtifactName": sub_artifact_name, "artifact": artifact_id},
        {"$setOnInsert": {"isRequired": True, "isActive": True}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if result:
        return result["_id"]
    return (await db[SUBARTIFACTS_COLLECTION].insert_one(
        {"subArtifactName": sub_artifact_name, "artifact": artifact_id, "isRequired": True, "isActive": True}
    )).inserted_id


async def resolve_tmf_from_metadata(
    db,
    zone_number,
    zone_name: str,
    section_number: str,
    section_name: str,
    artifact_number: str,
    artifact_name: str,
    sub_artifact_name: Optional[str] = None,
) -> Tuple[ObjectId, ObjectId, ObjectId, Optional[ObjectId]]:
    """
    Resolve TMF hierarchy from metadata (like Node.js). Returns (zone_id, section_id, artifact_id, sub_artifact_id).
    sub_artifact_id is None if sub_artifact_name is empty.
    """
    zone_id = await ensure_zone(db, int(zone_number) if zone_number is not None else 0, zone_name or "Unknown")
    section_id = await ensure_section(db, section_number or "00.00", section_name or "Unknown", zone_id)
    artifact_id = await ensure_artifact(db, artifact_number or "00.00.00", artifact_name or "Unknown", section_id)
    sub_artifact_id = None
    if sub_artifact_name and str(sub_artifact_name).strip():
        sub_artifact_id = await ensure_sub_artifact(db, str(sub_artifact_name).strip(), artifact_id)
    return zone_id, section_id, artifact_id, sub_artifact_id


def tmf_from_classification(classification: dict) -> dict:
    """
    Map Gemini classification result to TMF metadata keys (zoneNumber, zoneName, sectionNumber, etc.).
    suggestedZone: { id, number, name }, suggestedSection: string, suggestedArtifact: string, suggestedSubartifact: string.
    """
    zone = classification.get("suggestedZone") or {}
    zone_num = zone.get("number") or zone.get("id") or "0"
    try:
        zone_number = int(zone_num)
    except (TypeError, ValueError):
        zone_number = 0
    section_str = classification.get("suggestedSection") or "00.00"
    if isinstance(section_str, dict):
        section_str = section_str.get("number") or section_str.get("id") or "00.00"
    artifact_str = classification.get("suggestedArtifact") or "00.00.00"
    if isinstance(artifact_str, dict):
        artifact_str = artifact_str.get("number") or artifact_str.get("id") or "00.00.00"
    sub_str = classification.get("suggestedSubartifact") or ""
    if isinstance(sub_str, dict):
        sub_str = sub_str.get("name") or sub_str.get("id") or ""
    return {
        "zoneNumber": zone_number,
        "zoneName": (zone.get("name") or "Unknown").strip(),
        "sectionNumber": str(section_str).strip() or "00.00",
        "sectionName": str(section_str).strip() or "Unknown",
        "artifactNumber": str(artifact_str).strip() or "00.00.00",
        "artifactName": str(artifact_str).strip() or "Unknown",
        "subArtifactName": str(sub_str).strip() if sub_str else "",
    }
