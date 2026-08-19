from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from bson import ObjectId
import logging
import re
import uuid

logger = logging.getLogger(__name__)

from ..models.isf_document import (
    ISFDocumentCreate,
    ISFDocumentUpdate,
    ISFDocumentResponse,
    DocumentType,
    DocumentStatus,
    AuditTrail,
    QualityControlStatus,
    CompletenessStatus,
    ArchivalStatus,
    GCPComplianceStatus,
    LegibilityClear,
    RegulatoryAuthority,
    AccessLevel,
)
from ..core.workflow_constants import WorkflowState


def _coerce_version(value) -> int:
    """Mongo/Node may store version as int, float, or string like '1.0'."""
    if value is None:
        return 1
    if isinstance(value, bool):
        return 1
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 1
        try:
            return int(float(s))
        except ValueError:
            return 1
    return 1


def _safe_enum(enum_cls, raw, default):
    if raw is None or raw == "" or raw == "N/A":
        return default
    if isinstance(raw, enum_cls):
        return raw
    s = str(raw).strip()
    sup = s.upper()
    try:
        return enum_cls[sup]
    except KeyError:
        pass
    try:
        return enum_cls(s)
    except ValueError:
        return default


class ISFDocumentService:
    
    async def generate_document_id(self, db) -> str:
        """Generate unique document ID"""
        # Generate unique ID with prefix
        prefix = "ISF"
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d")
        random_part = str(uuid.uuid4())[:8].upper()
        return f"{prefix}-{timestamp}-{random_part}"
    
    async def get_documents(
        self,
        db,
        skip: int = 0,
        limit: int = 100,
        study: Optional[str] = None,
        country: Optional[str] = None,
        site: Optional[str] = None,
        search: Optional[str] = None,
        user_id: Optional[str] = None,
        collection_name: str = "isf_documents",  # Default collection name
        sort_field: str = "_id",
        sort_direction: int = -1,
    ) -> List[ISFDocumentResponse]:
        """Get documents with optional filtering"""
        try:
            # Build query — Mongo stores Node-style camelCase (documentType, not document_type).
            #
            # Scope by STUDY + SITE. Site matching is tolerant of empty/missing site
            # so legacy documents (uploaded before the site id was recorded) are not
            # silently hidden — study above still scopes the result set.
            #
            # NOTE on the site identifier: the frontend's `selectedSiteId` can be the
            # site UUID (`site.id`) OR the site code (`site.site_id`) depending on the
            # code path. Upload and list both read the same `selectedSiteId`, so within
            # a session they agree. If they ever diverge, make the frontend send a single
            # canonical site id for both upload and list.
            parts: List[Dict[str, Any]] = []
            if study:
                parts.append({"study": study})
            if country:
                parts.append({"country": country})
            if site:
                parts.append({
                    "$or": [
                        {"site": site},
                        {"site": ""},
                        {"site": None},
                        {"site": {"$exists": False}},
                    ]
                })

            if search:
                # Do NOT use $text — it requires a text index and 500s in prod if missing.
                esc = re.escape(search.strip())
                parts.append(
                    {
                        "$or": [
                            {"title": {"$regex": esc, "$options": "i"}},
                            {"documentId": {"$regex": esc, "$options": "i"}},
                        ]
                    }
                )

            if user_id:
                uid = ObjectId(user_id)
                parts.append(
                    {
                        "$or": [
                            {"created_by": uid},
                            {"uploaded_by": uid},
                            {"author": uid},
                        ]
                    }
                )

            if not parts:
                query: Dict[str, Any] = {}
            elif len(parts) == 1:
                query = parts[0]
            else:
                query = {"$and": parts}

            # Execute query
            collection = getattr(db, collection_name)  # Use the specified collection name

            async def _consume_cursor(cur):
                out: List[ISFDocumentResponse] = []
                async for doc in cur:
                    try:
                        out.append(self._convert_to_response(doc))
                    except Exception as doc_err:
                        doc_key = doc.get("documentId") or doc.get("_id")
                        logger.warning(
                            "Skipping ISF document %s due to conversion error: %s",
                            doc_key,
                            doc_err,
                            exc_info=True,
                        )
                return out

            # Sorting on creationDate can 500 when BSON types are mixed (string vs date).
            try:
                cursor = (
                    collection.find(query)
                    .sort(sort_field, sort_direction)
                    .skip(skip)
                    .limit(limit)
                )
                return await _consume_cursor(cursor)
            except Exception as sort_err:
                logger.warning(
                    "ISF list query failed (sort=%s dir=%s): %s — retrying with _id",
                    sort_field,
                    sort_direction,
                    sort_err,
                    exc_info=True,
                )
                cursor = (
                    collection.find(query)
                    .sort("_id", sort_direction)
                    .skip(skip)
                    .limit(limit)
                )
                return await _consume_cursor(cursor)

        except Exception as e:
            raise Exception(f"Failed to retrieve documents: {str(e)}")
    
    async def get_document_by_id(
        self,
        db,
        document_id: str,
        user_id: Optional[str] = None,
        collection_name: str = "isf_documents"  # Default collection name
    ) -> Optional[ISFDocumentResponse]:
        """Get document by ID"""
        try:
            # Build query
            query = {"_id": ObjectId(document_id)}
            
            # Add user permissions filter (simplified)
            if user_id:
                query["$or"] = [
                    {"created_by": ObjectId(user_id)},
                    {"uploaded_by": ObjectId(user_id)},
                    {"author": ObjectId(user_id)}
                ]
            
            # Execute query
            collection = getattr(db, collection_name)  # Use the specified collection name
            doc = await collection.find_one(query)
            
            if not doc:
                return None
            
            return self._convert_to_response(doc)
            
        except Exception as e:
            raise Exception(f"Failed to retrieve document: {str(e)}")
    
    async def create_document(
        self,
        db,
        document: ISFDocumentCreate,
        user_id: str,
        created_by: str,
        file_metadata: Optional[Dict[str, Any]] = None,
        collection_name: str = "isf_documents"  # Default collection name
    ) -> ISFDocumentResponse:
        """Create new document"""
        try:
            # Prepare document data
            doc_data = document.dict()
            doc_data["created_by"] = ObjectId(created_by)
            doc_data["creation_date"] = datetime.now(timezone.utc).replace(tzinfo=None)
            doc_data["modification_date"] = datetime.now(timezone.utc).replace(tzinfo=None)
            doc_data["import_date"] = datetime.now(timezone.utc).replace(tzinfo=None)
            
            # Add file metadata if provided
            if file_metadata:
                doc_data["file_hash"] = file_metadata.get("hash")
                doc_data["page_count"] = file_metadata.get("page_count")
            
            # Add initial audit trail
            audit_trail = AuditTrail(
                action="DOCUMENT_CREATED",
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                user=str(created_by),
                details={"file_metadata": file_metadata} if file_metadata else {}
            )
            doc_data["audit_trail"] = [audit_trail.dict()]
            
            # Insert document
            collection = getattr(db, collection_name)  # Use the specified collection name
            result = await collection.insert_one(doc_data)
            
            # Retrieve created document
            created_doc = await collection.find_one({"_id": result.inserted_id})
            
            return self._convert_to_response(created_doc)
            
        except Exception as e:
            raise Exception(f"Failed to create document: {str(e)}")
    
    async def update_document(
        self,
        db,
        document_id: str,
        document_update: ISFDocumentUpdate,
        user_id: str,
        updated_by: str,
        collection_name: str = "isf_documents"  # Default collection name
    ) -> Optional[ISFDocumentResponse]:
        """Update document"""
        try:
            # Build update data
            update_data = document_update.dict(exclude_unset=True)
            update_data["last_modified_by"] = ObjectId(updated_by)
            update_data["modification_date"] = datetime.now(timezone.utc).replace(tzinfo=None)
            
            # Add audit trail entry
            audit_trail = AuditTrail(
                action="DOCUMENT_UPDATED",
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                user=ObjectId(updated_by),
                details={"updated_fields": list(update_data.keys())}
            )
            
            # Update document
            collection = getattr(db, collection_name)  # Use the specified collection name
            result = await collection.update_one(
                {"_id": ObjectId(document_id)},
                {
                    "$set": update_data,
                    "$push": {"audit_trail": audit_trail.dict()}
                }
            )
            
            if result.matched_count == 0:
                return None
            
            # Retrieve updated document
            updated_doc = await collection.find_one({"_id": ObjectId(document_id)})
            
            return self._convert_to_response(updated_doc)
            
        except Exception as e:
            raise Exception(f"Failed to update document: {str(e)}")
    
    async def delete_document(
        self,
        db,
        document_id: str,
        user_id: Optional[str] = None,
        collection_name: str = "isf_documents"  # Default collection name
    ) -> bool:
        """Delete document. If user_id is provided and valid ObjectId, only allow delete when user is created_by/uploaded_by/author."""
        if not document_id or not ObjectId.is_valid(document_id):
            return False
        try:
            collection = getattr(db, collection_name)
            query = {"_id": ObjectId(document_id)}
            if user_id and ObjectId.is_valid(user_id):
                query["$or"] = [
                    {"created_by": ObjectId(user_id)},
                    {"uploaded_by": ObjectId(user_id)},
                    {"author": ObjectId(user_id)}
                ]
            doc = await collection.find_one(query)
            if not doc:
                return False
            result = await collection.delete_one({"_id": ObjectId(document_id)})
            return result.deleted_count > 0
        except Exception as e:
            raise Exception(f"Failed to delete document: {str(e)}")
    
    async def approve_document(
        self,
        db,
        document_id: str,
        user_id: str,
        collection_name: str = "isf_documents"  # Default collection name
    ) -> bool:
        """Approve document"""
        try:
            # Update document status
            collection = getattr(db, collection_name)  # Use the specified collection name
            audit_trail = AuditTrail(
                action="DOCUMENT_APPROVED",
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                user=ObjectId(user_id),
                details={}
            )
            result = await collection.update_one(
                {"_id": ObjectId(document_id)},
                {
                    "$set": {
                        "status": DocumentStatus.APPROVED.value,
                        "approval_date": datetime.now(timezone.utc).replace(tzinfo=None),
                        "last_modified_by": ObjectId(user_id)
                    },
                    "$push": {"audit_trail": audit_trail.dict()}
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            raise Exception(f"Failed to approve document: {str(e)}")
    
    async def reject_document(
        self,
        db,
        document_id: str,
        user_id: str,
        reason: str,
        collection_name: str = "isf_documents"  # Default collection name
    ) -> bool:
        """Reject document"""
        try:
            # Update document status
            collection = getattr(db, collection_name)  # Use the specified collection name
            audit_trail = AuditTrail(
                action="DOCUMENT_REJECTED",
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                user=ObjectId(user_id),
                details={"reason": reason}
            )
            result = await collection.update_one(
                {"_id": ObjectId(document_id)},
                {
                    "$set": {
                        "status": DocumentStatus.REJECTED.value,
                        "modification_date": datetime.now(timezone.utc).replace(tzinfo=None),
                        "last_modified_by": ObjectId(user_id)
                    },
                    "$push": {"audit_trail": audit_trail.dict()}
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            raise Exception(f"Failed to reject document: {str(e)}")
    
    async def archive_document(
        self,
        db,
        document_id: str,
        user_id: str,
        collection_name: str = "isf_documents"  # Default collection name
    ) -> bool:
        """Archive document"""
        try:
            # Update document status
            collection = getattr(db, collection_name)  # Use the specified collection name
            audit_trail = AuditTrail(
                action="DOCUMENT_ARCHIVED",
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                user=ObjectId(user_id),
                details={}
            )
            result = await collection.update_one(
                {"_id": ObjectId(document_id)},
                {
                    "$set": {
                        "status": DocumentStatus.ARCHIVED.value,
                        "archival_status": "ARCHIVED",
                        "modification_date": datetime.now(timezone.utc).replace(tzinfo=None),
                        "last_modified_by": ObjectId(user_id)
                    },
                    "$push": {"audit_trail": audit_trail.dict()}
                }
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            raise Exception(f"Failed to archive document: {str(e)}")
    
    async def get_document_audit_trail(
        self,
        db,
        document_id: str,
        user_id: Optional[str] = None,
        collection_name: str = "isf_documents"  # Default collection name
    ) -> Optional[List[Dict[str, Any]]]:
        """Get document audit trail. DB may store auditTrail (camelCase) or audit_trail."""
        try:
            collection = getattr(db, collection_name)
            query = {"_id": ObjectId(document_id)}
            if user_id:
                query["$or"] = [
                    {"created_by": ObjectId(user_id)},
                    {"uploaded_by": ObjectId(user_id)},
                    {"author": ObjectId(user_id)}
                ]
            doc = await collection.find_one(query)
            if not doc:
                return None
            raw = doc.get("auditTrail", doc.get("audit_trail", [])) or []
            # Normalize: ensure 'user' is string for JSON
            result = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                user_val = item.get("user")
                if isinstance(user_val, ObjectId):
                    user_val = str(user_val)
                result.append({
                    "action": item.get("action", ""),
                    "timestamp": item.get("timestamp"),
                    "user": user_val or "",
                    "details": item.get("details"),
                    "ip_address": item.get("ipAddress") or item.get("ip_address"),
                })
            return result
            
        except Exception as e:
            raise Exception(f"Failed to retrieve audit trail: {str(e)}")
    
    def _convert_to_response(self, doc: Dict[str, Any]) -> ISFDocumentResponse:
        """Convert database document to response model - matches Node.js schema exactly"""
        # Create a mapped document with correct field names
        mapped_doc = {}
        
        # Core Identification (matches Node.js)
        mapped_doc["id"] = str(doc["_id"])
        mapped_doc["document_id"] = doc.get("documentId", str(doc["_id"]))
        mapped_doc["title"] = doc.get("title", "")
        mapped_doc["description"] = doc.get("description", None)
        
        # Classification (matches Node.js) — coerce to enum (invalid → OTHER)
        doc_type = doc.get("documentType", "OTHER")
        if doc_type == "N/A" or not doc_type:
            doc_type = "OTHER"
        mapped_doc["document_type"] = _safe_enum(DocumentType, doc_type, DocumentType.OTHER)
        mapped_doc["tmf_reference"] = doc.get("tmfReference") or ""
        if not mapped_doc["tmf_reference"]:
            mapped_doc["tmf_reference"] = "-"
        
        # Study Association (matches Node.js)
        mapped_doc["study"] = doc.get("study", None)
        mapped_doc["country"] = doc.get("country", None)
        mapped_doc["site"] = doc.get("site", None)
        
        # File Information (matches Node.js)
        mapped_doc["file_url"] = doc.get("fileUrl") or doc.get("file_url") or ""
        if not mapped_doc["file_url"]:
            mapped_doc["file_url"] = " "
        fs = doc.get("fileSize", doc.get("file_size", 0))
        try:
            mapped_doc["file_size"] = int(fs) if fs is not None else 0
        except (TypeError, ValueError):
            mapped_doc["file_size"] = 0
        if mapped_doc["file_size"] < 0:
            mapped_doc["file_size"] = 0
        mapped_doc["mime_type"] = doc.get("mimeType", None)
        mapped_doc["file_hash"] = doc.get("fileHash", None)
        mapped_doc["page_count"] = doc.get("pageCount", None)
        lc = doc.get("legibilityClear") or doc.get("legibility_clear")
        mapped_doc["legibility_clear"] = (
            _safe_enum(LegibilityClear, lc, None) if lc not in (None, "", "N/A") else None
        )
        mapped_doc["ingestion_type"] = doc.get("ingestionType", "Manual")
        mapped_doc["language"] = doc.get("language", "en")
        
        # Temporal Metadata (matches Node.js)
        mapped_doc["document_date"] = doc.get("documentDate", datetime.now(timezone.utc).replace(tzinfo=None))
        mapped_doc["creation_date"] = doc.get("creationDate", datetime.now(timezone.utc).replace(tzinfo=None))
        mapped_doc["modification_date"] = doc.get("modificationDate", datetime.now(timezone.utc).replace(tzinfo=None))
        mapped_doc["import_date"] = doc.get("importDate", datetime.now(timezone.utc).replace(tzinfo=None))
        mapped_doc["approval_date"] = doc.get("approvalDate", None)
        mapped_doc["expiration_date"] = doc.get("expirationDate", None)
        
        # Authorship (matches Node.js)
        mapped_doc["author"] = str(doc.get("author", "")) if doc.get("author") else None
        mapped_doc["contributors"] = [str(c) for c in doc.get("contributors", [])]
        mapped_doc["approvers"] = []
        mapped_doc["uploaded_by"] = str(doc.get("uploadedBy", "")) if doc.get("uploadedBy") else None
        
        # Status and Workflow (matches Node.js)
        status = doc.get("status", "DRAFT")
        if status == "N/A" or not status:
            status = "DRAFT"
        mapped_doc["status"] = _safe_enum(DocumentStatus, status, DocumentStatus.DRAFT)
        mapped_doc["quality_control_status"] = _safe_enum(
            QualityControlStatus,
            doc.get("qualityControlStatus", "PENDING"),
            QualityControlStatus.PENDING,
        )
        mapped_doc["completeness_status"] = _safe_enum(
            CompletenessStatus,
            doc.get("completenessStatus", "PENDING_REVIEW"),
            CompletenessStatus.PENDING_REVIEW,
        )
        mapped_doc["archival_status"] = _safe_enum(
            ArchivalStatus,
            doc.get("archivalStatus", "ACTIVE"),
            ArchivalStatus.ACTIVE,
        )
        
        # Technical Metadata (matches Node.js)
        _ss = doc.get("securitySettings") or doc.get("security_settings") or {}
        if isinstance(_ss, dict) and _ss:
            _al = _ss.get("access_level") or _ss.get("accessLevel") or "RESTRICTED"
            mapped_doc["security_settings"] = {
                "access_level": _safe_enum(AccessLevel, _al, AccessLevel.RESTRICTED),
                "allowed_roles": _ss.get("allowed_roles")
                or _ss.get("allowedRoles")
                or [],
            }
        else:
            mapped_doc["security_settings"] = {
                "access_level": AccessLevel.RESTRICTED,
                "allowed_roles": [],
            }
        mapped_doc["related_documents"] = []
        _ra = doc.get("regulatoryAuthority") or doc.get("regulatory_authority")
        mapped_doc["regulatory_authority"] = (
            _safe_enum(RegulatoryAuthority, _ra, None) if _ra not in (None, "", "N/A") else None
        )
        mapped_doc["gcp_compliance_status"] = _safe_enum(
            GCPComplianceStatus,
            doc.get("gcpComplianceStatus", "PENDING_REVIEW"),
            GCPComplianceStatus.PENDING_REVIEW,
        )
        mapped_doc["retention_requirements"] = doc.get("retentionRequirements", None)
        mapped_doc["previous_versions"] = []
        
        # Convert workflowSummary field names from camelCase to snake_case
        # Fixed: Ensure field names match Pydantic model expectations
        workflow_summary = doc.get("workflowSummary", None)
        if workflow_summary:
            mapped_doc["workflow_summary"] = {
                "lifecycle_state": workflow_summary.get("lifecycleState", "INTAKE"),
                "review_overall_status": workflow_summary.get("reviewOverallStatus", "NOT_STARTED"),
                "approval_overall_status": workflow_summary.get("approvalOverallStatus", "NOT_STARTED"),
                "metrics": workflow_summary.get("metrics", {}),
                "last_transition_at": workflow_summary.get("lastTransitionAt", None)
            }
        else:
            mapped_doc["workflow_summary"] = None
        
        # Additional Metadata (matches Node.js)
        mapped_doc["tags"] = doc.get("tags", [])
        mapped_doc["custom_metadata"] = doc.get("customMetadata", {})
        mapped_doc["country"] = doc.get("country", "")
        mapped_doc["site"] = doc.get("site", "")
        
        # Map user fields (Node stores camelCase: createdBy, author, uploadedBy)
        created_by_val = doc.get("createdBy") or doc.get("created_by")
        mapped_doc["created_by"] = str(created_by_val) if created_by_val else ""
        author_val = doc.get("author")
        mapped_doc["author"] = str(author_val) if author_val else ""
        uploaded_by_val = doc.get("uploadedBy") or doc.get("uploaded_by")
        mapped_doc["uploaded_by"] = str(uploaded_by_val) if uploaded_by_val else ""
        
        # Map other fields
        mapped_doc["title"] = doc.get("title", "") or "Untitled"
        mapped_doc["description"] = doc.get("description", "")
        mapped_doc["version"] = _coerce_version(doc.get("version"))
        mapped_doc["language"] = doc.get("language", "en")
        
        # Convert lists of ObjectIds
        if "contributors" in doc:
            mapped_doc["contributors"] = [str(c) for c in doc["contributors"]]
        else:
            mapped_doc["contributors"] = []
        
        # Map audit trail (Node stores camelCase: auditTrail). Ensure ObjectIds are serialized to str.
        raw_audit_trail = doc.get("auditTrail", doc.get("audit_trail", [])) or []
        audit_trail = []
        for item in raw_audit_trail:
            if not isinstance(item, dict):
                continue
            user_val = item.get("user")
            if isinstance(user_val, ObjectId):
                user_val = str(user_val)
            audit_trail.append({
                "action": item.get("action", ""),
                "timestamp": item.get("timestamp") or datetime.now(timezone.utc).replace(tzinfo=None),
                "user": user_val or "",
                "details": item.get("details"),
                "ip_address": item.get("ipAddress") or item.get("ip_address"),
            })
        mapped_doc["audit_trail"] = audit_trail
        
        # TMF hierarchy (Node stores camelCase: zone, section, artifact, subArtifact)
        zone_ref = doc.get("zone")
        mapped_doc["zone"] = str(zone_ref) if zone_ref else None
        section_ref = doc.get("section")
        mapped_doc["section"] = str(section_ref) if section_ref else None
        artifact_ref = doc.get("artifact")
        mapped_doc["artifact"] = str(artifact_ref) if artifact_ref else None
        sub_artifact_ref = doc.get("subArtifact") or doc.get("sub_artifact")
        mapped_doc["sub_artifact"] = str(sub_artifact_ref) if sub_artifact_ref else None
        
        return ISFDocumentResponse(**mapped_doc)
