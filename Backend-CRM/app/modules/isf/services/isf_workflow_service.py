"""
ISF Workflow service - mirrors Node.js isfDocumentWorkflow.service and controller behavior.
Stores/retrieves workflow in MongoDB (isfworkflows collection) and keeps document.workflowRef/workflowSummary in sync.
"""
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from bson import ObjectId

from ..core.workflow_constants import (
    build_default_isf_workflow,
    build_workflow_summary,
    calculate_workflow_metrics,
)

# MongoDB collection names: match Node/Mongoose (ISFWorkflow -> isfworkflows, ISFDocument may be isf_documents or isfdocuments)
DOCUMENTS_COLLECTION = "isf_documents"
WORKFLOWS_COLLECTION = "isfworkflows"


def _serialize_workflow_for_response(doc: dict) -> dict:
    """Convert workflow document for JSON response: ObjectId -> str, datetime -> ISO string."""
    if not doc:
        return doc
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat() if hasattr(v, "isoformat") else str(v)
        elif isinstance(v, dict):
            out[k] = _serialize_workflow_for_response(v)
        elif isinstance(v, list):
            out[k] = [
                _serialize_workflow_for_response(x) if isinstance(x, dict) else
                (x.isoformat() if isinstance(x, datetime) else str(x) if isinstance(x, ObjectId) else x)
                for x in v
            ]
        else:
            out[k] = v
    return out


async def _get_document(db, document_id: str) -> Optional[Tuple[dict, str]]:
    """Get document by _id or documentId. Tries isf_documents then isfdocuments (Node). Returns (doc, collection_name) or None."""
    for coll in (DOCUMENTS_COLLECTION, "isfdocuments"):
        try:
            if ObjectId.is_valid(document_id):
                oid = ObjectId(document_id)
                doc = await db[coll].find_one({"_id": oid})
                if doc:
                    return (doc, coll)
            doc = await db[coll].find_one({"documentId": document_id})
            if doc:
                return (doc, coll)
        except Exception:
            continue
    return None


async def _get_workflow_by_document(db, document_oid: ObjectId) -> Optional[dict]:
    """Get workflow from isfworkflows by document reference (status ACTIVE)."""
    w = await db[WORKFLOWS_COLLECTION].find_one({"document": document_oid, "status": "ACTIVE"})
    return w


async def _get_workflow_by_ref(db, workflow_ref: ObjectId) -> Optional[dict]:
    """Get workflow by its _id."""
    return await db[WORKFLOWS_COLLECTION].find_one({"_id": workflow_ref})


def _ensure_workflow_metrics(workflow: dict) -> dict:
    """Ensure workflow has metrics (recalculate if missing)."""
    if not workflow:
        return workflow
    workflow["metrics"] = calculate_workflow_metrics(workflow)
    return workflow


async def hydrate_workflow_document(
    db, document: dict, user_id: Optional[str] = None, documents_collection: str = None
) -> Tuple[dict, dict]:
    """
    Load or create workflow for document. Returns (document, workflow_doc).
    Updates document's workflowRef and workflowSummary in DB if a new workflow was created.
    documents_collection: name of the documents collection (where to update workflowRef).
    """
    doc_oid = document.get("_id")
    if not doc_oid:
        return document, None
    doc_coll = documents_collection or DOCUMENTS_COLLECTION

    workflow_ref = document.get("workflowRef") or document.get("workflow_ref")
    workflow_doc = None
    if workflow_ref:
        workflow_doc = await _get_workflow_by_ref(db, workflow_ref if isinstance(workflow_ref, ObjectId) else ObjectId(workflow_ref))

    if not workflow_doc:
        # Create new workflow (same as Node hydrateWorkflowDocument)
        initial = build_default_isf_workflow(document)
        initial["document"] = doc_oid
        # Optional: check for legacy embedded workflow
        legacy = await db[doc_coll].find_one(
            {"_id": doc_oid},
            {"workflow": 1}
        )
        if legacy and legacy.get("workflow") and legacy["workflow"].get("lifecycleState"):
            initial = {**initial, **legacy["workflow"], "document": doc_oid}
        workflow_doc = _ensure_workflow_metrics(initial)
        # Insert into isfworkflows (no _id so MongoDB will create one)
        insert_result = await db[WORKFLOWS_COLLECTION].insert_one(workflow_doc)
        workflow_doc["_id"] = insert_result.inserted_id
        workflow_doc["document"] = doc_oid
        # Update metrics again after insert (metrics may have been stripped by insert)
        metrics = calculate_workflow_metrics(workflow_doc)
        await db[WORKFLOWS_COLLECTION].update_one(
            {"_id": insert_result.inserted_id},
            {"$set": {"metrics": metrics}}
        )
        workflow_doc["metrics"] = metrics
        summary = build_workflow_summary(workflow_doc)
        # Update document: set workflowRef and workflowSummary (camelCase for Node compatibility)
        update_doc = {
            "workflowRef": insert_result.inserted_id,
            "workflowSummary": summary,
        }
        # Also set snake_case in case FastAPI document model expects it
        update_doc["workflow_ref"] = insert_result.inserted_id
        update_doc["workflow_summary"] = summary
        await db[doc_coll].update_one(
            {"_id": doc_oid},
            {"$set": update_doc}
        )
        # Push audit trail on document (optional, like Node pushWorkflowAudit)
        audit_entry = {
            "action": "WORKFLOW_INITIALIZED",
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
            "user": ObjectId(user_id) if user_id and ObjectId.is_valid(user_id) else None,
            "details": {"lifecycleState": workflow_doc.get("lifecycleState", "INTAKE")},
            "ipAddress": None
        }
        await db[doc_coll].update_one(
            {"_id": doc_oid},
            {"$push": {"auditTrail": audit_entry}}
        )
        document["workflowRef"] = insert_result.inserted_id
        document["workflowSummary"] = summary

    return document, workflow_doc


class ISFWorkflowService:
    """Service for document workflow get/initialize. Matches Node.js API behavior and response shape."""

    async def get_workflow(self, db, document_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow for document. If none exists, initialize and return.
        Returns serialized workflow dict for response data.
        """
        result = await _get_document(db, document_id)
        if not result:
            return None
        document, doc_coll = result
        doc_oid = document["_id"]
        workflow = await _get_workflow_by_document(db, doc_oid)
        if workflow:
            _ensure_workflow_metrics(workflow)
            return _serialize_workflow_for_response(workflow)
        _, workflow_doc = await hydrate_workflow_document(db, document, user_id, doc_coll)
        if not workflow_doc:
            return None
        return _serialize_workflow_for_response(workflow_doc)

    async def initialize_workflow(self, db, document_id: str, user_id: str) -> Dict[str, Any]:
        """
        Initialize workflow for document (create if not exists). Returns same shape as Node:
        { success: True, message, data: { workflow, auditTrail } }.
        """
        result = await _get_document(db, document_id)
        if not result:
            raise ValueError("Document not found")
        document, doc_coll = result
        _, workflow_doc = await hydrate_workflow_document(db, document, user_id, doc_coll)
        if not workflow_doc:
            raise ValueError("Failed to initialize workflow")
        # Fetch audit trail from document for response (use same collection as document)
        doc_updated = await db[doc_coll].find_one({"_id": document["_id"]}, {"auditTrail": 1, "audit_trail": 1})
        audit_trail = (doc_updated or {}).get("auditTrail") or (doc_updated or {}).get("audit_trail") or []
        return {
            "workflow": _serialize_workflow_for_response(workflow_doc),
            "auditTrail": [
                {
                    **item,
                    "timestamp": item.get("timestamp").isoformat() if hasattr(item.get("timestamp"), "isoformat") else item.get("timestamp"),
                    "user": str(item["user"]) if isinstance(item.get("user"), ObjectId) else item.get("user")
                }
                for item in audit_trail
            ]
        }

    async def update_intake_workflow(self, db, document_id: str, payload: dict, user_id: str) -> Dict[str, Any]:
        """
        Update the INTAKE stage of the workflow and optionally mark it complete.
        """
        result = await _get_document(db, document_id)
        if not result:
            raise ValueError("Document not found")
        document, doc_coll = result
        _, workflow_doc = await hydrate_workflow_document(db, document, user_id, doc_coll)
        if not workflow_doc:
            raise ValueError("Failed to initialize workflow")
        
        intake_data = workflow_doc.get("intake", {})
        
        if "ingestionMethod" in payload:
            intake_data["ingestionMethod"] = payload["ingestionMethod"]
        if "sourceSystem" in payload:
            intake_data["sourceSystem"] = payload["sourceSystem"]
        if "metadataConfidence" in payload:
            intake_data["metadataConfidence"] = payload["metadataConfidence"]
            
        dup_check = payload.get("duplicateCheck", {})
        if dup_check:
            intake_data["duplicateCheck"] = {
                "status": dup_check.get("status", intake_data.get("duplicateCheck", {}).get("status", "PENDING")),
                "matchedDocumentId": dup_check.get("matchedDocumentId", intake_data.get("duplicateCheck", {}).get("matchedDocumentId", "")),
                "checkedAt": datetime.now(timezone.utc).replace(tzinfo=None)
            }
            
        virus_scan = payload.get("virusScan", {})
        if virus_scan:
            intake_data["virusScan"] = {
                "status": virus_scan.get("status", intake_data.get("virusScan", {}).get("status", "PENDING")),
                "engine": virus_scan.get("engine", intake_data.get("virusScan", {}).get("engine", "")),
                "scannedAt": datetime.now(timezone.utc).replace(tzinfo=None)
            }
            
        mv = payload.get("metadataVerification", {})
        if mv:
            intake_data["metadataVerification"] = {
                **intake_data.get("metadataVerification", {}),
                **mv,
                "verifiedAt": datetime.now(timezone.utc).replace(tzinfo=None),
                "verifiedBy": user_id
            }
            
        if "notes" in payload:
            intake_data["notes"] = payload["notes"]

        # Persist markComplete so UI and stage card show correct state after reload
        intake_data["markComplete"] = bool(payload.get("markComplete", False))

        updated_metadata = payload.get("updatedMetadata", {})
        doc_updates = {}
        if updated_metadata:
            for k in ["title", "description", "documentType", "tmfReference", "version", "language", "author", "legibility"]:
                if k in updated_metadata:
                    doc_updates[k] = updated_metadata[k]
                    if k == "legibility": doc_updates["legibilityClear"] = updated_metadata["legibility"]
            
            for k in ["zoneName", "sectionName", "artifactName", "subArtifactName"]:
                if k in updated_metadata: doc_updates[k] = updated_metadata[k]
                
            pc = updated_metadata.get("pageCount")
            if pc is not None and pc != "N/A":
                try: doc_updates["pageCount"] = int(pc)
                except ValueError: pass
                
            custom_tmf = {
                k: updated_metadata.get(k) for k in [
                    "processBasedMetadata", "tmfLevel", "coreOrRecommended",
                    "ichCode", "iso14155Reference", "uniqueIdNumber",
                    "sponsorDocument", "investigatorDocument", "processNumber",
                    "processName", "trialLevelDocument", "countryRegionLevelDocument",
                    "siteLevelDocument"
                ]
            }
            doc_updates["customMetadata.tmfMetadata"] = custom_tmf
            
        if doc_updates:
            doc_updates["lastModifiedBy"] = ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id
            doc_updates["modificationDate"] = datetime.now(timezone.utc).replace(tzinfo=None)
            await db[doc_coll].update_one({"_id": document["_id"]}, {"$set": doc_updates})
            
        workflow_updates = {}
        
        mark_complete = payload.get("markComplete", False)
        if mark_complete:
            intake_data["status"] = "COMPLETED"
            workflow_updates["lifecycleState"] = "QC_VALIDATION"
            if not workflow_doc.get("qcValidation", {}).get("status"):
                workflow_updates["qcValidation"] = workflow_doc.get("qcValidation", {})
                workflow_updates["qcValidation"]["status"] = "IN_PROGRESS"
                
        workflow_updates["intake"] = intake_data
        
        await db[WORKFLOWS_COLLECTION].update_one(
            {"_id": workflow_doc["_id"]},
            {"$set": workflow_updates}
        )
        
        updated_workflow = await db[WORKFLOWS_COLLECTION].find_one({"_id": workflow_doc["_id"]})
        updated_workflow = _ensure_workflow_metrics(updated_workflow)
        
        audit_entry = {
            "action": "INTAKE_COMPLETED" if mark_complete else "INTAKE_UPDATED",
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
            "user": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id,
            "details": {"notes": payload.get("transitionNotes", "")},
            "ipAddress": None
        }
        
        summary = build_workflow_summary(updated_workflow)
        await db[doc_coll].update_one(
            {"_id": document["_id"]},
            {
                "$push": {"auditTrail": audit_entry},
                "$set": {"workflowSummary": summary, "workflow_summary": summary}
            }
        )
        
        doc_updated = await db[doc_coll].find_one({"_id": document["_id"]}, {"auditTrail": 1, "audit_trail": 1})
        audit_trail_data = (doc_updated or {}).get("auditTrail") or (doc_updated or {}).get("audit_trail") or []
        
        return {
            "workflow": _serialize_workflow_for_response(updated_workflow),
            "auditTrail": [
                {
                    **item,
                    "timestamp": item.get("timestamp").isoformat() if hasattr(item.get("timestamp"), "isoformat") else item.get("timestamp"),
                    "user": str(item["user"]) if isinstance(item.get("user"), ObjectId) else item.get("user")
                }
                for item in audit_trail_data
            ]
        }

    async def update_qc_validation_workflow(self, db, document_id: str, payload: dict, user_id: str) -> Dict[str, Any]:
        """
        Update the QC Validation stage. When marked complete: transition to ACTIVATION (not REVIEW_PREPARATION)
        and set document status to APPROVED.
        """
        result = await _get_document(db, document_id)
        if not result:
            raise ValueError("Document not found")
        document, doc_coll = result
        _, workflow_doc = await hydrate_workflow_document(db, document, user_id, doc_coll)
        if not workflow_doc:
            raise ValueError("Failed to initialize workflow")

        qc_data = dict(workflow_doc.get("qcValidation") or {})

        if "status" in payload:
            qc_data["status"] = payload["status"]
        if "qaLead" in payload:
            qc_data["qaLead"] = payload["qaLead"]
        if "reviewer" in payload:
            qc_data["reviewer"] = payload["reviewer"]
        if "qcDecision" in payload:
            qc_data["qcDecision"] = payload["qcDecision"]
        if "qcDecisionNotes" in payload:
            qc_data["qcDecisionNotes"] = payload["qcDecisionNotes"]
        if "reviewStages" in payload:
            qc_data["reviewStages"] = payload["reviewStages"]
        if "checklist" in payload and isinstance(payload.get("checklist"), dict):
            qc_data["checklist"] = {**(qc_data.get("checklist") or {}), **payload["checklist"]}
        if "sponsorPersons" in payload:
            qc_data["sponsorPersons"] = payload["sponsorPersons"]
        if "publicationStatus" in payload:
            qc_data["publicationStatus"] = payload["publicationStatus"]
        if "actualEffectiveDate" in payload:
            qc_data["actualEffectiveDate"] = payload["actualEffectiveDate"]

        qc_data["markComplete"] = bool(payload.get("markComplete", False))
        qc_data["updatedAt"] = datetime.now(timezone.utc).replace(tzinfo=None)
        qc_data["updatedBy"] = user_id

        workflow_updates = {"qcValidation": qc_data}
        mark_complete = payload.get("markComplete", False)
        if mark_complete:
            qc_data["status"] = "COMPLETED"
            # Transition to ACTIVATION (not REVIEW_PREPARATION)
            workflow_updates["lifecycleState"] = "ACTIVATION"
            # Mark review/approval as completed so document is treated as approved (skipped path)
            review = dict(workflow_doc.get("review") or {})
            review["overallStatus"] = "COMPLETED"
            workflow_updates["review"] = review
            approval = dict(workflow_doc.get("approval") or {})
            approval["overallStatus"] = "COMPLETED"
            workflow_updates["approval"] = approval
            rp = dict(workflow_doc.get("reviewPreparation") or {})
            rp["status"] = "COMPLETED"
            workflow_updates["reviewPreparation"] = rp
            activation = dict(workflow_doc.get("activation") or {})
            if not activation.get("status"):
                activation["status"] = "INACTIVE"
            workflow_updates["activation"] = activation

        await db[WORKFLOWS_COLLECTION].update_one(
            {"_id": workflow_doc["_id"]},
            {"$set": workflow_updates}
        )

        updated_workflow = await db[WORKFLOWS_COLLECTION].find_one({"_id": workflow_doc["_id"]})
        updated_workflow = _ensure_workflow_metrics(updated_workflow)

        audit_entry = {
            "action": "QC_VALIDATION_COMPLETED" if mark_complete else "QC_VALIDATION_UPDATED",
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
            "user": ObjectId(user_id) if ObjectId.is_valid(user_id) else user_id,
            "details": {"notes": payload.get("transitionNotes", "")},
            "ipAddress": None
        }
        summary = build_workflow_summary(updated_workflow)
        doc_set = {
            "workflowSummary": summary,
            "workflow_summary": summary,
            "modificationDate": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        if mark_complete:
            doc_set["status"] = "APPROVED"
        await db[doc_coll].update_one(
            {"_id": document["_id"]},
            {"$push": {"auditTrail": audit_entry}, "$set": doc_set}
        )
        doc_updated = await db[doc_coll].find_one({"_id": document["_id"]}, {"auditTrail": 1, "audit_trail": 1})
        audit_trail_data = (doc_updated or {}).get("auditTrail") or (doc_updated or {}).get("audit_trail") or []
        return {
            "workflow": _serialize_workflow_for_response(updated_workflow),
            "auditTrail": [
                {
                    **item,
                    "timestamp": item.get("timestamp").isoformat() if hasattr(item.get("timestamp"), "isoformat") else item.get("timestamp"),
                    "user": str(item["user"]) if isinstance(item.get("user"), ObjectId) else item.get("user")
                }
                for item in audit_trail_data
            ]
        }
