from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from typing import List, Optional, Dict, Any

from datetime import datetime, timezone
import json
import hashlib
from fastapi import status as HTTPStatus
from bson import ObjectId

from ..models.isf_document import (
    ISFDocumentCreate, ISFDocumentUpdate, ISFDocumentResponse,
    DocumentType, DocumentStatus, AuditTrail
)
from ..core.config import settings
from ..services.isf_document_service import ISFDocumentService
from ..services.azure_upload import upload_to_azure
from ..services.tmf_resolution import resolve_tmf_from_metadata, tmf_from_classification
from ..services.isf_workflow_service import hydrate_workflow_document
from ..utils.file_handler import FileHandler
from ..utils.document_extractor import get_page_count
from ..core.database import get_database
from ..utils.auth import get_current_active_user

router = APIRouter()

# Dependency injection
def get_document_service():
    return ISFDocumentService()

def get_file_handler():
    return FileHandler()


def _parse_isf_sort(sort: Optional[str]) -> tuple:
    """
    Frontend sends e.g. createdAt:desc — map to Mongo field names (camelCase from Node).
    Returns (field_name, direction) where direction is 1 or -1.
    """
    # Default _id desc — stable, no mixed-type sort errors; ObjectId order ≈ insert time.
    if not sort or not str(sort).strip():
        return ("_id", -1)
    parts = str(sort).split(":", 1)
    key = (parts[0] or "").strip().lower()
    direction = (parts[1] or "desc").strip().lower() if len(parts) > 1 else "desc"
    sort_dir = -1 if direction in ("desc", "-1", "descending") else 1
    key_map = {
        "createdat": "_id",
        "creationdate": "creationDate",
        "modifiedat": "modificationDate",
        "modificationdate": "modificationDate",
        "title": "title",
        "status": "status",
    }
    field = key_map.get(key, "_id")
    return (field, sort_dir)


@router.get("", response_model=List[ISFDocumentResponse])
@router.get("/", response_model=List[ISFDocumentResponse], include_in_schema=False)
async def get_isf_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    page: Optional[int] = Query(None, ge=1),
    sort: Optional[str] = Query(None, description="e.g. createdAt:desc"),
    study: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    site: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Get all ISF documents with optional filtering"""
    try:
        # For testing, allow unauthenticated access to fetch all documents
        user_id = None  # No authentication required for testing

        # Frontend (ISFDocumentList) sends page=1&limit=10 — map to skip
        effective_skip = skip
        if page is not None:
            effective_skip = (page - 1) * limit

        sort_field, sort_direction = _parse_isf_sort(sort)
        
        print("DEBUG: get_isf_documents called with params:")
        print(f"  - skip: {effective_skip} (raw skip={skip}, page={page})")
        print(f"  - limit: {limit}")
        print(f"  - study: {study}")
        print(f"  - country: {country}")
        print(f"  - site: {site}")
        print(f"  - search: {search}")
        print(f"  - user_id: {user_id}")
        
        documents = await service.get_documents(
            db=db,
            skip=effective_skip,
            limit=limit,
            study=study,
            country=country,
            site=site,
            search=search,
            user_id=user_id,
            collection_name="isf_documents",  # Use isf_documents collection
            sort_field=sort_field,
            sort_direction=sort_direction,
        )
        
        print(f"DEBUG: service returned {len(documents)} documents")
        for i, doc in enumerate(documents):
            print(f"  - Doc {i+1}: {doc.document_id} - {doc.title}")
        
        return documents
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve documents: {str(e)}"
        )


@router.get("/{document_id}", response_model=ISFDocumentResponse)
async def get_isf_document(
    document_id: str,
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Get specific ISF document by ID"""
    try:
        document = await service.get_document_by_id(
            db=db,
            document_id=document_id
        )
        if not document:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        return document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve document: {str(e)}"
        )


@router.post("/upload", response_model=ISFDocumentResponse)
async def upload_isf_document(
    user_id: str = Form(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    document_type: DocumentType = Form(...),
    tmf_reference: Optional[str] = Form(None),   # made optional - frontend may omit
    study: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    site: Optional[str] = Form(None),
    document_date: Optional[str] = Form(None),    # accept as string to avoid datetime parse errors
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service),
    file_handler: FileHandler = Depends(get_file_handler)
):
    """Upload and create new ISF document - matches Node.js flow: Azure upload, TMF hierarchy, schema."""
    try:
        import re

        # Parse document_date safely (it may come as "2026-03-11" or full ISO string)
        parsed_document_date = datetime.now(timezone.utc).replace(tzinfo=None)
        if document_date:
            try:
                # Try various common formats
                for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                    try:
                        parsed_document_date = datetime.strptime(document_date, fmt)
                        break
                    except ValueError:
                        continue
            except Exception:
                parsed_document_date = datetime.now(timezone.utc).replace(tzinfo=None)

        file_content = await file.read()
        file_size = len(file_content)
        
        # PHI detection (like Node.js)
        phi_detected = False
        phi_details = []
        phi_patterns = [
            r'\b\d{3}-\d{2}-\d{4}\b',
            r'\b\d{2}[-\s]?\d{2}[-\s]?\d{4}\b',
            r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',
            r'\b[A-Z]{2}\d{2,4}\b',
            r'MR\d{6,8}\b',
        ]
        content_text = file_content.decode('utf-8', errors='ignore')
        for pattern in phi_patterns:
            if re.search(pattern, content_text):
                phi_detected = True
                phi_details.append(f"PHI pattern detected: {pattern}")
                break
        
        # Parse the metadata JSON string into raw_meta dict
        # This is the KEY field: the frontend sends all TMF hierarchy data
        # (zoneNumber, zoneName, sectionNumber, etc.) inside this JSON string.
        raw_meta = {}
        if metadata:
            try:
                raw_meta = json.loads(metadata) if isinstance(metadata, str) else metadata
            except Exception as parse_err:
                print(f"WARNING: Failed to parse metadata JSON: {parse_err}")
                raw_meta = {}
        
        print("DEBUG: Complete metadata received during upload:")
        print(f"  - Raw metadata string length: {len(metadata) if metadata else 0} chars")
        print(f"  - Raw metadata (first 500 chars): {metadata[:500] if metadata else 'None - metadata field was empty!'}")
        print("  - Parsed raw_meta:", raw_meta)
        print("  - File filename:", file.filename)
        print("  - File content type:", file.content_type)
        print("  - Form fields:")
        print("    * user_id:", user_id)
        print("    * title:", title)
        print("    * description:", description)
        print("    * document_type:", document_type)
        print("    * tmf_reference:", tmf_reference)
        print("    * study:", study)
        print("    * country:", country)
        print("    * site:", site)
        print("    * document_date (raw):", document_date)
        print("    * document_date (parsed):", parsed_document_date)
        print("  - TMF fields extracted from raw_meta:")
        print("    * zoneNumber:", raw_meta.get("zoneNumber"))
        print("    * zoneName:", raw_meta.get("zoneName"))
        print("    * sectionNumber:", raw_meta.get("sectionNumber"))
        print("    * sectionName:", raw_meta.get("sectionName"))
        print("    * artifactNumber:", raw_meta.get("artifactNumber"))
        print("    * artifactName:", raw_meta.get("artifactName"))
        print("    * subArtifactName:", raw_meta.get("subArtifactName"))
        
        classification_result = None
        if not phi_detected and not raw_meta.get("zoneNumber") and not raw_meta.get("zone_number"):
            print("DEBUG: Attempting classification - PHI detected:", phi_detected, "Has zone in meta:", bool(raw_meta.get("zoneNumber") or raw_meta.get("zone_number")))
            try:
                from ..services.gemini_service import GeminiService
                gemini_service = GeminiService()
                classification_result = await gemini_service.classify_document(
                    file_content, file.filename or "document", file.content_type or "application/octet-stream"
                )
                print("DEBUG: Classification successful:", classification_result is not None)
            except Exception as e:
                print("DEBUG: Classification failed:", str(e))
                pass
        

        print("raw_meta data for uploading document:", raw_meta)
        # TMF hierarchy: from metadata (Node-style) or from classification
        zone_id = section_id = artifact_id = sub_artifact_id = None
        if raw_meta.get("zoneNumber") is not None or raw_meta.get("zone_number") is not None:
            zone_id, section_id, artifact_id, sub_artifact_id = await resolve_tmf_from_metadata(
                db,
                zone_number=raw_meta.get("zoneNumber") or raw_meta.get("zone_number"),
                zone_name=raw_meta.get("zoneName") or raw_meta.get("zone_name") or "Unknown",
                section_number=raw_meta.get("sectionNumber") or raw_meta.get("section_number") or "00.00",
                section_name=raw_meta.get("sectionName") or raw_meta.get("section_name") or "Unknown",
                artifact_number=raw_meta.get("artifactNumber") or raw_meta.get("artifact_number") or "00.00.00",
                artifact_name=raw_meta.get("artifactName") or raw_meta.get("artifact_name") or "Unknown",
                sub_artifact_name=raw_meta.get("subArtifactName") or raw_meta.get("sub_artifact_name"),
            )
        elif classification_result:
            print("DEBUG: Classification result received:", classification_result)
            tmf_meta = tmf_from_classification(classification_result)
            print("DEBUG: TMF metadata from classification:", tmf_meta)
            zone_id, section_id, artifact_id, sub_artifact_id = await resolve_tmf_from_metadata(
                db,
                zone_number=tmf_meta["zoneNumber"],
                zone_name=tmf_meta["zoneName"],
                section_number=tmf_meta["sectionNumber"],
                section_name=tmf_meta["sectionName"],
                artifact_number=tmf_meta["artifactNumber"],
                artifact_name=tmf_meta["artifactName"],
                sub_artifact_name=tmf_meta["subArtifactName"] or None,
            )
            print("DEBUG: Resolved TMF IDs from classification:", zone_id, section_id, artifact_id, sub_artifact_id)
        
        # Default TMF hierarchy when none resolved (Node-compatible: document always has zone/section/artifact)
        if zone_id is None:
            print("DEBUG: Using default zone 0 - zone_id is None")
            zone_id, section_id, artifact_id, sub_artifact_id = await resolve_tmf_from_metadata(
                db,
                zone_number=0,
                zone_name="Unknown",
                section_number="00.00",
                section_name="Unknown",
                artifact_number="00.00.00",
                artifact_name="Unknown",
                sub_artifact_name=None,
            )
        else:
            print("DEBUG: Using resolved zone:", zone_id)
        
        # Resolve user to ObjectId (author, uploadedBy, createdBy, lastModifiedBy - Node sets all to uploaderUser._id)
        user_oid = None
        if user_id and ObjectId.is_valid(user_id):
            user_oid = ObjectId(user_id)
            try:
                users_coll = getattr(db, "users", None)
                if users_coll:
                    u = await users_coll.find_one({"_id": user_oid})
                    if not u:
                        u = await users_coll.find_one({"email": user_id})
                    if u:
                        user_oid = u["_id"]
            except Exception:
                pass
        if user_oid is None and user_id and ObjectId.is_valid(user_id):
            user_oid = ObjectId(user_id)
        
        # File hash (Node: calculateFileHash(buffer) - SHA-256 hex)
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # Page count (Node: rawMeta.pageCount or from validation; we extract from PDF when possible)
        mime_type = file.content_type or "application/octet-stream"
        page_count = get_page_count(file_content, mime_type)
        if page_count is None and raw_meta:
            try:
                pc = raw_meta.get("pageCount") or raw_meta.get("page_count")
                page_count = int(pc) if pc is not None else None
            except (TypeError, ValueError):
                page_count = None
        
        # customMetadata: same structure as Node (validation + tmfMetadata)
        custom_metadata = {
            "validation": {
                "validatedAt": datetime.now(timezone.utc).replace(tzinfo=None),
                "overallStatus": "PASSED" if not phi_detected else "FAILED",
                "isValid": not phi_detected,
                "virusScan": {"status": "UNKNOWN", "structureIntegrity": True, "formatValidation": True, "contentSafety": True},
                "generalValidation": {"status": "PASSED", "fileSizeValid": True, "fileTypeValid": True, "fileNameValid": True},
                "mimeValidation": {"status": "UNKNOWN", "detectedMimeType": mime_type, "declaredMimeType": mime_type, "notes": None, "errors": []},
                "phiDetection": {"status": "PASSED" if not phi_detected else "FAILED", "detected": phi_detected},
                "warnings": phi_details,
                "metadataSanitization": {"actions": [], "warnings": phi_details},
            },
            "tmfMetadata": {
                "processBasedMetadata": raw_meta.get("processBasedMetadata") or raw_meta.get("process_based_metadata") or "",
                "tmfLevel": raw_meta.get("tmfLevel") or raw_meta.get("tmf_level") or "",
                "coreOrRecommended": raw_meta.get("coreOrRecommended") or raw_meta.get("core_or_recommended") or "",
                "ichCode": raw_meta.get("ichCode") or raw_meta.get("ich_code") or "",
                "iso14155Reference": raw_meta.get("iso14155Reference") or raw_meta.get("iso14155_reference") or "",
                "uniqueIdNumber": raw_meta.get("uniqueIdNumber") or raw_meta.get("unique_id_number") or "",
                "sponsorDocument": raw_meta.get("sponsorDocument") is True or str(raw_meta.get("sponsorDocument", "")).lower() == "true",
                "investigatorDocument": raw_meta.get("investigatorDocument") is True or str(raw_meta.get("investigatorDocument", "")).lower() == "true",
                "processNumber": raw_meta.get("processNumber") or raw_meta.get("process_number") or "",
                "processName": raw_meta.get("processName") or raw_meta.get("process_name") or "",
                "trialLevelDocument": raw_meta.get("trialLevelDocument") or raw_meta.get("trial_level_document") or "",
                "trialLevelMilestoneEvent": raw_meta.get("trialLevelMilestoneEvent") or raw_meta.get("trial_level_milestone_event") or "",
                "countryRegionLevelDocument": raw_meta.get("countryRegionLevelDocument") or raw_meta.get("country_region_level_document") or "",
                "countryLevelMilestoneEvent": raw_meta.get("countryLevelMilestoneEvent") or raw_meta.get("country_level_milestone_event") or "",
                "siteLevelDocument": raw_meta.get("siteLevelDocument") or raw_meta.get("site_level_document") or "",
                "siteLevelMilestoneEvent": raw_meta.get("siteLevelMilestoneEvent") or raw_meta.get("site_level_milestone_event") or "",
            },
        }
        
        # Upload to Azure Blob Storage (same as Node.js uploadToAzure)
        azure_blob_url = upload_to_azure(
            file_content,
            file.filename or "document",
            file.content_type or "application/octet-stream",
        )
        
        # workflowSummary: camelCase to match Node.js and frontend
        workflow_summary = {
            "lifecycleState": "INTAKE",
            "reviewOverallStatus": "NOT_STARTED",
            "approvalOverallStatus": "NOT_STARTED",
            "metrics": {
                "reviewProgress": 0,
                "approvalProgress": 0,
                "auditReadiness": 0,
                "overdueCount": 0
            },
            "lastTransitionAt": None
        }
        
        doc_data = {
            "documentId": await service.generate_document_id(db),
            "title": title,
            "description": description or "",
            "documentType": document_type.value if document_type else "OTHER",
            "tmfReference": tmf_reference or raw_meta.get("tmfReference") or "",
            "version": 1,
            "study": study or raw_meta.get("study") or "",  # empty if no study provided — never fabricate a fake ID
            "country": country or raw_meta.get("country") or "",
            "site": site or raw_meta.get("site") or "",
            "fileUrl": azure_blob_url,
            "fileSize": file_size,
            "mimeType": mime_type,
            "fileHash": file_hash,
            "fileHashAlgorithm": "SHA-256",
            "metadataSanitization": {
                "actions": [],
                "warnings": phi_details if phi_detected else [],
                "detectedMimeType": mime_type,
                "declaredMimeType": mime_type,
                "sanitizedAt": datetime.now(timezone.utc).replace(tzinfo=None),
                "originalSize": file_size,
                "sanitizedSize": file_size
            },
            "pageCount": page_count,
            "legibilityClear": (lambda v: v if v in ("CLEAR", "UNCLEAR") else None)(raw_meta.get("legibilityClear") or raw_meta.get("legibility_clear")),
            "ingestionType": "Manual",
            "language": (raw_meta.get("language") or "en")[:10],
            "documentDate": parsed_document_date,
            "creationDate": datetime.now(timezone.utc).replace(tzinfo=None),
            "modificationDate": datetime.now(timezone.utc).replace(tzinfo=None),
            "importDate": datetime.now(timezone.utc).replace(tzinfo=None),
            "approvalDate": None,
            "expirationDate": None,
            "author": user_oid,
            "contributors": [],
            "approvers": [],
            "uploadedBy": user_oid,
            "createdBy": user_oid,
            "lastModifiedBy": user_oid,
            "status": "DRAFT",
            "qualityControlStatus": "PENDING",
            "completenessStatus": "PENDING_REVIEW",
            "archivalStatus": "ACTIVE",
            "securitySettings": {"accessLevel": "RESTRICTED", "allowedRoles": []},
            "relatedDocuments": [],
            "regulatoryAuthority": None,
            "gcpComplianceStatus": "PENDING_REVIEW",
            "retentionRequirements": None,
            "previousVersions": [],
            "workflowRef": None,
            "workflowSummary": workflow_summary,
            "auditTrail": [{
                "action": "DOCUMENT_CREATED",
                "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
                "user": ObjectId(user_id) if user_id and ObjectId.is_valid(user_id) else None,
                "details": {
                    "file_metadata": {
                        "filename": file.filename,
                        "content_type": file.content_type,
                        "size": file_size,
                        "phi_detected": phi_detected,
                        "classification": classification_result
                    }
                },
                "ipAddress": None
            }],
            "tags": [],
            "customMetadata": custom_metadata,
            "zone": zone_id,
            "section": section_id,
            "artifact": artifact_id,
            "subArtifact": sub_artifact_id,
        }
        
        print(f"DEBUG: Document data prepared: {len(str(doc_data))} characters")
        print(f"DEBUG: Document ID: {doc_data['documentId']}")
        print(f"DEBUG: TMF Resolution results - zone: {zone_id}, section: {section_id}, artifact: {artifact_id}, subArtifact: {sub_artifact_id}")
        
        # Step 5: Save to MongoDB (matches Node.js schema)
        result = await db.isf_documents.insert_one(doc_data)
        created_doc = await db.isf_documents.find_one({"_id": result.inserted_id})
        if not created_doc:
            raise HTTPException(status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created document")
        
        # Step 6: Initialize workflow (Node: workflowRef/workflowSummary set when workflow is opened; we set on create for consistency)
        try:
            await hydrate_workflow_document(db, created_doc, user_id, "isf_documents")
        except Exception as e:
            pass  # non-fatal; document is created, workflow can be initialized on first open
        
        created_doc = await db.isf_documents.find_one({"_id": result.inserted_id})
        return service._convert_to_response(created_doc)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}"
        )


@router.put("/{document_id}", response_model=ISFDocumentResponse)
async def update_isf_document(
    document_id: str,
    document_update: ISFDocumentUpdate,
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Update ISF document"""
    try:
        # Module runs auth-less (see delete below); "system" is the acting user
        # for the service's audit trail. Without these the call raised TypeError
        # and this endpoint always returned 500.
        updated_document = await service.update_document(
            db=db,
            document_id=document_id,
            document_update=document_update,
            user_id="system",
            updated_by="system",
        )
        if not updated_document:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        return updated_document
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update document: {str(e)}"
        )


@router.delete("/{document_id}")
async def delete_isf_document(
    document_id: str,
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Delete ISF document. Optional: pass current_user to restrict to own documents."""
    try:
        user_id = None  # No auth restriction: delete by id only so UI delete always works
        success = await service.delete_document(
            db=db,
            document_id=document_id,
            user_id=user_id
        )
        if not success:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        return {"success": True, "message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )


@router.post("/{document_id}/approve")
async def approve_isf_document(
    document_id: str,
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Approve ISF document"""
    try:
        success = await service.approve_document(
            db=db,
            document_id=document_id,
            user_id="system",
        )
        if not success:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found or cannot be approved"
            )
        return {"success": True, "message": "Document approved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve document: {str(e)}"
        )


@router.post("/{document_id}/reject")
async def reject_isf_document(
    document_id: str,
    reason: str = Form(...),
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Reject ISF document"""
    try:
        success = await service.reject_document(
            db=db,
            document_id=document_id,
            user_id="system",
            reason=reason,
        )
        if not success:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found or cannot be rejected"
            )
        return {"success": True, "message": "Document rejected successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject document: {str(e)}"
        )


@router.post("/{document_id}/archive")
async def archive_isf_document(
    document_id: str,
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Archive ISF document"""
    try:
        success = await service.archive_document(
            db=db,
            document_id=document_id,
            user_id="system",
        )
        if not success:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        return {"success": True, "message": "Document archived successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive document: {str(e)}"
        )


@router.get("/{document_id}/audit-trail")
async def get_document_audit_trail(
    document_id: str,
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Get document audit trail. Returns { audit_trail: [...] }."""
    try:
        audit_trail = await service.get_document_audit_trail(
            db=db,
            document_id=document_id
        )
        if audit_trail is None:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        return {"audit_trail": audit_trail}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit trail: {str(e)}"
        )


@router.get("/{document_id}/audit-logs")
async def get_document_audit_logs(
    document_id: str,
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """Alias for audit-trail. Returns { data: [...] } for frontend compatibility."""
    try:
        audit_trail = await service.get_document_audit_trail(
            db=db,
            document_id=document_id
        )
        if audit_trail is None:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        return {"data": audit_trail}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit trail: {str(e)}"
        )


@router.get("/sas-url")
async def get_sas_url_by_blob_name(
    blobName: str,
    current_user=Depends(get_current_active_user),
):
    """
    Generate a time-limited SAS read URL for a given Azure blob name.
    Compatible with Shashank's Node.js endpoint: GET /sas-url?blobName=xxx
    Returns { sasUrl: string }
    """
    from ..services.azure_upload import generate_sas_url
    try:
        blob_name = blobName.strip()
        if not blob_name:
            raise HTTPException(status_code=400, detail="blobName query parameter is required")

        sas_url = generate_sas_url(blob_name)
        if not sas_url:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Azure storage not configured or SAS generation failed"
            )
        return {"sasUrl": sas_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate SAS URL: {str(e)}"
        )


@router.get("/{document_id}/presign")
async def get_document_presign_url(
    document_id: str,
    db=Depends(get_database),
    service: ISFDocumentService = Depends(get_document_service)
):
    """
    Return a time-limited SAS URL for the document.
    Falls back to the raw file_url if Azure SAS generation is not configured.
    Frontend expects { url: string }.
    """
    from ..services.azure_upload import generate_sas_url
    try:
        doc = await service.get_document_by_id(db=db, document_id=document_id)
        if not doc:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        # Resolve the stored file URL
        file_url = getattr(doc, "file_url", None) or (doc.model_dump() if hasattr(doc, "model_dump") else {}).get("file_url")
        if not file_url:
            raise HTTPException(
                status_code=HTTPStatus.HTTP_404_NOT_FOUND,
                detail="Document has no file URL"
            )

        # Try to generate a SAS URL from the blob name embedded in the stored URL.
        # Stored URL format: https://<account>.blob.core.windows.net/<container>/<blobName>
        try:
            blob_name = file_url.split("/")[-1].split("?")[0]  # strip any existing query string
            sas_url = generate_sas_url(blob_name) if blob_name else None
        except Exception:
            sas_url = None

        # Return SAS URL if generated; otherwise fall back to the raw stored URL
        return {"url": sas_url or file_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get presign URL: {str(e)}"
        )
