from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from ..core.database import get_database
from ..services.isf_document_service import ISFDocumentService
from ..utils.auth import get_current_active_user


router = APIRouter()


ZONES_COLLECTION = "zones"
SECTIONS_COLLECTION = "sections"
ARTIFACTS_COLLECTION = "artifacts"
SUBARTIFACTS_COLLECTION = "subartifacts"
ISF_DOCUMENTS_COLLECTION = "isf_documents"


FolderType = Literal["zone", "section", "artifact", "subartifact"]


class ISFFolderNode(BaseModel):
    folder_id: str
    folder_type: FolderType
    folder_name: str
    folder_number: Optional[str] = None
    document_count: int = 0
    subfolders: List["ISFFolderNode"] = Field(default_factory=list)


ISFFolderNode.model_rebuild()


class ISFDocumentListItem(BaseModel):
    id: str
    title: str
    mime_type: Optional[str] = None
    file_url: Optional[str] = None
    file_size: Optional[int] = None
    modification_date: Optional[datetime] = None
    version: Optional[Union[int, float, str]] = None


class ISFImportRequest(BaseModel):
    document_ids: List[str] = Field(default_factory=list)


class ISFImportItem(BaseModel):
    id: str
    title: str
    mime_type: Optional[str] = None
    url: str


class ISFImportResponse(BaseModel):
    documents: List[ISFImportItem] = Field(default_factory=list)


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(str(value))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid ObjectId: {value}") from e


def _encode_folder_id(folder_type: FolderType, oid: ObjectId) -> str:
    return f"{folder_type}:{str(oid)}"


def _decode_folder_id(folder_id: str) -> Tuple[FolderType, ObjectId]:
    raw = (folder_id or "").strip()
    if ":" not in raw:
        raise HTTPException(status_code=400, detail="folder_id must be like 'zone:<id>'")
    folder_type, oid = raw.split(":", 1)
    if folder_type not in ("zone", "section", "artifact", "subartifact"):
        raise HTTPException(status_code=400, detail="folder_id type must be zone|section|artifact|subartifact")
    return folder_type, _oid(oid)


@router.get("/folders", response_model=List[ISFFolderNode])
async def get_isf_folders(
    _current_user=Depends(get_current_active_user),
    db=Depends(get_database),
):
    """
    Return hierarchical ISF folder structure (Zones -> Sections -> Artifacts -> SubArtifacts).

    Mirrors the ISF Viewer sidebar: every zone/section/artifact from the reference
    collections is returned (including empty ones) with per-folder document counts.
    Document refs that don't resolve to a reference record are appended as trailing
    "(unlinked)" zones so their files stay reachable.
    """
    zones = await db[ZONES_COLLECTION].find({}).sort("zoneNumber", 1).to_list(length=None)
    sections = await db[SECTIONS_COLLECTION].find({}).to_list(length=None)
    artifacts = await db[ARTIFACTS_COLLECTION].find({}).to_list(length=None)
    subartifacts = await db[SUBARTIFACTS_COLLECTION].find({}).to_list(length=None)

    # Per-folder document counts (a document carries all four refs, so counting each
    # field independently gives correct totals at every level).
    counts: Dict[str, Dict[Any, int]] = {}
    for field in ("zone", "section", "artifact", "subArtifact"):
        rows = await db[ISF_DOCUMENTS_COLLECTION].aggregate(
            [
                {"$match": {field: {"$ne": None}}},
                {"$group": {"_id": f"${field}", "n": {"$sum": 1}}},
            ]
        ).to_list(length=None)
        counts[field] = {r["_id"]: r["n"] for r in rows}

    sections_by_zone: Dict[ObjectId, List[Dict[str, Any]]] = {}
    for s in sections:
        if s.get("zone"):
            sections_by_zone.setdefault(s["zone"], []).append(s)

    artifacts_by_section: Dict[ObjectId, List[Dict[str, Any]]] = {}
    for a in artifacts:
        if a.get("section"):
            artifacts_by_section.setdefault(a["section"], []).append(a)

    sub_by_artifact: Dict[ObjectId, List[Dict[str, Any]]] = {}
    for sa in subartifacts:
        if sa.get("artifact"):
            sub_by_artifact.setdefault(sa["artifact"], []).append(sa)

    def fmt_num(v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    tree: List[ISFFolderNode] = []
    for z in zones:
        znode = ISFFolderNode(
            folder_id=_encode_folder_id("zone", z["_id"]),
            folder_type="zone",
            folder_name=str(z.get("zoneName") or "Zone"),
            folder_number=fmt_num(z.get("zoneNumber")),
            document_count=counts["zone"].get(z["_id"], 0),
        )
        for s in sorted(sections_by_zone.get(z["_id"], []), key=lambda s: str(s.get("sectionNumber", ""))):
            snode = ISFFolderNode(
                folder_id=_encode_folder_id("section", s["_id"]),
                folder_type="section",
                folder_name=str(s.get("sectionName") or "Section"),
                folder_number=fmt_num(s.get("sectionNumber")),
                document_count=counts["section"].get(s["_id"], 0),
            )
            for a in sorted(artifacts_by_section.get(s["_id"], []), key=lambda a: str(a.get("artifactNumber", ""))):
                anode = ISFFolderNode(
                    folder_id=_encode_folder_id("artifact", a["_id"]),
                    folder_type="artifact",
                    folder_name=str(a.get("artifactName") or "Artifact"),
                    folder_number=fmt_num(a.get("artifactNumber")),
                    document_count=counts["artifact"].get(a["_id"], 0),
                )
                for sa in sorted(sub_by_artifact.get(a["_id"], []), key=lambda sa: str(sa.get("subArtifactName", ""))):
                    anode.subfolders.append(
                        ISFFolderNode(
                            folder_id=_encode_folder_id("subartifact", sa["_id"]),
                            folder_type="subartifact",
                            folder_name=str(sa.get("subArtifactName") or "SubArtifact"),
                            document_count=counts["subArtifact"].get(sa["_id"], 0),
                        )
                    )
                snode.subfolders.append(anode)
            znode.subfolders.append(snode)
        tree.append(znode)

    # Documents whose zone ref doesn't resolve (deleted/reseeded reference records):
    # surface them as trailing "(unlinked)" zones, labelled from the docs' tmfReference
    # zone number when parsable, so their files remain reachable in the picker.
    known_zone_ids = {z["_id"] for z in zones}
    orphan_zone_ids = [zid for zid in counts["zone"] if zid not in known_zone_ids]
    if orphan_zone_ids:
        zone_ref_rows = await db[ISF_DOCUMENTS_COLLECTION].aggregate(
            [
                {"$match": {"zone": {"$in": orphan_zone_ids}, "tmfReference": {"$type": "string"}}},
                {"$group": {"_id": "$zone", "tmfRef": {"$first": "$tmfReference"}}},
            ]
        ).to_list(length=None)
        zone_num_from_ref: Dict[Any, int] = {}
        for row in zone_ref_rows:
            try:
                zone_num_from_ref[row["_id"]] = int((row.get("tmfRef") or "").split(".")[0])
            except (ValueError, TypeError):
                pass
        zones_by_number = {z.get("zoneNumber"): z for z in zones if z.get("zoneNumber") is not None}

        for zid in sorted(orphan_zone_ids, key=str):
            num = zone_num_from_ref.get(zid)
            canonical = zones_by_number.get(num)
            if canonical:
                label = f'{canonical.get("zoneName", "Zone")} (unlinked)'
            elif num is not None:
                label = f"Zone {num} (unlinked)"
            else:
                label = "Unlinked zone"
            tree.append(
                ISFFolderNode(
                    folder_id=_encode_folder_id("zone", zid),
                    folder_type="zone",
                    folder_name=label,
                    folder_number=fmt_num(num),
                    document_count=counts["zone"].get(zid, 0),
                )
            )

    return tree


@router.get("/documents", response_model=List[ISFDocumentListItem])
async def browse_isf_documents(
    folder_id: str = Query(..., description="Folder id from /isf/folders, e.g. zone:<id>"),
    _current_user=Depends(get_current_active_user),
    db=Depends(get_database),
):
    folder_type, oid = _decode_folder_id(folder_id)

    query: Dict[str, Any] = {}
    if folder_type == "zone":
        query["zone"] = oid
    elif folder_type == "section":
        query["section"] = oid
    elif folder_type == "artifact":
        query["artifact"] = oid
    else:
        query["subArtifact"] = oid

    docs = await db[ISF_DOCUMENTS_COLLECTION].find(query).sort("modificationDate", -1).limit(250).to_list(length=250)
    out: List[ISFDocumentListItem] = []
    for d in docs or []:
        raw_size = d.get("fileSize", d.get("file_size"))
        try:
            size_int = int(raw_size) if raw_size is not None else None
        except (TypeError, ValueError):
            size_int = None

        mod_raw = d.get("modificationDate") or d.get("modification_date") or d.get("updatedAt")
        if isinstance(mod_raw, datetime):
            mod_date = mod_raw
        else:
            mod_date = None

        out.append(
            ISFDocumentListItem(
                id=str(d.get("_id")),
                title=str(d.get("title") or d.get("documentId") or "Untitled"),
                mime_type=d.get("mimeType") or d.get("mime_type"),
                file_url=d.get("fileUrl") or d.get("file_url"),
                file_size=size_int,
                modification_date=mod_date,
                version=d.get("version"),
            )
        )
    return out


@router.post("/import", response_model=ISFImportResponse)
async def import_isf_documents(
    payload: ISFImportRequest,
    _current_user=Depends(get_current_active_user),
    db=Depends(get_database),
):
    """
    Given ISF document IDs, return presigned URLs (SAS) + metadata for client-side import.
    The frontend can download and stage these as Files inside the current module.
    """
    from ..services.azure_upload import generate_sas_url

    service = ISFDocumentService()
    docs: List[ISFImportItem] = []

    for doc_id in payload.document_ids or []:
        doc = await service.get_document_by_id(db=db, document_id=doc_id)
        if not doc:
            continue

        model = doc.model_dump() if hasattr(doc, "model_dump") else {}
        file_url = getattr(doc, "file_url", None) or model.get("file_url") or ""
        title = getattr(doc, "title", None) or model.get("title") or "Untitled"
        mime_type = getattr(doc, "mime_type", None) or model.get("mime_type")

        if not file_url:
            continue

        try:
            blob_name = file_url.split("/")[-1].split("?")[0]
            sas_url = generate_sas_url(blob_name) if blob_name else None
        except Exception:
            sas_url = None

        docs.append(
            ISFImportItem(
                id=str(getattr(doc, "id", None) or model.get("id") or doc_id),
                title=str(title),
                mime_type=mime_type,
                url=sas_url or file_url,
            )
        )

    return ISFImportResponse(documents=docs)


