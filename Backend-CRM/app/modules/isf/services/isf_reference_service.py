from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from bson import ObjectId

from ..services.tmf_resolution import (
    ARTIFACTS_COLLECTION,
    SECTIONS_COLLECTION,
    SUBARTIFACTS_COLLECTION,
    ZONES_COLLECTION,
)


def _normalize_zone_number(value: Any) -> str:
    try:
        return str(int(value)).zfill(2)
    except (TypeError, ValueError):
        return str(value or "").zfill(2)


def _normalize_section_number(value: Any) -> Optional[str]:
    if value is None:
        return None
    parts = str(value).split(".")
    if len(parts) < 2:
        return str(value)
    zone = parts[0].zfill(2)
    rest = ".".join(parts[1:])
    return f"{zone}.{rest}"


def _normalize_artifact_number(value: Any) -> Optional[str]:
    if value is None:
        return None
    parts = str(value).split(".")
    if len(parts) != 3:
        return str(value)
    return ".".join(part.zfill(2) for part in parts)


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _artifact_metadata_fields(artifact: Dict[str, Any], zone: Dict[str, Any], section: Dict[str, Any]) -> Dict[str, Any]:
    meta = artifact.get("metadata") or {}
    artifact_number = _normalize_artifact_number(artifact.get("artifactNumber"))
    section_number = _normalize_section_number(section.get("sectionNumber"))
    return {
        "definition": _clean_value(meta.get("definition")),
        "coreOrRecommended": _clean_value(meta.get("coreOrRecommended")),
        "ichCode": _clean_value(meta.get("ichCode") or artifact.get("ichCode")),
        "iso14155Reference": _clean_value(meta.get("iso14155Reference")),
        "uniqueIdNumber": _clean_value(meta.get("uniqueIdNumber")),
        "sponsorDocument": bool(meta.get("sponsorDocument")) if meta.get("sponsorDocument") is not None else None,
        "investigatorDocument": bool(meta.get("investigatorDocument")) if meta.get("investigatorDocument") is not None else None,
        "processNumber": _clean_value(meta.get("processNumber")),
        "processName": _clean_value(meta.get("processName")),
        "trialLevelDocument": bool(meta.get("trialLevelDocument")) if meta.get("trialLevelDocument") is not None else None,
        "trialLevelMilestone": _clean_value(meta.get("trialLevelMilestone")),
        "countryLevelDocument": bool(meta.get("countryLevelDocument")) if meta.get("countryLevelDocument") is not None else None,
        "countryLevelMilestone": _clean_value(meta.get("countryLevelMilestone")),
        "siteLevelDocument": bool(meta.get("siteLevelDocument")) if meta.get("siteLevelDocument") is not None else None,
        "siteLevelMilestone": _clean_value(meta.get("siteLevelMilestone")),
        "datingConvention": _clean_value(meta.get("datingConvention")),
        "artifactOwner": _clean_value(meta.get("artifactOwner")),
        "artifactLocation": _clean_value(meta.get("artifactLocation")),
        "wetInkSignature": _clean_value(meta.get("wetInkSignature")),
        "sopReference": _clean_value(meta.get("sopReference")),
        "translationRequired": _clean_value(meta.get("translationRequired")),
        "currentArtifactName": _clean_value(meta.get("currentArtifactName")),
        "additionalMetadata": _clean_value(meta.get("additionalMetadata")),
        "zoneNumber": zone.get("zoneNumber"),
        "zoneName": zone.get("zoneName"),
        "sectionNumber": section_number,
        "sectionName": section.get("sectionName"),
        "artifactNumber": artifact_number,
        "isfStatus": artifact.get("isfStatus"),
        "siteAction": artifact.get("siteAction"),
        "rationale": artifact.get("rationale"),
    }


class ISFReferenceService:
    async def get_zones(self, db) -> List[Dict[str, Any]]:
        zones = await db[ZONES_COLLECTION].find({"isActive": {"$ne": False}}).sort("zoneNumber", 1).to_list(length=None)
        return [
            {
                "id": str(zone["_id"]),
                "zone_number": zone.get("zoneNumber"),
                "zone_name": zone.get("zoneName"),
                "is_active": zone.get("isActive", True),
            }
            for zone in zones
        ]

    async def get_sections_by_zone(self, db, zone_id: str) -> List[Dict[str, Any]]:
        zone_oid = ObjectId(zone_id)
        sections = (
            await db[SECTIONS_COLLECTION]
            .find({"zone": zone_oid, "isActive": {"$ne": False}})
            .sort("sectionNumber", 1)
            .to_list(length=None)
        )
        return [
            {
                "id": str(section["_id"]),
                "section_number": section.get("sectionNumber"),
                "section_name": section.get("sectionName"),
                "zone_id": zone_id,
                "is_active": section.get("isActive", True),
            }
            for section in sections
        ]

    async def get_hierarchy(self, db) -> Dict[str, Any]:
        """
        Build the full 4-level TMF hierarchy from MongoDB reference collections.
        Returns hierarchyData (nested tree) and artifactSubartifacts (flat lookup).
        """
        zones = await db[ZONES_COLLECTION].find({"isActive": {"$ne": False}}).sort("zoneNumber", 1).to_list(length=None)
        sections = await db[SECTIONS_COLLECTION].find({"isActive": {"$ne": False}}).sort("sectionNumber", 1).to_list(length=None)
        artifacts = await db[ARTIFACTS_COLLECTION].find({"isActive": {"$ne": False}}).sort("artifactNumber", 1).to_list(length=None)
        subartifacts = await db[SUBARTIFACTS_COLLECTION].find({"isActive": {"$ne": False}}).sort("subArtifactName", 1).to_list(length=None)

        sections_by_zone: Dict[ObjectId, List[Dict[str, Any]]] = {}
        for section in sections:
            zone_id = section.get("zone")
            if zone_id:
                sections_by_zone.setdefault(zone_id, []).append(section)

        artifacts_by_section: Dict[ObjectId, List[Dict[str, Any]]] = {}
        for artifact in artifacts:
            section_id = artifact.get("section")
            if section_id:
                artifacts_by_section.setdefault(section_id, []).append(artifact)

        subartifacts_by_artifact: Dict[ObjectId, List[Dict[str, Any]]] = {}
        for sub in subartifacts:
            artifact_id = sub.get("artifact")
            if artifact_id:
                subartifacts_by_artifact.setdefault(artifact_id, []).append(sub)

        hierarchy_data: List[Dict[str, Any]] = []

        for zone in zones:
            zone_number = _normalize_zone_number(zone.get("zoneNumber"))
            zone_entry: Dict[str, Any] = {
                "Zone": {
                    "Number": zone_number,
                    "Name": zone.get("zoneName") or "",
                    "Id": str(zone["_id"]),
                },
                "Sections": [],
            }

            for section in sections_by_zone.get(zone["_id"], []):
                section_number = _normalize_section_number(section.get("sectionNumber"))
                section_entry: Dict[str, Any] = {
                    "Section": {
                        "Number": section_number,
                        "Name": section.get("sectionName") or "",
                        "Id": str(section["_id"]),
                    },
                    "Artifacts": [],
                }

                for artifact in artifacts_by_section.get(section["_id"], []):
                    artifact_number = _normalize_artifact_number(artifact.get("artifactNumber"))

                    artifact_entry = {
                        "Artifact": {
                            "Number": artifact_number,
                            "Name": artifact.get("artifactName") or "",
                            "Id": str(artifact["_id"]),
                            "isfStatus": artifact.get("isfStatus"),
                            "siteAction": artifact.get("siteAction"),
                            "rationale": artifact.get("rationale"),
                        },
                        "SubArtifacts": [
                            {"Name": sa.get("subArtifactName"), "Id": str(sa["_id"])}
                            for sa in subartifacts_by_artifact.get(artifact["_id"], [])
                            if sa.get("subArtifactName")
                        ],
                    }
                    section_entry["Artifacts"].append(artifact_entry)

                zone_entry["Sections"].append(section_entry)

            hierarchy_data.append(zone_entry)

        # Rebuild flat map with full metadata from DB artifacts (not just hierarchy shell)
        flat_map: Dict[str, Any] = {}
        for zone in zones:
            for section in sections_by_zone.get(zone["_id"], []):
                section_number = _normalize_section_number(section.get("sectionNumber"))
                section_name = section.get("sectionName") or ""
                artifact_names: List[str] = []
                section_artifacts: List[Dict[str, str]] = []

                for artifact in artifacts_by_section.get(section["_id"], []):
                    artifact_number = _normalize_artifact_number(artifact.get("artifactNumber"))
                    artifact_name = artifact.get("artifactName") or ""
                    if not artifact_number or not artifact_name:
                        continue

                    sub_names = [
                        sa.get("subArtifactName")
                        for sa in subartifacts_by_artifact.get(artifact["_id"], [])
                        if sa.get("subArtifactName")
                    ]
                    artifact_names.append(artifact_name)
                    section_artifacts.append({"number": artifact_number, "name": artifact_name})

                    meta = _artifact_metadata_fields(artifact, zone, section)
                    entry = {"name": artifact_name, "subartifacts": sub_names, **{k: v for k, v in meta.items() if v is not None}}
                    flat_map[artifact_number] = entry

                    parts = artifact_number.split(".")
                    if len(parts) == 3 and section_number:
                        non_padded_last = str(int(parts[2]))
                        non_padded_key = f"{section_number}.{non_padded_last}"
                        if non_padded_key != artifact_number:
                            flat_map[non_padded_key] = dict(entry)

                if section_number and section_name:
                    flat_map[section_number] = {
                        "name": section_name,
                        "subartifacts": artifact_names,
                        "artifacts": section_artifacts,
                    }

        return {
            "hierarchyData": hierarchy_data,
            "artifactSubartifacts": flat_map,
        }
