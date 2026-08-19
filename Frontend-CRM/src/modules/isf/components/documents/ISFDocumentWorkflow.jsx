import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Archive,
  BarChart3,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  Clock,
  FileText,
  Fingerprint,
  Hash,
  Layers,
  Mail,
  MapPin,
  PenTool,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  UploadCloud,
  Upload,
  UserPlus,
  Users,
  XCircle,
  Zap,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { useToast } from "@/components/ui/use-toast";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import StageCard from "./workflow/StageCard";
import ComplianceTagList from "./workflow/ComplianceTagList";
import StageActionButtons from "./workflow/StageActionButtons";
import ISFIntakeStageForm from "./workflow/ISFIntakeStageForm";
import ISFQcValidationForm from "./workflow/ISFQcValidationForm";7
import RevisionForm from "./workflow/RevisionForm";
import { toTitleCase } from "./workflow/workflowUtils";
import ISFAIUploadDrawer from "@/components/ai/ISFAIUploadDrawer";
import RightDrawer from "@/components/ui/right-drawer";
import RejectionDialog from "./workflow/RejectionDialog";
import sharedAuthService from "@/services/sharedAuth.service";
import { canOpenWorkflowStage } from "@/config/workflowPermissions";
import isfDocumentWorkflowService from "@/services/isfDocumentWorkflow.service";
import isfDocumentService from "@/services/isfDocument.service";

const STATUS_COPY = {
  completed: { label: "Completed", tone: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  active: { label: "In Progress", tone: "bg-sky-100 text-sky-700 border-sky-200" },
  rejected: { label: "Rejected", tone: "bg-red-100 text-red-700 border-red-200" },
  pending: { label: "Pending", tone: "bg-slate-100 text-slate-600 border-slate-200" },
  gated: { label: "Awaiting Compliance", tone: "bg-amber-100 text-amber-700 border-amber-200" },
};

// QC validation based on decision - simplified to single check (qcDecision)
const QC_CHECKLIST_KEYS = ["qcDecision"];
const QC_STATUS_LABELS = {
  NOT_STARTED: "Pending",
  IN_PROGRESS: "In Review",
  COMPLETED: "Completed",
};
const REVIEW_PREP_CHECKLIST_KEYS = ["qcReportCompiled", "trainingBriefed", "risksLogged"];
const REVIEW_PREP_STATUS_LABELS = {
  NOT_STARTED: "Queued",
  IN_PROGRESS: "Preparing",
  COMPLETED: "Ready",
};

const clampPercentage = (value) => {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
};

const ratioToPercent = (value) => {
  if (!Number.isFinite(value)) return 0;
  return value > 1 ? clampPercentage(value) : clampPercentage(value * 100);
};

const humanizeStatus = (value) => {
  if (!value) return undefined;
  return toTitleCase(String(value).replace(/[\s_-]+/g, " "));
};

const resolveStatusLabel = (statusKey, rawStatus, fallback) =>
  humanizeStatus(rawStatus) || fallback || STATUS_COPY[statusKey]?.label || "Pending";

const formatPercentLabel = (value) => `${clampPercentage(value)}%`;

const formatDateTime = (value) => {
  if (!value) return "Not scheduled";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not scheduled";
  return date.toLocaleString();
};

const STAGE_ACTIONS = {
  INTAKE: {
    primary: { label: "Validate Intake", icon: ClipboardCheck },
    secondary: null,
  },
  QC_VALIDATION: {
    primary: { label: "Review Intake Report", icon: ClipboardList },
    // This opens the QC Validation form where TMF Owner can be assigned
    // secondary: { label: "Assign TMF Owner", icon: UserPlus },
  },
  REVIEW_PREPARATION: {
    primary: { label: "Assign Reviewers", icon: UserPlus },
    secondary: { label: "Prepare Packet", icon: Layers },
    tertiary: { label: "Will remain in 3rd stage (Delegate my reviewer)", icon: Users },
  },
  IN_REVIEW: {
    primary: { label: "Facilitate Review", icon: ClipboardCheck },
    secondary: { label: "Escalate Feedback", icon: AlertTriangle },
  },
  PRE_APPROVAL: {
    primary: { label: "Resolve Findings", icon: PenTool },
    secondary: { label: "Share Summary", icon: Send },
  },
  APPROVAL: {
    primary: { label: "Request Signature", icon: PenTool },
    secondary: { label: "Send Reminder", icon: Send },
  },
  REVIEW: {
    primary: { label: "Manage Review Process", icon: ClipboardCheck },
    secondary: { label: "Request Signatures", icon: Fingerprint },
  },
  ACTIVATION: {
    primary: { label: "Distribute Effective Copy", icon: Send },
    secondary: { label: "Register Training", icon: UserPlus },
  },
  REVISION: {
    primary: { label: "Manage Change & Archive", icon: PenTool },
    secondary: { label: "Archive Document", icon: Archive },
  },
  AUDIT_REPORTING: {
    primary: { label: "Generate Audit Report", icon: FileText },
    secondary: { label: "Share CAPA Log", icon: ShieldCheck },
  },
};

const complianceTags = ["21 CFR Part 11", "QA-Verified", "Audit Ready"];
const HIDDEN_STAGE_KEYS = new Set(["IN_REVIEW", "PRE_APPROVAL", "APPROVAL", "AUDIT_REPORTING"]);

const ISFDocumentWorkflow = ({ document, onWorkflowUpdate, className, layout = "page", onStageOpen: externalOnStageOpen }) => {
  const workflow = useMemo(() => {
    const wf = document?.workflow ?? {};
    return wf;
  }, [document]);
  const currentLifecycle = workflow?.lifecycleState ?? "INTAKE";
  const [showAIUploadDrawer, setShowAIUploadDrawer] = useState(false);
  const [showFullAuditTrail, setShowFullAuditTrail] = useState(false);
  const documentId = document?._id;

  const [studyTitle, setStudyTitle] = useState(document.study);

  // useEffect(() => {
  //   const fetchStudyName = async () => {
  //     if (!document?.study) return;

  //     try {
  //       const fullStudy = await studyService.getStudy(document.study);
  //       setStudyTitle(fullStudy.data?.title);
  //     } catch (err) {
  //       console.error("Failed to fetch study", err);
  //     }
  //   };

  //   fetchStudyName();
  // }, [document?.study]);

  // ===== INTAKE DRAFT STATE (defined early for real-time progress) =====
  const buildIntakeDraftEarly = useCallback(
    (context = {}) => {
      const matchedDocId = context?.duplicateCheck?.matchedDocumentId;
      const matchedDocIdStr = matchedDocId
        ? (typeof matchedDocId === 'object' && matchedDocId.toString ? matchedDocId.toString() : String(matchedDocId))
        : "";
      return {
        ingestionMethod: context?.ingestionMethod || "MANUAL_UPLOAD",
        sourceSystem: context?.sourceSystem || "",
        duplicateStatus: context?.duplicateCheck?.status || document?.duplicateStatus || "CLEAR",
        matchedDocumentId: matchedDocIdStr,
        virusStatus: context?.virusScan?.status || document?.virusStatus || document?.customMetadata?.validation?.virusScan?.status || "PENDING",
        virusEngine: context?.virusScan?.engine || document?.customMetadata?.validation?.virusScan?.engine || "",
        metadataVerification: {
          zoneVerified: context?.metadataVerification?.zoneVerified || false,
          sectionVerified: context?.metadataVerification?.sectionVerified || false,
          artifactVerified: context?.metadataVerification?.artifactVerified || false,
          subArtifactVerified: context?.metadataVerification?.subArtifactVerified || false,
        },
        notes: context?.notes || "",
        markComplete: context?.markComplete || false,
        legibilityClear: document?.legibilityClear || "",
      };
    },
    []
  );

  const [intakeDraftEarly, setIntakeDraftEarly] = useState(() => buildIntakeDraftEarly(workflow?.intake));

  console.log('Initial intakeDraftEarly:', intakeDraftEarly);

  // Sync early draft when workflow changes (also handles reset case)
  useEffect(() => {
    setIntakeDraftEarly(buildIntakeDraftEarly(workflow?.intake));
  }, [workflow?.intake, buildIntakeDraftEarly]);

  // Force re-render when document or workflow changes significantly
  useEffect(() => {
    // This effect ensures component updates when document/workflow data changes
    // The dependency on workflow lifecycleState will trigger re-render on state changes
    if (workflow?.lifecycleState) {
      console.log('🔄 DocumentWorkflow: Workflow state changed to', workflow.lifecycleState);
    }
  }, [workflow?.lifecycleState, document?._id, document?.workflow?.lifecycleState]);

  // Real-time Intake metrics calculated from draft (for card display)
  const intakeMetricsFromDraft = useMemo(() => {
    const draft = intakeDraftEarly;
    // const draft = intakeDraftEarly;

    // Security checks (weight: 50% - most important for intake)
    const duplicateComplete = draft?.duplicateStatus === "CLEAR";
    const virusComplete = draft?.virusStatus === "CLEAN";
    const securityChecksComplete = [duplicateComplete, virusComplete].filter(Boolean).length;
    const securityContribution = (securityChecksComplete / 2) * 50;

    // Metadata verification (weight: 30%)
    const metadataVerification = draft?.metadataVerification || {};
    const hasZone = !!document?.zone;
    const hasSection = !!document?.section;
    const hasArtifact = !!document?.artifact;
    const hasSubArtifact = !!document?.subArtifact;
    const totalMetadataItems = [hasZone, hasSection, hasArtifact, hasSubArtifact].filter(Boolean).length;
    const verifiedMetadataItems = [
      hasZone && metadataVerification.zoneVerified,
      hasSection && metadataVerification.sectionVerified,
      hasArtifact && metadataVerification.artifactVerified,
      hasSubArtifact && metadataVerification.subArtifactVerified,
    ].filter(Boolean).length;
    // Only count verified items, not just presence of metadata
    // If metadata exists but isn't verified, don't count it toward progress
    const metadataContribution = totalMetadataItems > 0 && verifiedMetadataItems > 0
      ? (verifiedMetadataItems / totalMetadataItems) * 30
      : 0;
    // Adjust total weight when no metadata
    const adjustedSecurityWeight = totalMetadataItems > 0 ? 50 : 80; // If no TMF, security is 80%
    const adjustedSecurityContribution = (securityChecksComplete / 2) * adjustedSecurityWeight;

    // Ingestion info (weight: 20%)
    // Only count ingestionMethod if it's been explicitly set (not just the default)
    // Check if it exists in the backend workflow data, meaning it was saved
    const ingestionMethodFromBackend = workflow?.intake?.ingestionMethod;
    const hasIngestionMethod = ingestionMethodFromBackend && ingestionMethodFromBackend !== "";
    // Source system is optional, so ingestionMethod alone gives full credit
    // Only count ingestion if ingestionMethod was explicitly set (saved to backend)
    const ingestionContribution = hasIngestionMethod
      ? 20 // Give full 20% if ingestionMethod is set (sourceSystem is optional)
      : 0; // If ingestionMethod not explicitly set, don't count ingestion at all

    // Pending checks
    const duplicatePending = draft?.duplicateStatus !== "CLEAR";
    const virusPending = draft?.virusStatus !== "CLEAN";
    const metadataVerificationPending = [
      hasZone && !metadataVerification.zoneVerified,
      hasSection && !metadataVerification.sectionVerified,
      hasArtifact && !metadataVerification.artifactVerified,
      hasSubArtifact && !metadataVerification.subArtifactVerified,
    ].filter(Boolean).length;
    const pendingChecks = [duplicatePending, virusPending].filter(Boolean).length + metadataVerificationPending;

    // Use adjusted security contribution when no metadata
    const finalProgress = totalMetadataItems > 0
      ? Math.round(securityContribution + metadataContribution + ingestionContribution)
      : Math.round(adjustedSecurityContribution + ingestionContribution);

    return {
      progress: finalProgress,
      pendingChecks,
    };
  }, [intakeDraftEarly, workflow?.intake?.ingestionMethod, document?.zone, document?.section, document?.artifact, document?.subArtifact]);

  // Debug: Log documentId availability
  React.useEffect(() => {
    if (typeof window !== 'undefined') {
      console.log('DocumentWorkflow - documentId:', documentId);
      console.log('DocumentWorkflow - document:', document);
    }
  }, [documentId, document]);

  // Fetch audit trail from API
  const { data: apiAuditTrail = [], isLoading: isLoadingAuditTrail, error: auditTrailError, refetch: refetchAuditTrail } = useQuery({
    queryKey: ['document-audit-trail', documentId],
    queryFn: async () => {
      if (!documentId) {
        console.warn('No documentId provided to fetch audit trail');
        return [];
      }
      console.log('Fetching audit trail for document:', documentId);
      try {
        const result = await isfDocumentService.getAuditTrail(documentId);
        console.log('Audit trail result:', result);
        return result;
      } catch (error) {
        console.error('Error in queryFn for audit trail:', error);
        throw error;
      }
    },
    enabled: !!documentId,
    staleTime: 30000, // 30 seconds
    retry: 1,
    refetchOnWindowFocus: false,
    refetchOnMount: true,
    onError: (error) => {
      console.error('Error fetching audit trail:', error);
      console.error('Error details:', error.response?.data || error.message);
      console.error('Error status:', error.response?.status);
      console.error('Error URL:', error.config?.url);
    },
    onSuccess: (data) => {
      console.log('Audit trail fetched successfully:', data);
      console.log('Number of entries:', data?.length || 0);
    },
  });

  // Debug: Log query state
  React.useEffect(() => {
    console.log('Audit Trail Query State:', {
      documentId,
      enabled: !!documentId,
      isLoading: isLoadingAuditTrail,
      hasData: Array.isArray(apiAuditTrail) && apiAuditTrail.length > 0,
      dataLength: apiAuditTrail?.length || 0,
      error: auditTrailError,
    });
  }, [documentId, isLoadingAuditTrail, apiAuditTrail, auditTrailError]);

  const auditTrailEntries = useMemo(() => {
    // Debug logging
    if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
      console.log('Audit Trail Debug:', {
        apiAuditTrail,
        apiAuditTrailLength: apiAuditTrail?.length,
        documentAuditTrail: document?.auditTrail,
        documentAuditTrailLength: document?.auditTrail?.length,
        isLoadingAuditTrail,
        auditTrailError,
        hasApiData: !isLoadingAuditTrail && !auditTrailError && Array.isArray(apiAuditTrail),
      });
    }

    // Priority 1: Use API audit trail if query has completed successfully
    // If API returns empty array, that's valid - return empty (don't show synthetic data)
    if (!isLoadingAuditTrail && !auditTrailError && Array.isArray(apiAuditTrail)) {
      return apiAuditTrail.map((entry) => {
        const user = entry.user;
        const details = entry.details || {};
        // Prefer explicit display names from audit details, then user object, then fallbacks
        const explicitName =
          details.userName ||
          details.actorName ||
          details.performedByName ||
          details.rejectedByName;

        const nameFromUser =
          user &&
          (`${user.firstName || ''} ${user.lastName || ''}`.trim() || user.email || null);

        return {
          action: entry.action,
          timestamp: entry.timestamp,
          details,
          actor: explicitName || nameFromUser || 'System',
          user,
          ipAddress: entry.ipAddress,
        };
      });
    }

    // Priority 2: While loading, show document auditTrail if available
    if (isLoadingAuditTrail && Array.isArray(document?.auditTrail) && document.auditTrail.length > 0) {
      return document.auditTrail.map((entry) => ({
        action: entry.action,
        timestamp: entry.timestamp,
        details: entry.details,
        actor: entry.user?.firstName && entry.user?.lastName
          ? `${entry.user.firstName} ${entry.user.lastName}`
          : entry.user?.email || 'System',
        user: entry.user,
        ipAddress: entry.ipAddress,
      }));
    }

    // Priority 3: Only show synthetic entries if API query failed
    // DO NOT show synthetic entries if API returned empty array (that means no real audit data exists)
    if (auditTrailError) {
      // Build synthetic entries from workflow data as fallback only on error
      const syntheticEntries = [];

      if (Array.isArray(workflow?.stateHistory) && workflow.stateHistory.length > 0) {
        syntheticEntries.push(
          ...workflow.stateHistory.map((event) => ({
            action: `State transition: ${event.fromState || 'Unknown'} → ${event.toState || 'Unknown'}`,
            timestamp: event.changedAt,
            details: event.notes || `Workflow state changed from ${event.fromState} to ${event.toState}`,
            actor: event.actor || "System",
          }))
        );
      }

      if (Array.isArray(workflow?.qcValidation?.auditLog) && workflow.qcValidation.auditLog.length > 0) {
        syntheticEntries.push(
          ...workflow.qcValidation.auditLog.map((entry) => ({
            action: entry.action || "QC validation update",
            timestamp: entry.timestamp,
            details: entry.notes,
            actor: entry.actor || "QA Team",
          }))
        );
      }

      if (Array.isArray(workflow?.reviewPreparation?.auditLog) && workflow.reviewPreparation.auditLog.length > 0) {
        syntheticEntries.push(
          ...workflow.reviewPreparation.auditLog.map((entry) => ({
            action: entry.action || "Review preparation update",
            timestamp: entry.timestamp,
            details: entry.notes,
            actor: entry.actor || "Review Coordination",
          }))
        );
      }

      if (syntheticEntries.length > 0) {
        return syntheticEntries
          .filter((entry) => entry.timestamp)
          .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
      }
    }

    // Fallback: Return empty array if no audit data
    return [];
  }, [apiAuditTrail, isLoadingAuditTrail, auditTrailError, document?.auditTrail, workflow?.stateHistory, workflow?.qcValidation?.auditLog, workflow?.reviewPreparation?.auditLog]);

  // qcSummary now accepts an optional override checklist for real-time updates
  const createQcSummary = useCallback((overrideChecklist = null) => {
    const section = workflow?.qcValidation || {};
    const decision = section.qcDecision;
    const completed = decision ? 1 : 0;
    const progress = decision ? 100 : 0;

    return {
      section,
      checklist: { qcDecision: decision },
      completed,
      progress,
      status: (section.status || "NOT_STARTED").toUpperCase(),
    };
  }, [workflow?.qcValidation]);

  // Base qcSummary from server data
  const qcSummary = useMemo(() => createQcSummary(), [createQcSummary]);

  // Pull the most recent review/approval/consolidation payloads. Some responses
  // embed them directly on workflow, others nest under workflow.details, and
  // older entries may only be present on auditTrail.details.updates.*
  const latestReviewApprovalUpdate = useMemo(() => {
    const auditEntries = Array.isArray(document?.auditTrail) ? document.auditTrail : [];
    for (let i = auditEntries.length - 1; i >= 0; i -= 1) {
      const entry = auditEntries[i];
      const updates = entry?.details?.updates;
      if (updates?.review || updates?.approval || updates?.consolidation) {
        // Debug log
        if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
          console.log('[ISFDocumentWorkflow] latestReviewApprovalUpdate found at index', i, {
            action: entry?.action,
            timestamp: entry?.timestamp,
            reviewNotes: updates?.review?.notes,
            approvalNotes: updates?.approval?.notes,
            consolidationStatus: updates?.consolidation?.status,
          });
        }
        return updates;
      }
    }
    return null;
  }, [document?.auditTrail]);

  // Helper to merge objects, preferring non-null/non-empty values from updates
  const mergePreferNonNull = (base, updates) => {
    const merged = { ...(base || {}) };
    for (const [key, value] of Object.entries(updates || {})) {
      // Arrays should be replaced entirely if present in updates
      if (Array.isArray(value)) {
        if (value.length > 0) {
          merged[key] = value;
        } else if (merged[key] === undefined) {
          merged[key] = value;
        }
      } else if (value !== null && value !== undefined && value !== "") {
        merged[key] = value;
      } else if (merged[key] === undefined) {
        merged[key] = value;
      }
    }
    return merged;
  };

  // Resolve review/approval/consolidation data regardless of where backend placed them.
  const resolvedReviewData = useMemo(() => {
    const direct =
      workflow?.review ||
      workflow?.details?.review ||
      workflow?.details?.updates?.review ||
      null;

    const updates = latestReviewApprovalUpdate?.review || {};

    // Merge, preferring non-null values
    const merged = mergePreferNonNull(direct, updates);

    // Debug log
    if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
      console.log('[ISFDocumentWorkflow] resolvedReviewData:', {
        direct,
        updates,
        merged,
        notes: merged.notes,
        stages: merged.stages?.length,
      });
    }

    return merged;
  }, [workflow, latestReviewApprovalUpdate]);

  const resolvedApprovalData = useMemo(() => {
    const direct =
      workflow?.approval ||
      workflow?.details?.approval ||
      workflow?.details?.updates?.approval ||
      null;

    const updates = latestReviewApprovalUpdate?.approval || {};

    // Merge, preferring non-null values
    const merged = mergePreferNonNull(direct, updates);

    // Debug log
    if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
      console.log('[ISFDocumentWorkflow] resolvedApprovalData:', {
        direct,
        updates,
        merged,
        notes: merged.notes,
        stages: merged.stages?.length,
      });
    }

    return merged;
  }, [workflow, latestReviewApprovalUpdate]);

  const resolvedConsolidationData = useMemo(() => {
    const direct =
      workflow?.review?.consolidation ||
      workflow?.consolidation ||
      workflow?.details?.consolidation ||
      workflow?.details?.updates?.consolidation ||
      null;

    const updates = latestReviewApprovalUpdate?.consolidation || {};

    // Merge, preferring non-null values
    const merged = mergePreferNonNull(direct, updates);

    // Debug log
    if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
      console.log('[ISFDocumentWorkflow] resolvedConsolidationData:', {
        direct,
        updates,
        merged,
        status: merged.status,
        notes: merged.notes,
        findingsResolved: merged.findingsResolved,
      });
    }

    return merged;
  }, [workflow, latestReviewApprovalUpdate]);

  const reviewPrepSummary = useMemo(() => {
    const section = workflow?.reviewPreparation || {};
    const checklist = section.checklist || {};
    const completed = REVIEW_PREP_CHECKLIST_KEYS.reduce((acc, key) => acc + (checklist[key] ? 1 : 0), 0);
    const progress = REVIEW_PREP_CHECKLIST_KEYS.length
      ? Math.round((completed / REVIEW_PREP_CHECKLIST_KEYS.length) * 100)
      : 0;

    return {
      section,
      checklist,
      completed,
      progress,
      status: (section.status || "NOT_STARTED").toUpperCase(),
    };
  }, [workflow?.reviewPreparation]);

  // Review & Approval draft state (declared early so it can be used in stageSequence)
  const buildReviewApprovalDraft = useCallback((reviewData = {}, approvalData = {}, consolidationData = {}) => {
    // Check for rejection/return status
    const reviewRejection = reviewData?.rejection;
    const approvalRejection = approvalData?.rejection;
    const actionType = reviewRejection || approvalRejection
      ? (reviewRejection?.category === 'RETURNED' || approvalRejection?.category === 'RETURNED' ? 'requestChanges' : 'reject')
      : null;
    const actionNotes = reviewRejection?.reason || approvalRejection?.reason || null;

    // Consolidation can come from either consolidationData (top-level) or reviewData.consolidation (nested)
    const consolidation = consolidationData?.status ? consolidationData : reviewData?.consolidation || {};

    return {
      reviewStages: reviewData?.stages || [],
      reviewNotes: reviewData?.notes || "",
      delegateReviewer: reviewData?.delegateReviewer || reviewData?.delegatedReviewer || "",
      consolidationStatus: consolidation?.status || "NOT_STARTED",
      findingsResolved: consolidation?.findingsResolved || false,
      consolidationNotes: consolidation?.notes || "",
      initialInReviewDate: reviewData?.initialInReviewDate || null,
      initialSteadyStateDate: consolidation?.initialSteadyStateDate || reviewData?.initialSteadyStateDate || null,
      reviewCyclesCount: reviewData?.reviewCyclesCount || 0,
      consolidationCompletedDate: consolidation?.consolidationCompletedDate || null,
      approvalStages: approvalData?.stages || [],
      approvalNotes: approvalData?.notes || "",
      actionType: actionType || null,
      actionNotes: actionNotes || null,
    };
  }, []);

  const [reviewApprovalDraft, setReviewApprovalDraft] = useState(() =>
    buildReviewApprovalDraft(resolvedReviewData, resolvedApprovalData, resolvedConsolidationData)
  );

  // Build functions for draft states (declared early so they can be used in draft state initialization)
  const buildIntakeDraft = useCallback(
    (context = {}) => {
      // Convert ObjectId to string if needed
      const matchedDocId = context?.duplicateCheck?.matchedDocumentId;
      const matchedDocIdStr = matchedDocId
        ? (typeof matchedDocId === 'object' && matchedDocId.toString ? matchedDocId.toString() : String(matchedDocId))
        : "";

      const docType = document?.documentType ?? document?.document_type;
      const tmfRef = document?.tmfReference ?? document?.tmf_reference;
      const docDate = document?.documentDate ?? document?.document_date;
      const pageCount = document?.pageCount ?? document?.page_count;
      const legibility = document?.legibilityClear ?? document?.legibility_clear;

      return {
        // Document Metadata
        documentTitle: context?.documentTitle || document?.title || document?.documentTitle || "",
        title: context?.title || document?.title || document?.documentTitle || "",
        description: context?.description || document?.description || "",
        documentType: context?.documentType || docType || "",
        tmfReference: context?.tmfReference || tmfRef || "",
        version: context?.version || document?.version || "1.0",
        documentDate: context?.documentDate || docDate || null,
        language: context?.language || document?.language || "en",
        author: context?.author || document?.author || "",
        accessLevel: context?.accessLevel || document?.accessLevel || "Restricted",
        status: context?.status || document?.status || "Draft",
        pageCount: context?.pageCount ?? pageCount ?? "",

        // TMF Hierarchy
        zoneNumber: context?.zoneNumber || document?.zoneNumber || "",
        zoneName: context?.zoneName || document?.zoneName || "",
        zoneDescription: context?.zoneDescription || document?.zoneDescription || "",
        sectionNumber: context?.sectionNumber || document?.sectionNumber || "",
        sectionName: context?.sectionName || document?.sectionName || "",
        sectionDescription: context?.sectionDescription || document?.sectionDescription || "",
        artifactNumber: context?.artifactNumber || document?.artifactNumber || "",
        artifactName: context?.artifactName || document?.artifactName || "",
        artifactDescription: context?.artifactDescription || document?.artifactDescription || "",
        subArtifactName: context?.subArtifactName || document?.subArtifactName || "",
        mandatory: context?.mandatory ?? document?.mandatory ?? false,

        // Study & Site Context
        study: context?.study || document?.study || "",
        site: context?.site || document?.site || "",
        country: context?.country || document?.country || "",
        indication: context?.indication || document?.indication || "",

        // TMF Metadata & Regulatory
        processBasedMetadata: context?.processBasedMetadata || document?.processBasedMetadata || "",
        coreOrRecommended: context?.coreOrRecommended || document?.coreOrRecommended || "",
        ichCode: context?.ichCode || document?.ichCode || "",
        iso14155Reference: context?.iso14155Reference || document?.iso14155Reference || "",
        uniqueIdNumber: context?.uniqueIdNumber || document?.uniqueIdNumber || "",
        regulatoryAuthority: context?.regulatoryAuthority || document?.regulatoryAuthority || "",
        gcpComplianceStatus: context?.gcpComplianceStatus || document?.gcpComplianceStatus || "PENDING_REVIEW",
        sponsorDocument: context?.sponsorDocument ?? document?.sponsorDocument ?? false,
        investigatorDocument: context?.investigatorDocument ?? document?.investigatorDocument ?? false,

        // Lifecycle & Retention
        effectiveDate: context?.effectiveDate || document?.effectiveDate || null,
        expirationDate: context?.expirationDate || document?.expirationDate || null,
        approvalDate: context?.approvalDate || document?.approvalDate || null,
        qualityControlStatus: context?.qualityControlStatus || document?.qualityControlStatus || "PENDING",
        completenessStatus: context?.completenessStatus || document?.completenessStatus || "PENDING_REVIEW",
        archivalStatus: context?.archivalStatus || document?.archivalStatus || "ACTIVE",
        retentionDuration: context?.retentionDuration || document?.retentionDuration || "",
        retentionStartDate: context?.retentionStartDate || document?.retentionStartDate || null,
        retentionEndDate: context?.retentionEndDate || document?.retentionEndDate || null,

        // Process & Milestones
        processNumber: context?.processNumber || document?.processNumber || "",
        processName: context?.processName || document?.processName || "",
        trialLevelDocument: context?.trialLevelDocument ?? document?.trialLevelDocument ?? false,
        trialLevelMilestoneEvent: context?.trialLevelMilestoneEvent || document?.trialLevelMilestoneEvent || "",
        countryRegionLevelDocument: context?.countryRegionLevelDocument ?? document?.countryRegionLevelDocument ?? false,
        countryLevelMilestoneEvent: context?.countryLevelMilestoneEvent || document?.countryLevelMilestoneEvent || "",
        siteLevelDocument: context?.siteLevelDocument ?? document?.siteLevelDocument ?? false,
        siteLevelMilestoneEvent: context?.siteLevelMilestoneEvent || document?.siteLevelMilestoneEvent || "",

        // Ingestion & Workflow
        ingestionMethod: context?.ingestionMethod || "MANUAL_UPLOAD",
        sourceSystem: context?.sourceSystem || "",
        metadataConfidence: Math.round((context?.metadataConfidence ?? 0) * 100),
        duplicateStatus: context?.duplicateCheck?.status ?? document?.duplicateStatus ?? document?.duplicate_status ?? "PENDING",
        matchedDocumentId: matchedDocIdStr,
        duplicateNotes: context?.duplicateCheck?.notes || "",
        virusStatus: context?.virusScan?.status ?? document?.virusStatus ?? document?.virus_status ?? document?.customMetadata?.validation?.virusScan?.status ?? document?.custom_metadata?.validation?.virusScan?.status ?? "PENDING",
        virusEngine: context?.virusScan?.engine ?? document?.customMetadata?.validation?.virusScan?.engine ?? document?.custom_metadata?.validation?.virusScan?.engine ?? "",
        virusScanNotes: context?.virusScan?.notes || "",

        metadataVerification: {
          zoneVerified: context?.metadataVerification?.zoneVerified || false,
          sectionVerified: context?.metadataVerification?.sectionVerified || false,
          artifactVerified: context?.metadataVerification?.artifactVerified || false,
          subArtifactVerified: context?.metadataVerification?.subArtifactVerified || false,
        },
        notes: context?.notes || "",
        markComplete: context?.markComplete || false,
        transitionNotes: "",
        legibilityClear: legibility ?? "",
      };
    },
    [
      document?.protocolId,
      document?.site,
      document?.tmfReference,
      document?.tmf_reference,
      document?.legibilityClear,
      document?.legibility_clear,
      document?.virusStatus,
      document?.virus_status,
      document?.customMetadata?.validation?.virusScan?.status,
      document?.custom_metadata?.validation?.virusScan?.status,
      document?.duplicateStatus,
      document?.duplicate_status,
    ]
  );

  // --- UPDATE THIS SECTION IN ISFDocumentWorkflow.jsx ---
  const buildQcDraft = useCallback(
    (context = {}) => {
      // 1. Correctly define the variable to avoid the ReferenceError
      const existingRouting = (context?.sponsorPersons && context.sponsorPersons.length > 0)
        ? context.sponsorPersons[0]
        : {};

      return {
        qaLead: context?.qaLead || "",
        reviewer: context?.reviewer || "",
        qcDecision: context?.qcDecision || null,
        qcDecisionNotes: context?.qcDecisionNotes || "",
        actualEffectiveDate: context?.actualEffectiveDate || "",
        publicationStatus: context?.publicationStatus || 'UNPUBLISHED',
        markComplete: false,
        transitionNotes: "",

        // 2. Flatten the nested data so QcValidationForm can read it easily
        sendToTmf: existingRouting.sendToTmf?.isEnabled || false,
        tmfEmail: existingRouting.sendToTmf?.routingEmail || "",
        sendToSafety: existingRouting.sendToSafety?.isEnabled || false,
        safetyEmail: existingRouting.sendToSafety?.safetyEmail || "",
        safetyCcEmails: existingRouting.sendToSafety?.ccList || [],

        sponsorPersons: context?.sponsorPersons || [],
      };
    },
    []
  );

  const formatDateInput = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const iso = date.toISOString();
    return iso.slice(0, 16);
  };

  const buildReviewPrepDraft = useCallback((context = {}) => {
    return {
      coordinator: context?.coordinator || "",
      primaryReviewer: context?.primaryReviewer || "",
      delegateReviewer: context?.delegateReviewer || "",
      backupReviewer: context?.backupReviewer || "",
      meetingScheduledAt: formatDateInput(context?.meetingScheduledAt),
      supportingPacketUrl: context?.supportingPacketUrl || "",
      notes: context?.notes || "",
      checklist: REVIEW_PREP_CHECKLIST_KEYS.reduce(
        (acc, key) => ({
          ...acc,
          [key]: Boolean(context?.checklist?.[key]),
        }),
        {}
      ),
      approvalDate: context?.approvalDate || null,
      actionType: context?.actionType || null,
      actionNotes: context?.actionNotes || null,
      markComplete: context?.actionType === "approve",
    };
  }, []);

  const buildActivationDraft = useCallback((context = {}) => {
    const formatDate = (date) => {
      if (!date) return "";
      const d = new Date(date);
      if (Number.isNaN(d.getTime())) return "";
      return d.toISOString().split("T")[0];
    };

    return {
      actualEffectiveDate: formatDate(context?.actualEffectiveDate),
      status: context?.status || (context?.isActive ? "ACTIVE" : "INACTIVE"),
      isActive: context?.isActive !== undefined ? context.isActive : (context?.status === "ACTIVE"),
      distributionStatus: context?.distributionStatus || "NOT_STARTED",
      trainingStatus: context?.trainingStatus || "NOT_STARTED",
      notes: context?.notes || "",
      dateEditComment: context?.dateEditComment || null,
      // Publish/Retire fields
      publishedAt: context?.publishedAt || null,
      publishedBy: context?.publishedBy || null,
      retiredAt: context?.retiredAt || null,
      retiredBy: context?.retiredBy || null,
      retireReason: context?.retireReason || null,
    };
  }, []);

  const buildRevisionDraft = useCallback((context = {}) => {
    const formatDate = (date) => {
      if (!date) return "";
      const d = new Date(date);
      if (Number.isNaN(d.getTime())) return "";
      return d.toISOString().split("T")[0];
    };

    return {
      // Start with no decision selected so Stage 5 does not appear
      // as "completed" before the user explicitly chooses YES/NO.
      documentRevision: context?.documentRevision ?? "",
      archiveOlderVersion: context?.archiveOlderVersion ?? "",
      archiveStatus: context?.archiveStatus || null,
      archiveDate: formatDate(context?.archiveDate),
      requiresChange: context?.requiresChange || false,
      notes: context?.notes || "",
    };
  }, []);

  // Declare draft states early so they can be used in metrics calculations
  const [intakeDraft, setIntakeDraft] = useState(() => buildIntakeDraft(workflow?.intake));
  const [qcDraft, setQcDraft] = useState(() => buildQcDraft(workflow?.qcValidation));
  const [reviewPrepDraft, setReviewPrepDraft] = useState(() => buildReviewPrepDraft(workflow?.reviewPreparation));
  const [activationDraft, setActivationDraft] = useState(() => buildActivationDraft(workflow?.activation));
  const [revisionDraft, setRevisionDraft] = useState(() => buildRevisionDraft(workflow?.revision));

  // Real-time QC Validation metrics based on draft (declared early for use in stageSequence)
  const qcDraftMetrics = useMemo(() => {
    // QC metric is balanced 50/50 between QC decision and publication status
    const decisionDone = qcDraft?.qcDecision ? 1 : 0;
    const pubDone = (qcDraft?.publicationStatus === 'PUBLISHED') ? 1 : 0;
    const completed = decisionDone + pubDone;
    const total = 2; // decision + publication
    const progress = total > 0 ? Math.round((completed / total) * 100) : 0;

    return {
      progress,
      completed,
      total,
      publicationStatus: qcDraft?.publicationStatus || 'UNPUBLISHED',
      qaLead: qcDraft?.qaLead || "",
    };
  }, [qcDraft]);

  // Real-time Review Preparation metrics based on draft (declared early for use in stageSequence)
  const reviewPrepDraftMetrics = useMemo(() => {
    const checklist = reviewPrepDraft?.checklist || {};
    const completed = REVIEW_PREP_CHECKLIST_KEYS.reduce((acc, key) => acc + (checklist[key] ? 1 : 0), 0);
    const total = REVIEW_PREP_CHECKLIST_KEYS.length;
    const progress = total > 0 ? Math.round((completed / total) * 100) : 0;

    // Count assigned reviewers
    const hasCoordinator = !!reviewPrepDraft?.coordinator?.trim();
    const hasPrimaryReviewer = !!reviewPrepDraft?.primaryReviewer?.trim();
    const hasBackupReviewer = !!reviewPrepDraft?.backupReviewer?.trim();
    const reviewersAssigned = [hasCoordinator, hasPrimaryReviewer, hasBackupReviewer].filter(Boolean).length;

    return {
      progress,
      completed,
      total,
      reviewersAssigned,
      meetingScheduledAt: reviewPrepDraft?.meetingScheduledAt || null,
    };
  }, [reviewPrepDraft]);

  // Real-time Activation metrics based on draft (declared early for use in stageSequence)
  const activationDraftMetrics = useMemo(() => {
    const activation = activationDraft || {};

    // Logical progress calculation based on workflow steps:
    // Step 1: Activation date set (30%) - Required to activate
    // Step 2: Document activated (20%) - Status must be ACTIVE
    // Step 3: Distribution completed (25%) - Must be sent to sites
    // Step 4: Training completed (25%) - Training must be completed

    let progress = 0;

    // Step 1: Activation date (30%)
    if (activation.actualEffectiveDate && activation.actualEffectiveDate.trim() !== "") {
      progress += 30;
    }

    // Step 2: Document activated (20%)
    if (activation.status === "ACTIVE" || activation.isActive === true) {
      progress += 20;
    }

    // Step 3: Distribution completed (25%)
    if (activation.distributionStatus === "COMPLETED") {
      progress += 25;
    } else if (activation.distributionStatus === "IN_PROGRESS") {
      progress += 12.5; // Half credit for in progress
    }

    // Step 4: Training completed (25%)
    if (activation.trainingStatus === "COMPLETED") {
      progress += 25;
    } else if (activation.trainingStatus === "IN_PROGRESS") {
      progress += 12.5; // Half credit for in progress
    }

    progress = Math.min(Math.round(progress), 100);

    return {
      progress,
      completed: Math.round(progress / 25), // Approximate completed steps
      total: 4, // Four logical steps
      actualEffectiveDate: activation.actualEffectiveDate || null,
      status: activation.status || (activation.isActive ? "ACTIVE" : "INACTIVE"),
      distributionStatus: activation.distributionStatus || "NOT_STARTED",
      trainingStatus: activation.trainingStatus || "NOT_STARTED",
    };
  }, [activationDraft]);

  // Real-time Revision metrics based on draft (declared early for use in stageSequence)
  const revisionDraftMetrics = useMemo(() => {
    const revision = revisionDraft || {};

    // Logical progress calculation based on workflow:
    // If no decision made (empty): 0% (not started)
    // If NO revision needed: 100% (complete - no action required)
    // If YES revision needed:
    //   - If archiveOlderVersion is NO: 100% (decision made, no archiving needed - complete)
    //   - If archiveOlderVersion is YES: 
    //     * Archive status and date both set: 100% (complete)
    //     * Only one set: 50% (partial)
    //     * Neither set: 0% (incomplete)

    // Don't default to "NO" - use empty string if not set
    const documentRevision = revision.documentRevision || "";
    const archiveOlderVersion = revision.archiveOlderVersion || "";

    let progress = 0;

    // If no decision made yet, progress is 0%
    if (!documentRevision || documentRevision === "") {
      progress = 0;
    } else if (documentRevision === "NO") {
      // If NO revision needed, stage is complete
      progress = 100;
    } else if (documentRevision === "YES") {
      // If archive decision is not made yet, progress is partial
      if (!archiveOlderVersion || archiveOlderVersion === "") {
        progress = 50; // Decision made to revise, but archive decision pending
      } else if (archiveOlderVersion === "NO") {
        // If archive decision is NO, stage is complete (no archiving needed)
        progress = 100;
      } else if (archiveOlderVersion === "YES") {
        // If archiving, both archiveStatus and archiveDate must be set
        const hasArchiveStatus = revision.archiveStatus && revision.archiveStatus.trim() !== "";
        const hasArchiveDate = revision.archiveDate && revision.archiveDate !== null && revision.archiveDate !== "";

        if (hasArchiveStatus && hasArchiveDate) {
          progress = 100; // Both required fields complete
        } else if (hasArchiveStatus || hasArchiveDate) {
          progress = 50; // One of two fields complete
        } else {
          progress = 33; // Archive decision made but fields incomplete
        }
      }
    }

    progress = Math.min(Math.round(progress), 100);

    return {
      progress,
      completed: documentRevision === "NO" ? 1 : (archiveOlderVersion === "NO" ? 1 : (archiveOlderVersion === "YES" && revision.archiveStatus && revision.archiveDate ? 1 : 0)),
      total: 1,
      documentRevision: documentRevision,
      archiveOlderVersion: archiveOlderVersion,
      archiveStatus: revision.archiveStatus || null,
      archiveDate: revision.archiveDate || null,
      requiresChange: revision.requiresChange || false,
    };
  }, [revisionDraft]);

  const stageSequence = useMemo(() => {
    const workflowMetrics = workflow?.metrics ?? {};
    const reviewStages = workflow?.review?.stages ?? [];
    const approvalStages = workflow?.approval?.stages ?? [];
    const overdue = workflowMetrics?.overdueCount ?? 0;

    // Blocker checks per stage to prevent 100% if required items are missing
    const getStageBlockers = (stageKey) => {
      const blockers = [];
      if (stageKey === "INTAKE") {
        if (workflow?.intake?.duplicateCheck?.status !== "CLEAR") blockers.push("Duplicate check must be CLEAR");
        if (workflow?.intake?.virusScan?.status !== "CLEAN") blockers.push("Virus scan must be CLEAN");
        if (workflow?.intake?.markComplete !== true) blockers.push("Mark intake complete");
      } else if (stageKey === "QC_VALIDATION") {
        if (workflow?.qcValidation?.status !== "COMPLETED") blockers.push("QC status must be COMPLETED");
        if (workflow?.qcValidation?.markComplete !== true) blockers.push("Mark QC complete");
      } else if (stageKey === "REVIEW_PREPARATION") {
        const prep = workflow?.reviewPreparation || {};
        if (!prep.primaryReviewer || prep.primaryReviewer.trim().length === 0) blockers.push("Assign primary reviewer");
        const checklist = prep.checklist || {};
        ["qcReportCompiled", "trainingBriefed", "risksLogged"].forEach((k) => {
          if (!checklist[k]) blockers.push(`Complete ${k}`);
        });
        if (prep.status !== "COMPLETED") blockers.push("Set Review Prep to COMPLETED");
      } else if (stageKey === "REVIEW") {
        const stages = workflow?.review?.stages || [];
        if (!stages.every((s) => (s.status || "").toUpperCase() === "COMPLETED")) {
          blockers.push("All review stages must be COMPLETED");
        }
        const consolidation = workflow?.review?.consolidation;
        if (consolidation && consolidation.status !== "COMPLETED" && consolidation.findingsResolved !== true) {
          blockers.push("Resolve consolidation findings");
        }
      } else if (stageKey === "APPROVAL") {
        const stages = workflow?.approval?.stages || [];
        if (!stages.every((s) => {
          const status = (s.status || "").toUpperCase();
          return status === "COMPLETED" || status === "SIGNED";
        })) {
          blockers.push("All approval stages must be COMPLETED/SIGNED");
        }
        const hasESign = workflow?.approval?.eSignature?.manifestId ||
          stages.some((s) => s.eSignature?.signed === true);
        if (stages.length && !hasESign) blockers.push("Capture e-signature");
      } else if (stageKey === "ACTIVATION") {
        if (workflow?.activation?.status !== "ACTIVE") blockers.push("Activation status must be ACTIVE");
        if (workflow?.activation?.distributionStatus !== "COMPLETED") blockers.push("Distribution must be COMPLETED");
        if (workflow?.activation?.trainingStatus !== "COMPLETED") blockers.push("Training must be COMPLETED");
      }
      return blockers;
    };

    // USE DRAFT-BASED METRICS for real-time progress (calculated earlier in component)
    const intakePendingChecks = intakeMetricsFromDraft.pendingChecks;
    const calculatedIntakeProgress = intakeMetricsFromDraft.progress;

    // Format ingestion method for display
    // Only show if it's been explicitly set (saved to backend), otherwise show "Not set"
    const ingestionMethodFromBackend = workflow?.intake?.ingestionMethod;
    const ingestionMethod = ingestionMethodFromBackend || intakeDraftEarly?.ingestionMethod || "";
    const ingestionMethodLabels = {
      MANUAL_UPLOAD: "Manual Upload",
      EMAIL: "Email",
      API: "API",
      INTEGRATION: "Integration"
    };
    const intakeSourceSystem = ingestionMethod
      ? (ingestionMethodLabels[ingestionMethod] || ingestionMethod)
      : "Not set";

    // Get compliance statuses from draft for real-time updates
    const duplicateStatus = intakeDraftEarly?.duplicateStatus || "PENDING";
    const virusScanStatus = intakeDraftEarly?.virusStatus || "PENDING";

    console.log('[ISFDocumentWorkflow] Intake draft statuses:', {
      duplicateStatus,
      virusScanStatus,
    });

    // Format compliance tags with actual status
    const sourceIntegrityLabel = duplicateStatus === "CLEAR"
      ? "Source Integrity: Verified"
      : duplicateStatus === "MATCHED"
        ? "Source Integrity: Duplicate Found"
        : "Source Integrity: Pending";

    const virusScanLabel = virusScanStatus === "CLEAN"
      ? "Virus Scan: Clean"
      : virusScanStatus === "INFECTED"
        ? "Virus Scan: Infected"
        : "Virus Scan: Pending";

    // Use draft-based metrics for QC Validation (real-time updates)
    const qcDraftCompleted = qcDraftMetrics.completed;
    const qcDraftTotal = qcDraftMetrics.total;
    const qcDraftProgressPct = qcDraftMetrics.progress;
    const qcDraftQaLead = qcDraftMetrics.qaLead;

    // Use draft-based metrics for Review Preparation (real-time updates)
    const reviewPrepDraftCompleted = reviewPrepDraftMetrics.completed;
    const reviewPrepDraftTotal = reviewPrepDraftMetrics.total;
    const reviewPrepDraftProgressPct = reviewPrepDraftMetrics.progress;
    const reviewPrepDraftReviewersAssigned = reviewPrepDraftMetrics.reviewersAssigned;
    const reviewPrepDraftMeetingDate = reviewPrepDraftMetrics.meetingScheduledAt;

    // Use draft data for real-time progress updates (similar to intake)
    const draftReviewStages = reviewApprovalDraft?.reviewStages ?? reviewStages;
    const draftApprovalStages = reviewApprovalDraft?.approvalStages ?? approvalStages;
    const draftReviewNotes = reviewApprovalDraft?.reviewNotes ?? resolvedReviewData?.notes ?? "";
    const draftApprovalNotes = reviewApprovalDraft?.approvalNotes ?? resolvedApprovalData?.notes ?? "";
    const draftConsolidationStatus = reviewApprovalDraft?.consolidationStatus ?? resolvedConsolidationData?.status ?? "NOT_STARTED";
    const draftFindingsResolved = reviewApprovalDraft?.findingsResolved ?? resolvedConsolidationData?.findingsResolved ?? false;
    const draftConsolidationNotes = reviewApprovalDraft?.consolidationNotes ?? resolvedConsolidationData?.notes ?? "";
    const draftInitialInReviewDate = reviewApprovalDraft?.initialInReviewDate ?? resolvedReviewData?.initialInReviewDate ?? null;
    const draftConsolidationCompletedDate = reviewApprovalDraft?.consolidationCompletedDate ?? resolvedConsolidationData?.consolidationCompletedDate ?? null;

    // Calculate field-based progress for Review stages
    // Only count stages that have been started (status !== PENDING) or explicitly added by user
    // Default stages from backend initialization should not count until they're actually started
    const calculateReviewStageProgress = (stage) => {
      // If stage is still PENDING and hasn't been modified, don't count it
      const isDefaultStage = stage.status === "PENDING" && !stage.startedAt && !stage.completedAt;
      if (isDefaultStage) {
        return 0; // Default stages don't contribute to progress until started
      }

      const fields = [
        stage.name && stage.name.trim() !== "",
        stage.role && stage.role.trim() !== "",
        stage.dueDate && stage.dueDate !== null && stage.dueDate !== "",
      ];
      const filledFields = fields.filter(Boolean).length;
      return fields.length > 0 ? (filledFields / fields.length) * 100 : 0;
    };

    // Calculate field-based progress for Approval stages
    // Only count stages that have been started (status !== PENDING) or explicitly added by user
    const calculateApprovalStageProgress = (stage) => {
      // If stage is still PENDING and hasn't been modified, don't count it
      const isDefaultStage = stage.status === "PENDING" && !stage.startedAt && !stage.completedAt;
      if (isDefaultStage) {
        return 0; // Default stages don't contribute to progress until started
      }

      const fields = [
        stage.name && stage.name.trim() !== "",
        stage.role && stage.role.trim() !== "",
        stage.dueDate && stage.dueDate !== null && stage.dueDate !== "",
      ];
      const filledFields = fields.filter(Boolean).length;
      return fields.length > 0 ? (filledFields / fields.length) * 100 : 0;
    };

    // Filter out default stages that haven't been started
    const activeReviewStages = draftReviewStages.filter(stage => {
      // Include if status is not PENDING, or if it has been started/completed
      return stage.status !== "PENDING" || stage.startedAt || stage.completedAt;
    });

    const activeApprovalStages = draftApprovalStages.filter(stage => {
      // Include if status is not PENDING, or if it has been started/completed
      return stage.status !== "PENDING" || stage.startedAt || stage.completedAt;
    });

    // Calculate review progress based on field completion (only for active stages)
    const reviewStageProgresses = activeReviewStages.map(calculateReviewStageProgress);
    const reviewStagesProgress = activeReviewStages.length > 0
      ? reviewStageProgresses.reduce((sum, p) => sum + p, 0) / activeReviewStages.length
      : 0;

    // Review notes contribution: Count as filled if present
    const reviewNotesProgress = draftReviewNotes && draftReviewNotes.trim() !== "" ? 100 : 0;

    // Initial In Review Date contribution: Count as filled if present
    const initialDateProgress = draftInitialInReviewDate ? 100 : 0;

    // Review section: Average of stages (if any), notes, and date
    // If stages exist, they dominate; notes and date are supplementary
    let reviewProgressPct = 0;
    if (activeReviewStages.length > 0) {
      // Stages are primary (80%), notes (10%), date (10%)
      reviewProgressPct = (reviewStagesProgress * 0.8) +
        (reviewNotesProgress * 0.1) +
        (initialDateProgress * 0.1);
    } else {
      // No active stages: notes and date contribute equally
      const components = [reviewNotesProgress, initialDateProgress].filter(p => p > 0);
      reviewProgressPct = components.length > 0
        ? components.reduce((sum, p) => sum + p, 0) / components.length
        : 0;
    }
    reviewProgressPct = clampPercentage(reviewProgressPct);

    // Calculate approval progress based on field completion (only for active stages)
    const approvalStageProgresses = activeApprovalStages.map(calculateApprovalStageProgress);
    const approvalStagesProgress = activeApprovalStages.length > 0
      ? approvalStageProgresses.reduce((sum, p) => sum + p, 0) / activeApprovalStages.length
      : 0;

    // Approval notes contribution: Count as filled if present
    const approvalNotesProgress = draftApprovalNotes && draftApprovalNotes.trim() !== "" ? 100 : 0;

    // Approval section: Stages (90%), notes (10%)
    let approvalProgressPct = 0;
    if (activeApprovalStages.length > 0) {
      approvalProgressPct = (approvalStagesProgress * 0.9) + (approvalNotesProgress * 0.1);
    } else {
      approvalProgressPct = approvalNotesProgress;
    }
    approvalProgressPct = clampPercentage(approvalProgressPct);

    // Calculate consolidation progress based on field completion
    // All fields weighted equally: status, findingsResolved, notes, completedDate
    const consolidationFields = [
      draftConsolidationStatus && draftConsolidationStatus !== "NOT_STARTED",
      draftFindingsResolved === true,
      draftConsolidationNotes && draftConsolidationNotes.trim() !== "",
      draftConsolidationCompletedDate !== null && draftConsolidationCompletedDate !== "",
    ];
    const consolidationFilledFields = consolidationFields.filter(Boolean).length;
    const consolidationProgress = consolidationFields.length > 0
      ? (consolidationFilledFields / consolidationFields.length) * 100
      : 0;

    // Counts for metrics display (use active stages only)
    const reviewCompletedCount = activeReviewStages.filter((stage) => stage.status === "COMPLETED").length;
    const outstandingReviewCount = Math.max(activeReviewStages.length - reviewCompletedCount, 0);
    const reviewEscalations = activeReviewStages.filter((stage) => stage.status === "ESCALATED").length;

    const approvalCompletedCount = activeApprovalStages.filter((stage) =>
      stage.status === "COMPLETED" || stage.status === "SIGNED"
    ).length;
    const approvalPendingCount = activeApprovalStages.filter((stage) =>
      stage.status !== "COMPLETED" && stage.status !== "SIGNED" && stage.status !== "REJECTED"
    ).length;
    const approvalEscalations = activeApprovalStages.filter((stage) => stage.status === "ESCALATED").length;

    // Weighted combined progress for the Review & Approval stage
    // Fixed weights: Review (40%), Approval (40%), Consolidation (20%)
    // These weights reflect the workflow: Review → Consolidation → Approval
    const reviewApprovalProgress = clampPercentage(
      (reviewProgressPct * 0.4) +
      (approvalProgressPct * 0.4) +
      (consolidationProgress * 0.2)
    );

    // Show actual progress based on field completion, not capped by status
    // Progress reflects how many fields are filled, regardless of overall status

    // Enhanced Activation Progress Calculation - Use draft metrics for real-time updates
    const activationProgressRaw = activationDraftMetrics?.progress ?? 0;
    const activationStatus = (activationDraftMetrics?.status || workflow?.activation?.status || "").toUpperCase();
    const isActivationComplete = activationStatus === "COMPLETED" || activationStatus === "ACTIVE";
    const activationProgress = isActivationComplete ? activationProgressRaw : Math.min(activationProgressRaw, 95);

    // Enhanced Revision Progress Calculation - Use draft metrics for real-time updates
    const revisionProgressRaw = revisionDraftMetrics?.progress ?? 0;
    const revisionStatus = (revisionDraftMetrics?.status || workflow?.revision?.status || "").toUpperCase();
    // Only default to "NO" if documentRevision is explicitly set, not if it's empty/undefined
    const documentRevision = revisionDraftMetrics?.documentRevision || workflow?.revision?.documentRevision || "";

    // Revision stage progress logic:
    // - If documentRevision is empty (not started), progress is 0%
    // - If documentRevision is "NO" (no revision needed), stage is complete = 100%
    // - If status is COMPLETED or APPROVED, use actual progress
    // - Otherwise, cap at 95% until complete
    let revisionProgress;
    if (!documentRevision || documentRevision === "") {
      // No decision made yet = not started = 0%
      revisionProgress = 0;
    } else if (documentRevision === "NO") {
      // No revision needed = stage complete
      revisionProgress = 100;
    } else if (revisionStatus === "COMPLETED" || revisionStatus === "APPROVED" || revisionProgressRaw === 100) {
      revisionProgress = revisionProgressRaw;
    } else {
      revisionProgress = Math.min(revisionProgressRaw, 95);
    }
    const archiveProgress = workflow?.archive?.archivedAt ? 100 : 0;

    const auditReadinessRaw = workflowMetrics?.auditReadiness ?? workflowMetrics?.complianceScore;
    const reviewProgressForAudit = Number.isFinite(workflowMetrics?.reviewProgress)
      ? workflowMetrics.reviewProgress
      : 0;
    const approvalProgressForAudit = Number.isFinite(workflowMetrics?.approvalProgress)
      ? workflowMetrics.approvalProgress
      : 0;
    const combinedProgress =
      reviewProgressForAudit || approvalProgressForAudit
        ? (reviewProgressForAudit + approvalProgressForAudit) / (reviewProgressForAudit && approvalProgressForAudit ? 2 : 1)
        : 0;
    const auditProgress = Number.isFinite(auditReadinessRaw)
      ? ratioToPercent(auditReadinessRaw)
      : clampPercentage(combinedProgress);

    // Use actual calculated progress (not forced to 100% based on markComplete flag)
    // The markComplete flag only affects status label, not actual progress
    // Use draft-based progress for real-time updates
    const intakeProgress = calculatedIntakeProgress;
    const qcProgress = qcDraftProgressPct; // Use draft progress for real-time updates

    // Review Prep progress: Cap at 95% if status is not COMPLETED
    const reviewPrepStatus = (workflow?.reviewPreparation?.status || reviewPrepSummary?.status || "").toUpperCase();
    const isReviewPrepComplete = reviewPrepStatus === "COMPLETED";
    const reviewPrepProgress = isReviewPrepComplete
      ? reviewPrepDraftProgressPct
      : Math.min(reviewPrepDraftProgressPct, 95);

    const stages = [
      {
        key: "INTAKE",
        title: "Intake / Capture",
        subtitle: "Capture and classify document metadata",
        icon: UploadCloud,
        statusResolver: ({ statusKey }) => STATUS_COPY[statusKey]?.label || "Pending",
        progress: intakeProgress,
        context: workflow?.intake,
        metrics: [
          { label: "Pending Checks", value: intakePendingChecks },
          { label: "Source", value: intakeSourceSystem },
        ],
        compliance: [sourceIntegrityLabel, virusScanLabel],
      },
      {
        key: "QC_VALIDATION",
        title: "ISF Owner Validation",
        subtitle: "ISF owner review and validation of intake data",
        icon: ShieldCheck,
        statusResolver: ({ statusKey }) =>
          resolveStatusLabel(statusKey, qcSummary.section?.status ?? qcSummary.status),
        progress: qcProgress,
        context: { qc: qcSummary.section, intake: workflow?.intake },
        metrics: [
          { label: "Checklist Complete", value: `${qcDraftCompleted}/${qcDraftTotal} (${qcDraftProgressPct}%)` },
        ],
        compliance: ["QA-Verified", "Data Stewardship"],
      },
      {
        key: "REVIEW_PREPARATION",
        title: "Review Preparation",
        subtitle: "Assemble reviewers and supporting materials",
        icon: Users,
        statusResolver: ({ statusKey }) =>
          resolveStatusLabel(statusKey, reviewPrepSummary.section?.status ?? reviewPrepSummary.status),
        progress: reviewPrepProgress,
        context: { reviewPreparation: reviewPrepSummary.section, review: workflow?.review },
        metrics: [
          { label: "Checklist Complete", value: `${reviewPrepDraftCompleted}/${reviewPrepDraftTotal} (${reviewPrepDraftProgressPct}%)` },
          { label: "Reviewers Assigned", value: `${reviewPrepDraftReviewersAssigned}/3` },
          {
            label: "Session Date",
            value: reviewPrepDraftMeetingDate
              ? formatDateTime(new Date(reviewPrepDraftMeetingDate))
              : (reviewPrepSummary.section?.meetingScheduledAt
                ? formatDateTime(reviewPrepSummary.section.meetingScheduledAt)
                : "Not scheduled"),
          },
        ],
        compliance: ["Reviewer SOP", "GxP"],
      },
      {
        key: "IN_REVIEW",
        title: "Review",
        subtitle: "Facilitated review cycles and feedback",
        icon: ClipboardList,
        statusResolver: ({ statusKey, workflow }) =>
          resolveStatusLabel(statusKey, workflow?.review?.overallStatus),
        progress: reviewProgressPct,
        context: workflow?.review,
        metrics: [
          { label: "Open Reviews", value: outstandingReviewCount },
          { label: "Completed", value: reviewCompletedCount },
          { label: "Escalations", value: reviewEscalations },
        ],
        compliance: ["21 CFR Part 11"],
      },
      {
        key: "PRE_APPROVAL",
        title: "Pre-Approval Consolidation",
        subtitle: "Resolve findings and finalize packet",
        icon: Layers,
        statusResolver: ({ statusKey, workflow }) =>
          resolveStatusLabel(statusKey, workflow?.review?.overallStatus),
        progress:
          reviewPrepSummary.status === "COMPLETED" && reviewCompletedCount === reviewStages.length
            ? 100
            : reviewProgressPct,
        context: { review: workflow?.review, metrics: workflowMetrics },
        metrics: [
          { label: "Blocking Issues", value: overdue },
          { label: "Support Materials", value: workflow?.review?.supportingMaterials?.length ?? 0 },
          { label: "Review Progress", value: formatPercentLabel(reviewProgressPct) },
        ],
        compliance: ["QA Alignment", "Change Control"],
      },
      {
        key: "APPROVAL",
        title: "Formal Approval / e-Signature",
        subtitle: "Secure signatures and release decisions",
        icon: Fingerprint,
        statusResolver: ({ statusKey, workflow }) =>
          resolveStatusLabel(statusKey, workflow?.approval?.overallStatus),
        progress: approvalProgressPct,
        context: workflow?.approval,
        metrics: [
          { label: "Pending Signatures", value: approvalPendingCount },
          { label: "Completed", value: approvalCompletedCount },
          { label: "Escalations", value: approvalEscalations },
        ],
        compliance: ["21 CFR Part 11", "Digital Cert"],
      },
      {
        key: "REVISION",
        title: "Change Management & Archive",
        subtitle: "Govern updates, version lineage, and archival processes",
        icon: Sparkles,
        statusResolver: ({ statusKey, workflow }) => {
          // Check archive status first, then revision status
          if (workflow?.archive?.archivedAt || workflow?.lifecycleState === "ARCHIVED") {
            return resolveStatusLabel(statusKey, "ARCHIVED");
          }
          return resolveStatusLabel(
            statusKey,
            workflow?.revision?.status ?? (workflow?.revision ? "IN_PROGRESS" : null),
          );
        },
        progress: Math.max(revisionProgress, archiveProgress),
        context: { revision: workflow?.revision, archive: workflow?.archive },
        metrics: [
          { label: "Progress", value: `${Math.max(revisionProgress, archiveProgress)}%` },
          { label: "Document Revision", value: revisionDraftMetrics?.documentRevision || workflow?.revision?.documentRevision || "Not Started" },
          { label: "Archive Older Version", value: revisionDraftMetrics?.archiveOlderVersion || workflow?.revision?.archiveOlderVersion || "Not Started" },
          {
            label: "Archive Status",
            value: workflow?.archive?.archivedAt
              ? "Archived"
              : (revisionDraftMetrics?.archiveStatus || workflow?.revision?.archiveStatus || "—"),
          },
          {
            label: "Archived On",
            value: workflow?.archive?.archivedAt
              ? formatDateTime(workflow?.archive?.archivedAt)
              : "Not archived",
          },
          { label: "Retention (yrs)", value: document?.retentionRequirements?.duration ?? 15 },
          { label: "Archive Reason", value: workflow?.archive?.reason || "—" },
        ],
        compliance: ["Version Traceability", "Retention Policy", "GxP"],
      },
      {
        key: "AUDIT_REPORTING",
        title: "Audit & Reporting",
        subtitle: "Demonstrate compliance and traceability",
        icon: BarChart3,
        statusResolver: ({ statusKey, workflow }) =>
          resolveStatusLabel(
            statusKey,
            workflow?.metrics?.auditStatus ?? (workflow?.lifecycleState === "ARCHIVED" ? "AUDIT_READY" : null),
          ),
        progress: auditProgress,
        context: {
          auditTrail: auditTrailEntries,
          compliance: workflow?.compliance,
          metrics: workflowMetrics,
        },
        metrics: [
          { label: "Audit Logs", value: auditTrailEntries.length },
          { label: "Open Issues", value: workflow?.compliance?.regulatory?.issuesOpen ?? 0 },
          {
            label: "Cycle Time (days)",
            value: workflowMetrics?.cycleTimeDays ? workflowMetrics.cycleTimeDays.toFixed(1) : "0.0",
          },
        ],
        compliance: ["Inspection Ready", "Traceability"],
      },
    ];

    const lifecycleStageKeyMap = {
      IN_REVIEW: "REVIEW",
      PRE_APPROVAL: "REVIEW",
      APPROVAL: "REVIEW",
      REVIEW: "REVIEW",
      REVISION: "REVISION",
      OBSOLETE: "REVISION",
      ARCHIVED: "REVISION",
    };

    const effectiveLifecycle = lifecycleStageKeyMap[currentLifecycle] || currentLifecycle || "INTAKE";
    let activeIndex = stages.findIndex((stage) => stage.key === effectiveLifecycle);
    if (activeIndex === -1) {
      activeIndex = stages.findIndex((stage) => stage.key === currentLifecycle);
    }
    if (activeIndex === -1) {
      activeIndex = 0;
    }

    const augmentedStages = stages.map((stage, index) => {
      let statusKey = "pending";
      let rejectionReason = null;

      // Check if stage is rejected (highest priority)
      const isRejected =
        (stage.key === "INTAKE" && workflow?.intake?.rejection?.isRejected) ||
        (stage.key === "QC_VALIDATION" && workflow?.qcValidation?.rejection?.isRejected) ||
        (stage.key === "REVIEW_PREPARATION" && workflow?.reviewPreparation?.rejection?.isRejected) ||
        (stage.key === "REVIEW" && (workflow?.review?.rejection?.isRejected || workflow?.approval?.rejection?.isRejected)) ||
        (stage.key === "IN_REVIEW" && workflow?.review?.rejection?.isRejected) ||
        (stage.key === "APPROVAL" && workflow?.approval?.rejection?.isRejected);

      // Get rejection reason if rejected
      if (isRejected) {
        if (stage.key === "INTAKE") rejectionReason = workflow?.intake?.rejection?.reason;
        else if (stage.key === "QC_VALIDATION") rejectionReason = workflow?.qcValidation?.rejection?.reason;
        else if (stage.key === "REVIEW_PREPARATION") rejectionReason = workflow?.reviewPreparation?.rejection?.reason;
        else if (stage.key === "REVIEW") {
          rejectionReason = workflow?.review?.rejection?.reason || workflow?.approval?.rejection?.reason;
        }
        else if (stage.key === "IN_REVIEW") rejectionReason = workflow?.review?.rejection?.reason;
        else if (stage.key === "APPROVAL") rejectionReason = workflow?.approval?.rejection?.reason;
      }

      // Check if stage has markComplete flag set (high priority)
      const isMarkedComplete =
        (stage.key === "INTAKE" && workflow?.intake?.markComplete) ||
        // For QC, require publication to be considered 'marked complete' to avoid approval-only completion
        (stage.key === "QC_VALIDATION" && workflow?.qcValidation?.markComplete && workflow?.qcValidation?.publicationStatus === 'PUBLISHED') ||
        (stage.key === "REVIEW_PREPARATION" && workflow?.reviewPreparation?.markComplete);


      console.log("", workflow.intake);
      // Check if stage has actual data in the database
      const hasIntakeData = stage.key === "INTAKE" && workflow?.intake &&
        (workflow.intake.metadataConfidence !== undefined ||
          workflow.intake.duplicateCheck ||
          workflow.intake.virusScan ||
          workflow.intake.extractedMetadata);

      const hasQcData = stage.key === "QC_VALIDATION" && workflow?.qcValidation &&
        (workflow.qcValidation.qaLead ||
          workflow.qcValidation.checklist);

      const hasReviewPrepData = stage.key === "REVIEW_PREPARATION" && workflow?.reviewPreparation &&
        (workflow.reviewPreparation.primaryReviewer ||
          workflow.reviewPreparation.checklist ||
          workflow.reviewPreparation.meetingScheduledAt);

      const hasReviewData = stage.key === "REVIEW" && (
        (workflow?.review && (workflow.review.stages?.length > 0 || workflow.review.overallStatus)) ||
        (workflow?.approval && (workflow.approval.stages?.length > 0 || workflow.approval.overallStatus))
      );

      // Determine status based on actual data and lifecycle state
      // Priority: rejected > progress 100% (with no blockers) > markComplete > lifecycle position > has data
      const blockers = getStageBlockers(stage.key);
      const rawProgress = Number.isFinite(stage.progress) ? Math.min(Math.max(stage.progress, 0), 100) : 0;
      const stageProgress = blockers.length > 0 ? Math.min(rawProgress, 99) : rawProgress;
      const isProgressComplete = stageProgress === 100 && blockers.length === 0;

      if (isRejected) {
        // Stage is rejected - highest priority
        statusKey = "rejected";
      } else if (isProgressComplete) {
        // Stage with 100% progress is considered completed
        statusKey = "completed";
      } else if (isMarkedComplete) {
        // Stage is explicitly marked complete
        statusKey = "completed";
      } else if (index === activeIndex) {
        // Current lifecycle stage is active
        statusKey = "active";
      } else if (index < activeIndex && stageProgress > 0) {
        // Stage before active index with some progress - show as active (in progress)
        statusKey = "active";
      } else if (index < activeIndex && stageProgress === 0) {
        // Stage before active index with no progress (likely after reset) - show as pending
        statusKey = "pending";
      } else if (
        (stage.key === "INTAKE" && hasIntakeData) ||
        (stage.key === "QC_VALIDATION" && hasQcData) ||
        (stage.key === "REVIEW_PREPARATION" && hasReviewPrepData) ||
        (stage.key === "REVIEW" && hasReviewData)
      ) {
        // Stage has data but lifecycle hasn't reached it yet - show as active
        statusKey = "active";
      } else if (stage.key === "AUDIT_REPORTING" && (currentLifecycle === "ARCHIVED" || workflow?.archive?.archivedAt)) {
        statusKey = "gated";
      }

      return {
        ...stage,
        statusKey,
        statusConfig: STATUS_COPY[statusKey] ?? STATUS_COPY.pending,
        rejectionReason,
        blockers,
        progress: stageProgress,
      };
    });

    // Filter out hidden stages and Review Preparation (no longer needed)
    return augmentedStages.filter((stage) =>
      !HIDDEN_STAGE_KEYS.has(stage.key) && stage.key !== "REVIEW_PREPARATION"
    );
  }, [
    workflow,
    document,
    currentLifecycle,
    auditTrailEntries,
    qcSummary,
    reviewPrepSummary,
    intakeMetricsFromDraft,
    intakeDraftEarly,
    reviewApprovalDraft,
    qcDraftMetrics,
    reviewPrepDraftMetrics,
    activationDraftMetrics,
    revisionDraftMetrics,
    resolvedReviewData,
    resolvedApprovalData,
    resolvedConsolidationData,
  ]);

  const [activeStageDetail, setActiveStageDetail] = useState(null);
  const [isStageSheetOpen, setStageSheetOpen] = useState(false);

  // Get current user role for workflow stage access control (declared early for use in callbacks)
  const currentUser = sharedAuthService.getCurrentUser();
  const userRole = currentUser?.clinicalRole || currentUser?.neurodocRole || null;
  // Debug logging for role-based access control
  if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
    console.log('[ISFDocumentWorkflow] Role Debug:', {
      currentUser: currentUser ? {
        id: currentUser.id || currentUser._id,
        email: currentUser.email,
        neurodocRole: currentUser.neurodocRole,
        clinicalRole: currentUser.clinicalRole,
        rawRole: currentUser.role,
        applications: currentUser.applications
      } : null,
      resolvedUserRole: userRole,
      expectedAdminRole: 'ADMIN'
    });
  }

  // Declare toast early for use in callbacks
  const { toast } = useToast();

  const handleStageSheetToggle = useCallback((open) => {
    setStageSheetOpen(open);
    if (!open) {
      setActiveStageDetail(null);
    }
  }, []);

  const handleStageOpen = useCallback((stage, focusField = null) => {
    // Check if user has permission to open this stage
    if (userRole && stage.key) {
      const canOpen = canOpenWorkflowStage(userRole, stage.key);
      if (!canOpen) {
        toast({
          title: "Access Denied",
          description: `Your role (${userRole}) does not have permission to access the ${stage.title} stage.`,
          variant: "destructive"
        });
        return;
      }
    }

    setActiveStageDetail(stage);
    setStageSheetOpen(true);
    // Notify parent component when a stage is opened (for smart layout switching)
    if (externalOnStageOpen) {
      externalOnStageOpen(stage);
    }
    // If focusField is specified, scroll to that field after a short delay
    if (focusField) {
      setTimeout(() => {
        const field = document.getElementById(focusField);
        if (field) {
          field.scrollIntoView({ behavior: 'smooth', block: 'center' });
          field.focus();
        }
      }, 300);
    }
  }, [externalOnStageOpen, userRole, toast]);


  const lifecycleStats = useMemo(() => {
    if (!stageSequence.length) {
      return { total: 0, completedCount: 0, pendingCount: 0, overallProgress: 0, activeStage: null };
    }

    const completedCount = stageSequence.filter((stage) => stage.statusKey === "completed").length;
    const activeStage = stageSequence.find((stage) => stage.statusKey === "active") ?? null;
    const pendingCount = stageSequence.length - completedCount - (activeStage ? 1 : 0);
    const activeContribution = activeStage ? Math.min(Math.max(activeStage.progress ?? 0, 0), 100) / 100 : 0;

    return {
      total: stageSequence.length,
      completedCount,
      pendingCount,
      overallProgress: Math.round(((completedCount + activeContribution) / stageSequence.length) * 100),
      activeStage,
    };
  }, [stageSequence]);

  const documentTitle = document?.documentTitle || document?.title || "Untitled Document";
  const protocolId = document?.protocolId || workflow?.intake?.extractedMetadata?.protocolId || "Not assigned";
  const siteId = document?.site || workflow?.intake?.extractedMetadata?.siteId || "Not assigned";
  const ownerName = document?.owner?.name || document?.ownerName || "Unassigned Owner";
  const documentStatus = document?.status || workflow?.lifecycleState || "DRAFT";

  // Format document ID consistently - show full ID uniformly
  const displayDocumentId = documentId || "N/A";

  // Extract site name - handle both object and string formats
  const siteName = useMemo(() => {
    if (document?.site) {
      if (typeof document.site === 'object') {
        return document.site.name || document.site.siteCode || document.site._id || "Not assigned";
      }
      return document.site;
    }
    return workflow?.intake?.extractedMetadata?.siteName || siteId || "Not assigned";
  }, [document?.site, workflow?.intake?.extractedMetadata?.siteName, siteId]);

  const queryClient = useQueryClient();

  // Rejection handling state
  const [showRejectionDialog, setShowRejectionDialog] = useState(false);
  const [rejectionStage, setRejectionStage] = useState(null);



  // Real-time Intake metrics based on draft (for sheet display)
  // const intakeDraftMetrics = useMemo(() => {
  //   // Security checks (weight: 50%)
  //   const duplicateComplete = intakeDraft?.duplicateStatus === "CLEAR";
  //   const virusComplete = intakeDraft?.virusStatus === "CLEAN";
  //   const securityChecksComplete = [duplicateComplete, virusComplete].filter(Boolean).length;
  //   const securityPercent = Math.round((securityChecksComplete / 2) * 100);

  //   // Metadata verification (weight: 30%)
  //   const metadataVerification = intakeDraft?.metadataVerification || {}

  //   console.log("metadataVerification", metadataVerification);
  //   console.log("document", document);
  //   const hasZone = !!document?.zone;
  //   const hasSection = !!document?.section;
  //   const hasArtifact = !!document?.artifact;
  //   const hasSubArtifact = !!document?.subArtifact;
  //   const totalMetadataItems = [hasZone, hasSection, hasArtifact, hasSubArtifact].filter(Boolean).length;
  //   const verifiedMetadataItems = [
  //     hasZone && metadataVerification.zoneVerified,
  //     hasSection && metadataVerification.sectionVerified,
  //     hasArtifact && metadataVerification.artifactVerified,
  //     hasSubArtifact && metadataVerification.subArtifactVerified,
  //   ].filter(Boolean).length;
  //   const metadataPercent = totalMetadataItems > 0 ? Math.round((verifiedMetadataItems / totalMetadataItems) * 100) : 0;

  //   // Ingestion info (weight: 20%)
  //   // Only count ingestionMethod if it's been explicitly set (not just the default)
  //   // Check if it exists in the backend workflow data, meaning it was saved
  //   const ingestionMethodFromBackend = workflow?.intake?.ingestionMethod;
  //   const hasIngestionMethod = ingestionMethodFromBackend && ingestionMethodFromBackend !== "";
  //   // Source system is optional, only count if explicitly filled
  //   const hasSourceSystem = !!intakeDraft?.sourceSystem && intakeDraft?.sourceSystem.trim() !== "";
  //   const ingestionItemsComplete = (hasIngestionMethod ? 1 : 0) + (hasSourceSystem ? 1 : 0);
  //   const ingestionPercent = Math.round((ingestionItemsComplete / 2) * 100);


  //   console.log("workflow intake", workflow?.intake);
  //   // Calculate pending checks
  //   const duplicatePending = intakeDraft?.duplicateStatus !== "CLEAR";
  //   const virusPending = intakeDraft?.virusStatus !== "CLEAN";
  //   const metadataVerificationPending = [
  //     hasZone && !metadataVerification.zoneVerified,
  //     hasSection && !metadataVerification.sectionVerified,
  //     hasArtifact && !metadataVerification.artifactVerified,
  //     hasSubArtifact && !metadataVerification.subArtifactVerified,
  //   ].filter(Boolean).length;
  //   const pendingChecks = [duplicatePending, virusPending].filter(Boolean).length + metadataVerificationPending;

  //   // Adjusted weights when no metadata
  //   // For new documents, only count verified metadata, not just presence of metadata
  //   const securityWeight = totalMetadataItems > 0 ? 50 : 80;
  //   const metadataWeight = totalMetadataItems > 0 ? 30 : 0;
  //   const ingestionWeight = 20;

  //   // Security checks: Only count if both are CLEAR/CLEAN (not just PENDING)
  //   const securityContribution = (securityChecksComplete / 2) * securityWeight;

  //   // Metadata: Only count verified items, not just presence
  //   // If metadata exists but isn't verified, don't count it toward progress
  //   const metadataContribution = totalMetadataItems > 0 && verifiedMetadataItems > 0
  //     ? (verifiedMetadataItems / totalMetadataItems) * metadataWeight
  //     : 0;

  //   // Ingestion: Only count if ingestionMethod was explicitly set (saved to backend)
  //   // Don't count default "MANUAL_UPLOAD" value for new documents
  //   const ingestionContribution = hasIngestionMethod
  //     ? (ingestionItemsComplete / 2) * ingestionWeight
  //     : 0; // If ingestionMethod not explicitly set, don't count ingestion at all

  //   const totalProgress = Math.round(securityContribution + metadataContribution + ingestionContribution);

  //   return {
  //     progress: totalProgress,
  //     pendingChecks,
  //     security: { complete: securityChecksComplete, total: 2, percent: securityPercent },
  //     metadata: { verified: verifiedMetadataItems, total: totalMetadataItems, percent: metadataPercent },
  //     ingestion: { complete: ingestionItemsComplete, total: 2, percent: ingestionPercent },
  //   };
  // }, [intakeDraft, document?.zone, document?.section, document?.artifact, document?.subArtifact]);

  const intakeDraftMetrics = useMemo(() => {
    /* ---------------- SECURITY (50%) ---------------- */
    const duplicateComplete = intakeDraft?.duplicateStatus === "CLEAR";
    const virusComplete = intakeDraft?.virusStatus === "CLEAN";

    const securityCompleted = [duplicateComplete, virusComplete].filter(Boolean).length;
    const securityTotal = 2;
    const securityPercent = Math.round((securityCompleted / securityTotal) * 100);

    /* ---------------- METADATA (30%) ---------------- */
    const metadataVerification = intakeDraft?.metadataVerification || {};

    const hasZone = !!document?.zone;
    const hasSection = !!document?.section;
    const hasArtifact = !!document?.artifact;
    const hasSubArtifact = !!document?.subArtifact;

    const metadataItems = [
      { exists: hasZone, verified: metadataVerification.zoneVerified },
      { exists: hasSection, verified: metadataVerification.sectionVerified },
      { exists: hasArtifact, verified: metadataVerification.artifactVerified },
      { exists: hasSubArtifact, verified: metadataVerification.subArtifactVerified },
    ];

    const totalMetadataItems = metadataItems.filter(i => i.exists).length;
    const verifiedMetadataItems = metadataItems.filter(i => i.exists && i.verified).length;

    const metadataPercent =
      totalMetadataItems > 0
        ? Math.round((verifiedMetadataItems / totalMetadataItems) * 100)
        : 0;

    /* ---------------- INGESTION + LEGIBILITY (20%) ---------------- */
    // Ingestion
    const ingestionMethodFromBackend = workflow?.intake?.ingestionMethod;
    const ingestionComplete = !!ingestionMethodFromBackend;

    // Legibility
    const legibilityComplete = intakeDraft?.legibilityClear !== null && intakeDraft?.legibilityClear !== "";

    const ingestionLegibilityItems = [ingestionComplete, legibilityComplete];
    const ingestionLegibilityCompleted = ingestionLegibilityItems.filter(Boolean).length;
    const ingestionLegibilityTotal = ingestionLegibilityItems.length;
    const ingestionLegibilityPercent = Math.round(
      (ingestionLegibilityCompleted / ingestionLegibilityTotal) * 100
    );

    /* ---------------- WEIGHTS ---------------- */
    const securityWeight = 50;
    const metadataWeight = 30;
    const ingestionLegibilityWeight = 20;

    const securityContribution = (securityCompleted / securityTotal) * securityWeight;
    const metadataContribution =
      totalMetadataItems > 0
        ? (verifiedMetadataItems / totalMetadataItems) * metadataWeight
        : 0;
    const ingestionLegibilityContribution =
      (ingestionLegibilityCompleted / ingestionLegibilityTotal) * ingestionLegibilityWeight;

    const totalProgress = Math.round(
      securityContribution + metadataContribution + ingestionLegibilityContribution
    );

    /* ---------------- PENDING CHECKS ---------------- */
    const pendingChecks =
      [!duplicateComplete, !virusComplete].filter(Boolean).length +
      (totalMetadataItems - verifiedMetadataItems) +
      [!ingestionComplete, !legibilityComplete].filter(Boolean).length;

    return {
      progress: totalProgress,
      pendingChecks,
      security: {
        complete: securityCompleted,
        total: securityTotal,
        percent: securityPercent,
      },
      metadata: {
        verified: verifiedMetadataItems,
        total: totalMetadataItems,
        percent: metadataPercent,
      },
      ingestionLegibility: {
        complete: ingestionLegibilityCompleted,
        total: ingestionLegibilityTotal,
        percent: ingestionLegibilityPercent,
      },
    };
  }, [
    intakeDraft,
    document?.zone,
    document?.section,
    document?.artifact,
    document?.subArtifact,
    workflow?.intake?.ingestionMethod,
  ]);


  // Shorthand for progress value
  const intakeDraftProgress = intakeDraftMetrics.progress;
  const intakeDraftPendingChecks = intakeDraftMetrics.pendingChecks;

  const updateReviewApprovalDraft = useCallback((patch) => {
    setReviewApprovalDraft((prev) => ({
      ...prev,
      ...(typeof patch === "function" ? patch(prev) : patch),
    }));
  }, []);

  const updateIntakeDraft = useCallback((patch) => {
    setIntakeDraft((prev) => {
      const newDraft = {
        ...prev,
        ...(typeof patch === "function" ? patch(prev) : patch),
      };
      // Also update the early draft for real-time card progress
      setIntakeDraftEarly((prevEarly) => ({
        ...prevEarly,
        duplicateStatus: newDraft.duplicateStatus,
        virusStatus: newDraft.virusStatus,
        ingestionMethod: newDraft.ingestionMethod,
        sourceSystem: newDraft.sourceSystem,
        metadataVerification: newDraft.metadataVerification,
        legibilityClear: newDraft.legibilityClear
      }));
      return newDraft;
    });
  }, []);

  const handleLegibilityChange = useCallback((value) => {
    updateIntakeDraft({ legibilityClear: value });
  }, [updateIntakeDraft]);

  const updateQcDraft = useCallback((patch) => {
    setQcDraft((prev) => ({
      ...prev,
      ...(typeof patch === "function" ? patch(prev) : patch),
    }));
  }, []);

  const updateReviewPrepDraft = useCallback((patch) => {
    setReviewPrepDraft((prev) => ({
      ...prev,
      ...(typeof patch === "function" ? patch(prev) : patch),
    }));
  }, []);

  const updateActivationDraft = useCallback((patch) => {
    setActivationDraft((prev) => ({
      ...prev,
      ...(typeof patch === "function" ? patch(prev) : patch),
    }));
  }, []);

  const updateRevisionDraft = useCallback((patch) => {
    setRevisionDraft((prev) => ({
      ...prev,
      ...(typeof patch === "function" ? patch(prev) : patch),
    }));
  }, []);

  const intakeMutation = useMutation({
    // mutationFn: (payload) => 

    mutationFn: (payload) => isfDocumentWorkflowService.updateIntake(documentId, payload),
    onSuccess: async (data, variables) => {
      const { markComplete } = variables;
      console.log("markComplete snapshot:", markComplete);
      if (markComplete == true) {
        toast({
          title: "Intake Completed",
          description: "Intake stage completed successfully. Document advanced to QC Validation stage.",
          variant: "default"
        });
      } else {
        toast({
          title: "Intake Updated",
          description: "The intake stage has been saved successfully."
        });
      }
      // Invalidate all related queries to ensure fresh data
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      // Force refetch to get fresh data from server with updated metadataVerification
      await queryClient.refetchQueries({ queryKey: ["document", documentId] });
      // Notify parent component to refresh workflow data if callback provided
      if (onWorkflowUpdate) {
        onWorkflowUpdate();
      }
      // Only close if marked complete, otherwise keep open for further edits
      handleStageSheetToggle(false);
    },
    onError: (error) => {
      const message = error?.response?.data?.error || error?.message || "Failed to update intake";
      toast({ title: "Intake update failed", description: message, variant: "destructive" });
    },
  });

  const qcMutation = useMutation({
    mutationFn: (payload) => isfDocumentWorkflowService.updateQcValidation(documentId, payload),
    onSuccess: async (data, variables) => {
      if (variables.markComplete) {
        toast({
          title: "QC Validation Completed",
          description: "QC Validation stage completed successfully. Document advanced to Review stage.",
          variant: "default"
        });
      } else {
        toast({
          title: "QC Validation Updated",
          description: "The QC validation stage has been saved successfully."
        });
      }
      // Invalidate and refetch both document and workflow queries to get latest data
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", documentId] });
      // Refetch both queries immediately
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ["document", documentId] }),
        queryClient.refetchQueries({ queryKey: ["workflow", documentId] })
      ]);
      // Notify parent component to refresh workflow data if callback provided
      if (onWorkflowUpdate) {
        onWorkflowUpdate();
      }
      // Only close if marked complete, otherwise keep open for further edits
      if (variables.markComplete) {
        handleStageSheetToggle(false);
      }
    },
    onError: (error) => {
      const message = error?.response?.data?.error || error?.message || "Failed to update QC validation";
      toast({ title: "QC validation update failed", description: message, variant: "destructive" });
    },
  });

  const reviewPrepMutation = useMutation({
    mutationFn: (payload) => isfDocumentWorkflowService.updateReviewPreparation(documentId, payload),
    onSuccess: async (data, variables) => {
      if (variables.markComplete) {
        toast({
          title: "Review Preparation Completed",
          description: "Review preparation stage completed successfully.",
          variant: "default"
        });
      } else {
        toast({
          title: "Review Preparation Updated",
          description: "Review preparation saved successfully."
        });
      }
      // Invalidate and refetch both document and workflow queries to get latest data
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", documentId] });
      // Refetch both queries immediately
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ["document", documentId] }),
        queryClient.refetchQueries({ queryKey: ["workflow", documentId] })
      ]);
      // Notify parent component to refresh workflow data if callback provided
      if (onWorkflowUpdate) {
        onWorkflowUpdate();
      }
      // Only close if marked complete, otherwise keep open for further edits
      if (variables.markComplete) {
        handleStageSheetToggle(false);
      }
    },
    onError: (error) => {
      const message = error?.response?.data?.error || error?.message || "Failed to update review preparation";
      toast({ title: "Review preparation update failed", description: message, variant: "destructive" });
    },
  });

  // ==================== REJECTION MUTATION ====================
  const rejectionMutation = useMutation({
    mutationFn: (rejectionData) => isfDocumentWorkflowService.rejectDocument(documentId, rejectionData),
    onSuccess: async (data) => {
      toast({
        title: "Document Rejected",
        description: data.message || "Document has been rejected successfully.",
        variant: "default",
      });
      // Close rejection dialog
      setShowRejectionDialog(false);
      setRejectionStage(null);
      // Close stage sheet
      handleStageSheetToggle(false);
      // Invalidate and refetch queries
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", documentId] });
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ["document", documentId] }),
        queryClient.refetchQueries({ queryKey: ["workflow", documentId] }),
      ]);
      if (onWorkflowUpdate) {
        onWorkflowUpdate();
      }
    },
    onError: (error) => {
      const message = error?.response?.data?.error || error?.message || "Failed to reject document";
      toast({ title: "Rejection failed", description: message, variant: "destructive" });
    },
  });

  // Resolve rejection mutation
  const resolveRejectionMutation = useMutation({
    mutationFn: ({ stage, notes }) => isfDocumentWorkflowService.resolveRejection(documentId, { stage, notes }),
    onSuccess: async () => {
      toast({
        title: "Rejection Resolved",
        description: "The rejection has been resolved. Document can now proceed.",
        variant: "default",
      });
      // Invalidate and refetch queries
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", documentId] });
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ["document", documentId] }),
        queryClient.refetchQueries({ queryKey: ["workflow", documentId] }),
      ]);
      if (onWorkflowUpdate) {
        onWorkflowUpdate();
      }
    },
    onError: (error) => {
      const message = error?.response?.data?.error || error?.message || "Failed to resolve rejection";
      toast({ title: "Resolution failed", description: message, variant: "destructive" });
    },
  });

  // Detect active rejection across all stages
  const activeRejection = useMemo(() => {
    const stages = [
      { key: 'INTAKE', data: workflow?.intake?.rejection, label: 'Intake / Capture' },
      { key: 'QC_VALIDATION', data: workflow?.qcValidation?.rejection, label: 'TMF Owner Validation' },
      { key: 'REVIEW_PREPARATION', data: workflow?.reviewPreparation?.rejection, label: 'Review Preparation' },
      { key: 'IN_REVIEW', data: workflow?.review?.rejection, label: 'Review' },
      { key: 'APPROVAL', data: workflow?.approval?.rejection, label: 'Approval' },
    ];

    for (const stage of stages) {
      if (stage.data?.isRejected) {
        return {
          stage: stage.key,
          stageLabel: stage.label,
          reason: stage.data.reason,
          category: stage.data.category,
          actionRequired: stage.data.actionRequired,
          dueDate: stage.data.dueDate,
          rejectedAt: stage.data.rejectedAt,
          rejectedByName: stage.data.rejectedByName,
          returnToStage: stage.data.returnToStage,
        };
      }
    }
    return null;
  }, [workflow]);

  const handleResolveRejection = useCallback((stage) => {
    if (!documentId || !stage) return;
    resolveRejectionMutation.mutate({ stage, notes: 'Corrections made and verified.' });
  }, [documentId, resolveRejectionMutation]);

  const handleOpenRejectionDialog = useCallback((stageKey) => {
    setRejectionStage(stageKey);
    setShowRejectionDialog(true);
  }, []);

  const handleRejectDocument = useCallback((rejectionData) => {
    if (!documentId) {
      toast({
        title: "Missing document identifier",
        description: "Unable to reject document without a document reference.",
        variant: "destructive",
      });
      return;
    }
    rejectionMutation.mutate(rejectionData);
  }, [documentId, rejectionMutation, toast]);

  useEffect(() => {
    // Always update draft when workflow data changes from database
    // This ensures form fields are populated with latest data after saves
    if (workflow?.intake) {
      updateIntakeDraft(buildIntakeDraft(workflow.intake));
    }
  }, [workflow?.intake, buildIntakeDraft, updateIntakeDraft]);

  const canMarkIntakeComplete =
    // Duplicate check must be CLEAR to complete Intake.
    // Virus scan results are tracked for security but do not block completion.
    intakeDraft.duplicateStatus === "CLEAR";

  const canMarkQcComplete = useMemo(
    () => qcDraft.qcDecision !== null && qcDraft.qcDecision !== undefined,
    [qcDraft.qcDecision]
  );

  useEffect(() => {
    // Always update intake draft when workflow data changes from database
    // Also handles reset case when intake becomes empty/reset
    setIntakeDraft(buildIntakeDraft(workflow?.intake || {}));
  }, [workflow?.intake, buildIntakeDraft]);

  useEffect(() => {
    // Always update draft when workflow data changes from database
    // This ensures form fields are populated with latest data after saves
    // Also handles reset case when qcValidation becomes empty/reset
    setQcDraft(buildQcDraft(workflow?.qcValidation || {}));
  }, [workflow?.qcValidation, buildQcDraft]);

  useEffect(() => {
    // Always update draft when workflow data changes from database
    // This ensures form fields are populated with latest data after saves
    // Also handles reset case when reviewPreparation becomes empty/reset
    setReviewPrepDraft(buildReviewPrepDraft(workflow?.reviewPreparation || {}));
  }, [workflow?.reviewPreparation, buildReviewPrepDraft]);

  const canMarkReviewPrepComplete = useMemo(
    () =>
      REVIEW_PREP_CHECKLIST_KEYS.every((key) => reviewPrepDraft.checklist?.[key]) &&
      Boolean(reviewPrepDraft.primaryReviewer?.trim()),
    [reviewPrepDraft.checklist, reviewPrepDraft.primaryReviewer]
  );

  useEffect(() => {
    // Always update draft when workflow data changes from database
    // This ensures form fields are populated with latest data after saves
    // Also handles reset case when workflow.activation becomes empty/reset
    setActivationDraft(buildActivationDraft(workflow?.activation || {}));
  }, [workflow?.activation, buildActivationDraft]);

  useEffect(() => {
    // Always update draft when workflow revision data changes
    // Also handles reset case when workflow.revision becomes empty/reset
    // For new documents, ensure documentRevision is empty (not "NO")
    const revisionData = workflow?.revision || {};
    // If documentRevision is not explicitly set or is "NO" (default), ensure it's empty string
    if (!revisionData.documentRevision || revisionData.documentRevision === "NO") {
      revisionData.documentRevision = "";
    }
    setRevisionDraft(buildRevisionDraft(revisionData));
  }, [workflow?.revision, buildRevisionDraft]);

  useEffect(() => {
    // Always update draft when workflow data changes from database
    // This ensures form fields are populated with latest data after saves
    // Also handles reset case when review/approval data becomes empty/reset
    // Only update if the data actually changed to avoid overwriting user edits
    const newDraft = buildReviewApprovalDraft(
      resolvedReviewData || {},
      resolvedApprovalData || {},
      resolvedConsolidationData || {}
    );
    // Only update if there are actual changes to avoid resetting user edits
    setReviewApprovalDraft((prev) => {
      // If backend has stages but draft doesn't, or vice versa, update
      const backendHasStages = (newDraft.reviewStages?.length > 0 || newDraft.approvalStages?.length > 0);
      const draftHasStages = (prev.reviewStages?.length > 0 || prev.approvalStages?.length > 0);
      if (backendHasStages !== draftHasStages) {
        return newDraft;
      }
      // If backend has notes but draft doesn't, update
      if ((newDraft.reviewNotes || newDraft.approvalNotes) && !(prev.reviewNotes || prev.approvalNotes)) {
        return newDraft;
      }
      // Otherwise, merge to preserve user edits
      return {
        ...prev,
        // Only update fields that are actually different and not being edited
        reviewStages: newDraft.reviewStages?.length > 0 ? newDraft.reviewStages : prev.reviewStages,
        approvalStages: newDraft.approvalStages?.length > 0 ? newDraft.approvalStages : prev.approvalStages,
        consolidationStatus: newDraft.consolidationStatus || prev.consolidationStatus,
        findingsResolved: newDraft.findingsResolved !== undefined ? newDraft.findingsResolved : prev.findingsResolved,
      };
    });
  }, [
    resolvedReviewData,
    resolvedApprovalData,
    resolvedConsolidationData,
    buildReviewApprovalDraft
  ]);

  const reviewApprovalMutation = useMutation({
    mutationFn: (payload) => isfDocumentWorkflowService.updateReviewAndApproval(documentId, payload),
    onSuccess: async () => {
      toast({
        title: "Review & Approval Updated",
        description: "Review and approval configuration saved successfully."
      });
      // Invalidate and refetch both document and workflow queries to get latest data
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", documentId] });
      // Refetch both queries immediately
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ["document", documentId] }),
        queryClient.refetchQueries({ queryKey: ["workflow", documentId] })
      ]);
      // Notify parent component to refresh workflow data if callback provided
      if (onWorkflowUpdate) {
        onWorkflowUpdate();
      }
    },
    onError: (error) => {
      const message = error?.response?.data?.error || error?.message || "Failed to update review and approval";
      toast({ title: "Update failed", description: message, variant: "destructive" });
    },
  });

  const activationMutation = useMutation({
    mutationFn: (payload) => isfDocumentWorkflowService.updateActivation(documentId, payload),
    onSuccess: async () => {
      toast({
        title: "Activation Updated",
        description: "Activation details have been saved successfully."
      });
      // Invalidate and refetch both document and workflow queries to get latest data
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", documentId] });
      // Refetch both queries immediately
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ["documenzt", documentId] }),
        queryClient.refetchQueries({ queryKey: ["workflow", documentId] })
      ]);
      // Notify parent component to refresh workflow data if callback provided
      if (onWorkflowUpdate) {
        onWorkflowUpdate();
      }
    },
    onError: (error) => {
      const message = error?.response?.data?.error || error?.message || "Failed to update activation";
      toast({ title: "Activation update failed", description: message, variant: "destructive" });
    },
  });

  const revisionMutation = useMutation({
    mutationFn: (payload) => isfDocumentWorkflowService.updateRevision(documentId, payload),
    onSuccess: async () => {
      toast({
        title: "Revision Updated",
        description: "Revision details have been saved successfully."
      });
      await queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      await queryClient.invalidateQueries({ queryKey: ["workflow", documentId] });
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ["document", documentId] }),
        queryClient.refetchQueries({ queryKey: ["workflow", documentId] })
      ]);
      if (onWorkflowUpdate) {
        onWorkflowUpdate();
      }
    },
    onError: (error) => {
      const message = error?.response?.data?.error || error?.message || "Failed to update revision";
      toast({ title: "Revision update failed", description: message, variant: "destructive" });
    },
  });

  const handleSubmitIntake = useCallback(() => {
    if (!documentId) {
      toast({
        title: "Missing document identifier",
        description: "Unable to update intake without a document reference.",
        variant: "destructive",
      });
      return;
    }
    if (intakeDraft.markComplete && !canMarkIntakeComplete) {
      toast({
        title: "Cannot complete intake",
        description: "Duplicate check must be CLEAR and virus scan must be CLEAN before completion.",
        variant: "destructive",
      });
      return;
    }

    intakeMutation.mutate({
      ingestionMethod: intakeDraft.ingestionMethod || undefined,
      sourceSystem: intakeDraft.sourceSystem?.trim() || undefined,
      metadataConfidence: Number.isFinite(intakeDraft.metadataConfidence)
        ? Math.max(0, Math.min(100, intakeDraft.metadataConfidence)) / 100
        : undefined,
      duplicateCheck: {
        status: intakeDraft.duplicateStatus,
        matchedDocumentId: intakeDraft.matchedDocumentId?.trim() || undefined,
        notes: intakeDraft.duplicateNotes?.trim() || undefined,
      },
      virusScan: {
        status: intakeDraft.virusStatus,
        engine: intakeDraft.virusEngine?.trim() || undefined,
        notes: intakeDraft.virusScanNotes?.trim() || undefined,
      },
      extractedMetadata: {
        protocolId: intakeDraft.protocolId?.trim() || undefined,
        siteId: intakeDraft.siteId?.trim() || undefined,
        tmfArtifact: intakeDraft.tmfArtifact?.trim() || undefined,
      },
      // metadataVerification: intakeDraft.metadataVerification || undefined,
      metadataVerification: {
        zoneVerified: true,
        sectionVerified: true,
        artifactVerified: true,
        subArtifactVerified: true,
        verifiedBy: currentUser?.email,
        verifiedAt: new Date(),
      },
      updatedMetadata: {
        title: intakeDraft.documentTitle,
        description: intakeDraft.description || "N/A",
        documentType: intakeDraft.documentType || "OTHER",
        tmfReference: intakeDraft.tmfReference || "01.01.01",
        version: intakeDraft.version || 1,
        documentDate: intakeDraft.documentDate || new Date().toISOString().split('T')[0],
        approvalDate: intakeDraft.approvalDate || new Date().toISOString().split('T')[0],
        author: intakeDraft.author || "N/A",
        pageCount: (intakeDraft.pageCount && intakeDraft.pageCount !== 'N/A') ? Number(intakeDraft.pageCount) : 0,
        legibility: intakeDraft.legibilityClear,

        zoneNumber: intakeDraft.zoneNumber || "1",
        zoneName: intakeDraft.zoneName || "",
        sectionNumber: intakeDraft.sectionNumber || "",
        sectionName: intakeDraft.sectionName || "",
        artifactNumber: intakeDraft.artifactNumber || "",
        artifactName: intakeDraft.artifactName || "",
        subArtifactName: intakeDraft.subArtifactName || "",

        // TMF Metadata fields
        processBasedMetadata: intakeDraft.processBasedMetadata || 'N/A',
        tmfLevel: intakeDraft.tmfLevel || 'N/A',
        coreOrRecommended: intakeDraft.coreOrRecommended || 'N/A',
        ichCode: intakeDraft.ichCode || 'N/A',
        iso14155Reference: intakeDraft.iso14155Reference || 'N/A',
        uniqueIdNumber: intakeDraft.uniqueIdNumber || 'N/A',
        sponsorDocument: intakeDraft.sponsorDocument || false,
        investigatorDocument: intakeDraft.investigatorDocument || false,
        processNumber: intakeDraft.processNumber || 'N/A',
        processName: intakeDraft.processName || 'N/A',
        // Document Level Flags: Map 'X' or true to 'Yes', otherwise 'No'
        trialLevelDocument: (intakeDraft.trialLevelDocument === 'X' || intakeDraft.trialLevelDocument === 'Yes' || intakeDraft.trialLevelDocument === true) ? 'Yes' : 'No',
        trialLevelMilestoneEvent: intakeDraft.trialLevelMilestoneEvent || 'N/A',
        countryRegionLevelDocument: (intakeDraft.countryRegionLevelDocument === 'Yes' || intakeDraft.countryRegionLevelDocument === 'X' || intakeDraft.countryRegionLevelDocument === true) ? 'Yes' : 'No',
        countryLevelMilestoneEvent: intakeDraft.countryLevelMilestoneEvent || 'N/A',
        siteLevelDocument: (intakeDraft.siteLevelDocument === 'Yes' || intakeDraft.siteLevelDocument === 'X' || intakeDraft.siteLevelDocument === true) ? 'Yes' : 'No',
        siteLevelMilestoneEvent: intakeDraft.siteLevelMilestoneEvent || 'N/A',
      },
      notes: intakeDraft.notes?.trim() || undefined,
      markComplete: intakeDraft.markComplete,
      transitionNotes: intakeDraft.transitionNotes?.trim() || undefined,
    });
  }, [documentId, intakeDraft, canMarkIntakeComplete, intakeMutation, toast]);

  const handleSubmitQc = useCallback(() => {
    if (!documentId) {
      toast({
        title: "Missing document identifier",
        description: "Unable to update QC validation without a document reference.",
        variant: "destructive",
      });
      return;
    }

    // If reviewer is provided, automatically move to QC Validation (mark complete)
    const hasReviewer = qcDraft.reviewer && qcDraft.reviewer.trim().length > 0;

    if (qcDraft.markComplete && !canMarkQcComplete && !hasReviewer) {
      toast({
        title: "Cannot complete QC validation",
        description: "All QC checklist items must be completed before closing the stage.",
        variant: "destructive",
      });
      return;
    }

    // // Check if QC decision has been made
    const allChecked = qcDraft.qcDecision !== null && qcDraft.qcDecision !== undefined;

    // // If decision is APPROVE or APPROVE_WITH_COMMENTS, automatically mark complete
    const isApprovalDecision = qcDraft.qcDecision === "APPROVE" || qcDraft.qcDecision === "APPROVE_WITH_COMMENTS";

    // Mark complete if: reviewer provided, OR (approval decision AND document published),
    // or markComplete explicitly set with QC decision made
    const shouldMarkComplete = hasReviewer || (isApprovalDecision && qcDraft.publicationStatus === 'PUBLISHED') || (qcDraft.markComplete && allChecked);

    const strictSponsorPersons = [{
      sendToTmf: {
        isEnabled: qcDraft.sendToTmf || false,
        routingEmail: qcDraft.tmfEmail || "tmf-repository@sponsor.com"
      },
      sendToSafety: {
        isEnabled: qcDraft.sendToSafety || false,
        safetyEmail: qcDraft.safetyEmail || "safety@sponsor.com",
        ccList: qcDraft.safetyCcEmails || []
      }
    }];

    const status = shouldMarkComplete
      ? "COMPLETED"
      : qcDraft.qcDecision
        ? "IN_PROGRESS"
        : "NOT_STARTED";

    // // Format review stages
    const formattedReviewStages = (qcDraft.reviewStages || []).map((stage) => ({
      ...stage,
      assignees: Array.isArray(stage.assignees) ? stage.assignees : [],
      startedAt: stage.startedAt ? new Date(stage.startedAt) : null,
      completedAt: stage.completedAt ? new Date(stage.completedAt) : null,
      dueDate: stage.dueDate ? new Date(stage.dueDate) : null,
    }));

    qcMutation.mutate({
      studyId: document?.study || document?.studyId,
      qaLead:
        qcDraft.qaLead && qcDraft.qaLead.trim().length > 0 ? qcDraft.qaLead.trim() : null,
      reviewer:
        qcDraft.reviewer && qcDraft.reviewer.trim().length > 0 ? qcDraft.reviewer.trim() : null,
      qcDecision: qcDraft.qcDecision || null,
      qcDecisionNotes: qcDraft.qcDecisionNotes?.trim() || null,
      reviewStages: formattedReviewStages.length > 0 ? formattedReviewStages : undefined,
      checklist: qcDraft.checklist,
      status,
      markComplete: shouldMarkComplete,
      transitionNotes: hasReviewer
        ? "Moved to QC Validation with reviewer assigned"
        : (qcDraft.transitionNotes?.trim() || undefined),
      actualEffectiveDate: qcDraft.actualEffectiveDate || null,
      sponsorPersons: strictSponsorPersons || [],
      publicationStatus: qcDraft.publicationStatus || undefined,
    });
  }, [documentId, qcDraft, canMarkQcComplete, qcMutation, toast]);

  const handleSubmitActivation = useCallback(() => {
    if (!documentId) {
      toast({
        title: "Missing document identifier",
        description: "Unable to update activation without a document reference.",
        variant: "destructive",
      });
      return;
    }

    const formatDate = (dateStr) => {
      if (!dateStr || dateStr.trim() === "") return null;
      const date = new Date(dateStr);
      return Number.isNaN(date.getTime()) ? null : date;
    };

    activationMutation.mutate({
      actualEffectiveDate: formatDate(activationDraft.actualEffectiveDate),
      status: activationDraft.status || (activationDraft.isActive ? "ACTIVE" : "INACTIVE"),
      isActive: activationDraft.isActive !== undefined ? activationDraft.isActive : (activationDraft.status === "ACTIVE"),
      distributionStatus: activationDraft.distributionStatus || "NOT_STARTED",
      trainingStatus: activationDraft.trainingStatus || "NOT_STARTED",
      notes: activationDraft.notes?.trim() || null,
      dateEditComment: activationDraft.dateEditComment?.trim() || null,
      // Publish/Retire fields
      publishedAt: activationDraft.publishedAt || null,
      retiredAt: activationDraft.retiredAt || null,
      retireReason: activationDraft.retireReason?.trim() || null,
    });
  }, [documentId, activationDraft, activationMutation, toast]);

  const handleSubmitRevision = useCallback(() => {
    if (!documentId) {
      toast({
        title: "Missing document identifier",
        description: "Unable to update revision without a document reference.",
        variant: "destructive",
      });
      return;
    }

    // Validate archive date: warn and block if a future archive date is selected
    if (revisionDraft.archiveDate && revisionDraft.archiveDate.trim() !== "") {
      const archiveDate = new Date(revisionDraft.archiveDate);
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      if (!Number.isNaN(archiveDate.getTime()) && archiveDate > today) {
        toast({
          title: "Archive date is in the future",
          description: "Please select today or a past date when archiving the document.",
          variant: "destructive",
        });
        return;
      }
    }

    const formatDate = (dateStr) => {
      if (!dateStr || dateStr.trim() === "") return null;
      const date = new Date(dateStr);
      return Number.isNaN(date.getTime()) ? null : date.toISOString();
    };

    revisionMutation.mutate({
      documentRevision: revisionDraft.documentRevision || "NO",
      archiveOlderVersion: revisionDraft.archiveOlderVersion || "NO",
      archiveStatus: revisionDraft.archiveStatus || null,
      archiveDate: formatDate(revisionDraft.archiveDate),
      requiresChange: revisionDraft.requiresChange || false,
      notes: revisionDraft.notes?.trim() || null,
    });
  }, [documentId, revisionDraft, revisionMutation, toast]);

  const handleSubmitReviewPrep = useCallback(() => {
    if (!documentId) {
      toast({
        title: "Missing document identifier",
        description: "Unable to update review preparation without a document reference.",
        variant: "destructive",
      });
      return;
    }

    if (reviewPrepDraft.markComplete && !canMarkReviewPrepComplete) {
      toast({
        title: "Cannot complete review preparation",
        description: "Checklist must be complete and a primary reviewer assigned before progression.",
        variant: "destructive",
      });
      return;
    }

    const meetingValue = reviewPrepDraft.meetingScheduledAt
      ? new Date(reviewPrepDraft.meetingScheduledAt)
      : null;

    const status = reviewPrepDraft.actionType === "approve"
      ? "COMPLETED"
      : reviewPrepDraft.actionType === "reject"
        ? "REJECTED"
        : reviewPrepDraft.actionType === "requestChanges"
          ? "RETURNED"
          : REVIEW_PREP_CHECKLIST_KEYS.some((key) => reviewPrepDraft.checklist?.[key])
            ? "IN_PROGRESS"
            : "NOT_STARTED";

    reviewPrepMutation.mutate({
      coordinator: reviewPrepDraft.coordinator?.trim() || undefined,
      primaryReviewer: reviewPrepDraft.primaryReviewer?.trim() || undefined,
      backupReviewer: reviewPrepDraft.backupReviewer?.trim() || undefined,
      meetingScheduledAt: meetingValue && !Number.isNaN(meetingValue.getTime()) ? meetingValue.toISOString() : undefined,
      supportingPacketUrl: reviewPrepDraft.supportingPacketUrl?.trim() || undefined,
      notes: reviewPrepDraft.notes?.trim() || undefined,
      checklist: reviewPrepDraft.checklist,
      status,
      approvalDate: reviewPrepDraft.approvalDate || undefined,
      actionType: reviewPrepDraft.actionType || undefined,
      actionNotes: reviewPrepDraft.actionNotes || undefined,
      markComplete: reviewPrepDraft.markComplete || false,
    });
  }, [documentId, reviewPrepDraft, canMarkReviewPrepComplete, reviewPrepMutation, toast]);

  const handleReviewPrepApprove = useCallback(({ notes }) => {
    if (!documentId) return;
    setReviewPrepDraft((prev) => ({
      ...prev,
      actionType: "approve",
      approvalDate: new Date().toISOString(),
      actionNotes: notes || null,
      markComplete: true,
    }));
    handleSubmitReviewPrep();
  }, [documentId, handleSubmitReviewPrep]);

  const handleReviewPrepReject = useCallback(({ notes }) => {
    if (!documentId) return;
    setReviewPrepDraft((prev) => ({
      ...prev,
      actionType: "reject",
      actionNotes: notes,
    }));
    handleSubmitReviewPrep();
  }, [documentId, handleSubmitReviewPrep]);

  const handleReviewPrepRequestChanges = useCallback(({ notes }) => {
    if (!documentId) return;
    setReviewPrepDraft((prev) => ({
      ...prev,
      actionType: "requestChanges",
      actionNotes: notes,
    }));
    handleSubmitReviewPrep();
  }, [documentId, handleSubmitReviewPrep]);

  // Refresh handler removed with the refresh button; keep stub if reintroduced later.

  const fileInputRef = useRef(null);
  const [showReplaceDialog, setShowReplaceDialog] = useState(false);
  const [isReplacing, setIsReplacing] = useState(false);
  // When user selects a file inline, open the Replace dialog and pass this file for preview
  const [pendingReplaceFile, setPendingReplaceFile] = useState(null);

  const handleReplaceDocument = useCallback(() => {
    // Open the replace document dialog
    setShowReplaceDialog(true);
  }, []);

  // Actual replace handler that receives the file from the dialog
  const handleReplaceWithFile = useCallback(async (file, options = { commit: true }) => {
    if (!file || !documentId) {
      throw new Error('Missing file or document identifier');
    }

    setIsReplacing(true);

    try {
      console.log('🔄 Starting document replacement...', { documentId, fileName: file.name, fileSize: file.size, commit: options.commit, metadata: options.metadata });

      const response = await isfDocumentWorkflowService.replaceDocument(documentId, file, { commit: options.commit, metadata: options.metadata });
      console.log('✅ Document replacement response:', response);

      // If the replace was a preview (commit=false), do not invalidate or refetch - just return preview data
      if (options.commit === false && (response?.workflow?.preview || response?.preview)) {
        // Preview response (classification/intake) - don't refresh queries
        return response;
      }

      // For a committed replace, refresh workflow data - invalidate all related queries
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workflow', documentId] }),
        queryClient.invalidateQueries({ queryKey: ['document', documentId] }),
        queryClient.invalidateQueries({ queryKey: ['documents'] }),
        queryClient.invalidateQueries({ queryKey: ['document-audit-trail', documentId] }),
      ]);

      // Force refetch to get updated data immediately
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ['workflow', documentId], type: 'active' }),
        queryClient.refetchQueries({ queryKey: ['document', documentId], type: 'active' }),
        queryClient.refetchQueries({ queryKey: ['document-audit-trail', documentId], type: 'active' }),
      ]);

      // Trigger onWorkflowUpdate callback if provided to notify parent component
      if (onWorkflowUpdate) {
        console.log('🔄 Calling onWorkflowUpdate callback to refresh parent component');
        await onWorkflowUpdate();
      }

      toast({
        title: "Document replaced successfully",
        description: "Workflow has been reset to QC Validation stage.",
        variant: "default",
      });

      // Return response so caller (ReplaceDocumentDialog) can display classification / PHI details
      return response;

    } finally {
      setIsReplacing(false);
    }
  }, [documentId, queryClient, onWorkflowUpdate, toast]);

  const handleFileChange = useCallback(async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    if (!documentId) {
      toast({
        title: "Missing document identifier",
        description: "Unable to replace document without a document reference.",
        variant: "destructive",
      });
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    // Open replace dialog in PREVIEW mode with the chosen file
    setPendingReplaceFile(file);
    setShowReplaceDialog(true);

    // Clear local file input so user can re-select if needed
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }

    toast({
      title: 'Preview available',
      description: 'A preview will be generated. Click "Update metadata & Replace" to apply changes.',
      variant: 'default',
    });
  }, [documentId, toast]);

  const handleSubmitReviewApproval = useCallback(() => {
    if (!documentId) {
      toast({
        title: "Missing document identifier",
        description: "Unable to update review and approval without a document reference.",
        variant: "destructive",
      });
      return;
    }

    // Get the latest draft state - use functional update to get current state
    const currentDraft = reviewApprovalDraft;

    // Format review stages - use current draft stages
    const formattedReviewStages = (currentDraft.reviewStages || []).map((stage) => ({
      ...stage,
      assignees: Array.isArray(stage.assignees) ? stage.assignees : [],
      startedAt: stage.startedAt ? new Date(stage.startedAt) : null,
      completedAt: stage.completedAt ? new Date(stage.completedAt) : null,
      dueDate: stage.dueDate ? new Date(stage.dueDate) : null,
    }));

    // Format approval stages - use current draft stages
    const formattedApprovalStages = (currentDraft.approvalStages || []).map((stage) => {
      const normalizedStatus = stage.status === "SIGNED" ? "COMPLETED" : stage.status;
      return {
        ...stage,
        status: normalizedStatus,
        assignees: Array.isArray(stage.assignees) ? stage.assignees : [],
        startedAt: stage.startedAt ? new Date(stage.startedAt) : null,
        completedAt: stage.completedAt ? new Date(stage.completedAt) : null,
        dueDate: stage.dueDate ? new Date(stage.dueDate) : null,
        eSignature: stage.eSignature
          ? {
            ...stage.eSignature,
            signedAt: stage.eSignature.signedAt ? new Date(stage.eSignature.signedAt) : null,
          }
          : undefined,
      };
    });

    reviewApprovalMutation.mutate({
      review: {
        stages: formattedReviewStages,
        notes: reviewApprovalDraft.reviewNotes?.trim() || null,
        delegateReviewer: reviewApprovalDraft.delegateReviewer?.trim() || null,
        initialInReviewDate: reviewApprovalDraft.initialInReviewDate ? new Date(reviewApprovalDraft.initialInReviewDate) : null,
        reviewCyclesCount: reviewApprovalDraft.reviewCyclesCount || 0,
      },
      approval: {
        stages: formattedApprovalStages,
        notes: reviewApprovalDraft.approvalNotes?.trim() || null,
      },
      consolidation: {
        status: reviewApprovalDraft.consolidationStatus || "NOT_STARTED",
        findingsResolved: reviewApprovalDraft.findingsResolved || false,
        notes: reviewApprovalDraft.consolidationNotes?.trim() || null,
        initialSteadyStateDate: reviewApprovalDraft.initialSteadyStateDate ? new Date(reviewApprovalDraft.initialSteadyStateDate) : null,
        consolidationCompletedDate: reviewApprovalDraft.consolidationCompletedDate ? new Date(reviewApprovalDraft.consolidationCompletedDate) : null,
      },
      actionType: reviewApprovalDraft.actionType || undefined,
      actionNotes: reviewApprovalDraft.actionNotes?.trim() || undefined,
    });
  }, [documentId, reviewApprovalDraft, reviewApprovalMutation, toast]);

  const handleReviewApprovalApprove = useCallback(({ notes }) => {
    if (!documentId) return;
    setReviewApprovalDraft((prev) => ({
      ...prev,
      actionType: "approve",
      actionNotes: notes || null,
    }));
    handleSubmitReviewApproval();
  }, [documentId, handleSubmitReviewApproval]);

  const handleReviewApprovalReject = useCallback(({ notes }) => {
    if (!documentId) return;
    setReviewApprovalDraft((prev) => ({
      ...prev,
      actionType: "reject",
      actionNotes: notes,
    }));
    handleSubmitReviewApproval();
  }, [documentId, handleSubmitReviewApproval]);

  const handleReviewApprovalRequestChanges = useCallback(({ notes }) => {
    if (!documentId) return;
    setReviewApprovalDraft((prev) => ({
      ...prev,
      actionType: "requestChanges",
      actionNotes: notes,
    }));
    handleSubmitReviewApproval();
  }, [documentId, handleSubmitReviewApproval]);

  const documentRecords = useMemo(() => {
    const baseRecord = {
      id: document?._id || "primary",
      title: documentTitle,
      protocol: protocolId,
      site: siteId,
      version: document?.version ?? 1,
      author: document?.authorName || document?.author || "Unknown Author",
      modifiedAt: document?.modificationDate ? new Date(document.modificationDate).toLocaleString() : "N/A",
      owner: ownerName,
      status: documentStatus,
      progress: workflow?.metrics?.reviewProgress
        ? Math.round(workflow.metrics.reviewProgress * 100)
        : 40,
      tags: complianceTags,
    };

    const previous = (document?.previousVersions ?? []).map((entry, index) => ({
      id: `${entry.version ?? index}-previous`,
      title: `${documentTitle} v${entry.version ?? index}`,
      protocol: protocolId,
      site: siteId,
      version: entry.version ?? index,
      author: entry.uploadedByName || entry.uploadedBy || "Legacy",
      modifiedAt: entry.uploadedAt ? new Date(entry.uploadedAt).toLocaleString() : "N/A",
      owner: ownerName,
      status: "Archived",
      progress: 100,
      tags: ["Historical", "Locked"],
    }));

    return [baseRecord, ...previous].slice(0, 4);
  }, [document, documentTitle, protocolId, siteId, ownerName, documentStatus, workflow]);

  const isIntakeStage = activeStageDetail?.key === "INTAKE";
  const isQcStage = activeStageDetail?.key === "QC_VALIDATION";
  const isReviewPrepStage = activeStageDetail?.key === "REVIEW_PREPARATION";
  const isRevisionStage = activeStageDetail?.key === "REVISION";
  const isSavingStage = isIntakeStage
    ? intakeMutation.isPending
    : isQcStage
      ? qcMutation.isPending
      : isReviewPrepStage
        ? reviewPrepMutation.isPending
        : isRevisionStage
          ? revisionMutation.isPending
          : false;

  const lifecycleHighlights = useMemo(
    () => [
      {
        key: "owner",
        title: "Current Owner",
        value: ownerName,
        description: "Routed from governance policy set with delegated backup reviewer.",
        icon: Users,
      },
      {
        key: "cycle",
        title: "Cycle Time",
        value: `${workflow?.metrics?.cycleTimeDays ?? 12} days`,
        description: `Target SLA: 18 days • Last evaluated ${workflow?.metrics?.lastEvaluatedAt
          ? new Date(workflow.metrics.lastEvaluatedAt).toLocaleString()
          : "N/A"
          }`,
        icon: Activity,
        progress: Math.min((workflow?.metrics?.cycleTimeDays ?? 12) * 5, 100),
      },
      {
        key: "compliance",
        title: "Compliance",
        value: `${workflow?.compliance?.training?.completed ?? 0}/${workflow?.compliance?.training?.assignments ?? 0
          }`,
        description: "Training acknowledgements completed",
        icon: ShieldCheck,
      },
    ],
    [ownerName, workflow?.metrics, workflow?.compliance],
  );

  const lifecycleBadges = [
    {
      key: "completed",
      label: `${lifecycleStats.completedCount} Completed`,
      className: "bg-emerald-50 text-emerald-700",
    },
    lifecycleStats.activeStage
      ? {
        key: "active",
        label: `Active: ${lifecycleStats.activeStage.title}`,
        className: "bg-sky-50 text-sky-700",
      }
      : {
        key: "inactive",
        label: "No Active Stage",
        className: "bg-slate-100 text-slate-600",
      },
    {
      key: "pending",
      label: `${lifecycleStats.pendingCount} Remaining`,
      className: "bg-slate-100 text-slate-600",
    },
  ];

  const readinessCards = [
    {
      key: "completed",
      title: "Completed",
      description: `${lifecycleStats.completedCount} of ${lifecycleStats.total} stages`,
      badge: "Ready",
      badgeTone: "bg-emerald-100 text-emerald-700",
    },
    {
      key: "pending",
      title: "Pending",
      description: `${lifecycleStats.pendingCount} stages awaiting action`,
      badge: "Upcoming",
      badgeTone: "bg-slate-100 text-slate-600",
    },
  ];

  const isDrawerLayout = layout === "drawer";

  const isDocumentPublished = stageSequence[3]?.statusKey === "completed";

  return (
    <div
      className={cn(
        "flex flex-col",
        isDrawerLayout ? "h-full min-h-0" : "min-h-[720px]",
        className,
      )}
    >
      <div
        className={cn(
          "grid gap-5",
          isDrawerLayout ? "" : "max-w-6xl mx-auto",
        )}
      >
        <section
          className={cn(
            "rounded-xl border-2 border-blue-200 bg-gradient-to-br from-blue-50/50 via-white to-white shadow-md",
            isDrawerLayout ? "p-3" : "p-4",
          )}
        >
          {/* Compact Header with Title and Status */}
          <div className="flex flex-wrap items-start justify-between gap-3 mb-3 pb-3 border-b border-blue-200/50">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-sm font-bold text-slate-900">Clinical Trial Site Information Form</h2>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4">Document Lifecycle</Badge>
              </div>
              <h1 className="text-base font-semibold text-slate-900 truncate">{documentTitle}</h1>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <Badge className="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-semibold text-sky-700">
                {documentStatus}
              </Badge>
              <Badge className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
                {currentLifecycle}
              </Badge>
              {activeRejection && (
                <Badge className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700 border-red-200 gap-1">
                  <XCircle className="h-3 w-3" />
                  Rejected
                </Badge>
              )}
            </div>
          </div>

          {/* Compact Information Grid */}
          <div className="grid grid-cols-2 md:grid-cols-2 gap-2.5">
            {/* Document ID */}
            <div className="rounded-md border border-slate-200 bg-white p-2">
              <div className="flex items-center gap-1.5 mb-0.5">
                <Fingerprint className="h-3 w-3 text-slate-400" />
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">ID</p>
              </div>
              <p className="text-xs font-mono font-medium text-slate-900 break-all" title={displayDocumentId} style={{ wordBreak: 'break-all' }}>
                {displayDocumentId}
              </p>
            </div>

            {/* Study */}
            <div className="rounded-md border border-slate-200 bg-white p-2">
              <div className="flex items-center gap-1.5 mb-0.5">
                <Building2 className="h-3 w-3 text-slate-400" />
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Study</p>
              </div>
              <p className="text-xs font-semibold text-slate-900 truncate" title={document.study}>{document.study}</p>
            </div>

            {/* Protocol ID - only show if not "Not assigned" */}
            {protocolId !== "Not assigned" && (
              <div className="rounded-md border border-slate-200 bg-white p-2">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <Hash className="h-3 w-3 text-slate-400" />
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Protocol</p>
                </div>
                <p className="text-xs font-semibold text-slate-900 truncate" title={protocolId}>{protocolId}</p>
              </div>
            )}
          </div>

          {/* Optional badges row - compact */}
          {(document?.version || document?.documentType || document?.source === 'email_attachment') && (
            <div className="flex flex-wrap items-center gap-2 mt-2.5 pt-2 border-t border-slate-200/50">
              {document?.source === 'email_attachment' && (
                <SimpleTooltip content="Document imported from email">
                  <Badge
                    variant="secondary"
                    className="h-4 px-1.5 text-[10px] bg-blue-50 text-blue-700 border-blue-200 flex items-center gap-1"
                  >
                    <Mail className="w-2.5 h-2.5" />
                    Email
                  </Badge>
                </SimpleTooltip>
              )}
              {document?.version && (
                <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
                  v{document.version}
                </Badge>
              )}
              {document?.documentType && (
                <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
                  {document.documentType}
                </Badge>
              )}
            </div>
          )}
        </section>

        {/* Rejection Alert Banner */}
        {activeRejection && (
          <section className="rounded-2xl border-2 border-red-200 bg-gradient-to-r from-red-50 to-orange-50 p-5 shadow-sm">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-red-100 flex-shrink-0">
                  <XCircle className="h-6 w-6 text-red-600" />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-base font-bold text-red-900">Document Rejected</h3>
                    <Badge className="bg-red-100 text-red-700 border-red-200 text-xs">
                      {activeRejection.stageLabel}
                    </Badge>
                  </div>
                  <p className="text-sm text-red-800 max-w-2xl">
                    <span className="font-semibold">Reason:</span> {activeRejection.reason}
                  </p>
                  {activeRejection.actionRequired && (
                    <p className="text-sm text-red-700">
                      <span className="font-semibold">Action Required:</span> {activeRejection.actionRequired}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-3 text-xs text-red-600">
                    {activeRejection.rejectedByName && (
                      <span>Rejected by: <span className="font-medium">{activeRejection.rejectedByName}</span></span>
                    )}
                    {activeRejection.rejectedAt && (
                      <span>• {new Date(activeRejection.rejectedAt).toLocaleDateString()}</span>
                    )}
                    {activeRejection.dueDate && (
                      <span className="font-semibold">• Due: {new Date(activeRejection.dueDate).toLocaleDateString()}</span>
                    )}
                    {activeRejection.returnToStage && (
                      <span>• Returned to: {activeRejection.returnToStage.replace(/_/g, ' ')}</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex gap-2 flex-shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  className="border-red-200 text-red-700 hover:bg-red-100"
                  onClick={() => {
                    const stage = stageSequence.find(s => s.statusKey === 'rejected');
                    if (stage) handleStageOpen(stage);
                  }}
                >
                  View Details
                </Button>
                <Button
                  size="sm"
                  className="bg-red-600 text-white hover:bg-red-700 gap-1.5"
                  onClick={() => handleResolveRejection(activeRejection.stage)}
                  disabled={resolveRejectionMutation.isPending}
                >
                  {resolveRejectionMutation.isPending ? (
                    "Resolving..."
                  ) : (
                    <>
                      <CheckCircle2 className="h-4 w-4" />
                      Mark as Resolved
                    </>
                  )}
                </Button>
              </div>
            </div>
          </section>
        )}

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                Lifecycle Workflow
              </h2>
              <p className="text-xs text-slate-500">
                Inspection-ready overview of document lifecycle stages and compliance status.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs text-slate-500">
              {lifecycleBadges.map((chip) => (
                <Badge
                  key={chip.key}
                  className={cn("rounded-full px-3 py-1 font-semibold", chip.className)}
                >
                  {chip.label}
                </Badge>
              ))}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {/* {stageSequence.map((stage, index) => {
                  // Determine if stage is locked based on previous stage completion
                  // Stage 0 (INTAKE) is never locked
                  // Stage N is locked if Stage N-1 is not completed (statusKey !== "completed" AND progress < 100)
                  let isLocked = false;
                  let lockedReason = null;
                  
                  if (index > 0) {
                    const prevStage = stageSequence[index - 1];
                    const prevProgress = Number.isFinite(prevStage.progress) ? prevStage.progress : 0;
                    const isPrevCompleted = prevStage.statusKey === "completed" || prevProgress >= 100;
                    
                    if (!isPrevCompleted) {
                      isLocked = true;
                      lockedReason = `Complete "${prevStage.title}" first`;
                    }
                  }
                  
                  // Check role-based access - lock stage if user doesn't have permission
                  if (!isLocked && userRole && stage.key) {
                    const canOpen = canOpenWorkflowStage(userRole, stage.key);
                    if (!canOpen) {
                      isLocked = true;
                      lockedReason = `Your role (${userRole}) does not have access to this stage`;
                    }
                  }
                  
                  return (
                  <StageCard
                    key={stage.key}
                    stage={stage}
                    index={index}
                    actions={STAGE_ACTIONS[stage.key] || STAGE_ACTIONS.AUDIT_REPORTING}
                    statusConfig={stage.statusConfig}
                    userRole={userRole}
                    onOpen={handleStageOpen}
                    isLocked={isLocked}
                    lockedReason={lockedReason}
                  />
                  );
                })} */}
            {stageSequence.map((stage, index) => {
              let isLocked = false;
              let lockedReason = null;

              // 1️⃣ Document published check (HIGHEST priority)
              const isDocumentPublished =
                stageSequence[3]?.statusKey === "completed" && index <= 3;

              if (!isDocumentPublished) {
                // 2️⃣ Previous-stage locking
                if (index > 0) {
                  const prevStage = stageSequence[index - 1];
                  const prevProgress = Number.isFinite(prevStage.progress)
                    ? prevStage.progress
                    : 0;

                  const isPrevCompleted =
                    prevStage.statusKey === "completed" || prevProgress >= 100;

                  if (!isPrevCompleted) {
                    isLocked = true;
                    lockedReason = `Complete "${prevStage.title}" first`;
                  }
                }

                // 3️⃣ Role-based access
                if (!isLocked && userRole && stage.key) {
                  const canOpen = canOpenWorkflowStage(userRole, stage.key);
                  if (!canOpen) {
                    isLocked = true;
                    lockedReason = `Your role (${userRole}) does not have access to this stage`;
                  }
                }
              }

              return (
                <StageCard
                  key={stage.key}
                  stage={stage}
                  index={index}
                  actions={STAGE_ACTIONS[stage.key] || STAGE_ACTIONS.AUDIT_REPORTING}
                  statusConfig={stage.statusConfig}
                  userRole={userRole}
                  onOpen={handleStageOpen}
                  isLocked={isLocked}
                  lockedReason={lockedReason}
                  hideActions={isDocumentPublished}
                />
              );
            })}
          </div>
        </section>

        {!isDrawerLayout && (
          <>
            <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Document Records
                  </h2>
                  <p className="text-xs text-slate-500">
                    Key metadata snapshots with quick actions for lifecycle control.
                  </p>
                </div>
                <Button size="sm" variant="outline" className="gap-2 border-slate-300 text-slate-600">
                  <FileText className="h-4 w-4" />
                  Export Selected
                </Button>
              </div>
              <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
                {documentRecords.map((record) => (
                  <article
                    key={record.id}
                    className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
                  >
                    <div className="space-y-1.5 pb-3 border-b border-slate-100">
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold text-slate-900 line-clamp-2">{record.title}</h3>
                        <Badge className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                          v{record.version}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-slate-500">
                        Protocol {record.protocol} • Site {record.site}
                      </p>
                    </div>
                    <div className="space-y-3 pt-3 text-xs text-slate-600">
                      <div className="grid grid-cols-2 gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
                        <div>
                          <p className="text-[10px] uppercase tracking-wide text-slate-400">Owner</p>
                          <p className="font-semibold text-slate-900">{record.owner}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-[10px] uppercase tracking-wide text-slate-400">Status</p>
                          <Badge className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-700">
                            {record.status}
                          </Badge>
                        </div>
                      </div>
                      <div>
                        <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500">
                          <span>Progress</span>
                          <span>{Math.min(record.progress ?? 0, 100)}%</span>
                        </div>
                        <div className="mt-1.5 h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
                          <div
                            className="h-full bg-sky-500 transition-all duration-500 ease-in-out"
                            style={{ width: `${Math.min(record.progress ?? 0, 100)}%` }}
                          />
                        </div>
                      </div>
                      <SimpleTooltip content={`Last modified by ${record.author}`}>
                        <div className="flex items-center gap-1.5 text-slate-500">
                          <Clock className="h-3 w-3 text-slate-400" />
                          <span className="text-[11px]">Updated {record.modifiedAt}</span>
                        </div>
                      </SimpleTooltip>
                      <div className="flex flex-wrap gap-1">
                        {record.tags.map((tag) => (
                          <Badge
                            key={`${record.id}-${tag}`}
                            className="rounded-full border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600"
                          >
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
                      <div className="flex gap-1.5">
                        <SimpleTooltip content="Open review workspace">
                          <Button size="sm" className="bg-sky-600 text-white hover:bg-sky-600/90">
                            Review
                          </Button>
                        </SimpleTooltip>
                        <SimpleTooltip content="Complete approval and capture e-signature">
                          <Button size="sm" variant="outline" className="border-slate-200 text-slate-600 hover:bg-slate-100">
                            Approve
                          </Button>
                        </SimpleTooltip>
                      </div>
                      <div className="flex gap-1.5">
                        <SimpleTooltip content="Archive to retention vault">
                          <Button size="icon" variant="ghost" className="text-slate-500 hover:text-slate-900">
                            <Archive className="h-4 w-4" />
                          </Button>
                        </SimpleTooltip>
                        <SimpleTooltip content="Reassign owner or workflow stage">
                          <Button size="icon" variant="ghost" className="text-slate-500 hover:text-slate-900">
                            <Users className="h-4 w-4" />
                          </Button>
                        </SimpleTooltip>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Audit Logs
                  </h2>
                  <p className="text-xs text-slate-500">
                    Recent lifecycle events captured for inspection readiness.
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-2 border-slate-300 text-slate-600"
                  onClick={() => {
                    console.log('View Full Trail clicked, documentId:', documentId);
                    console.log('Current audit trail entries:', auditTrailEntries);
                    console.log('API audit trail:', apiAuditTrail);
                    console.log('Is loading:', isLoadingAuditTrail);
                    console.log('Error:', auditTrailError);
                    // Refetch audit trail when opening dialog
                    if (documentId) {
                      refetchAuditTrail();
                    }
                    setShowFullAuditTrail(true);
                  }}
                >
                  <FileText className="h-4 w-4" />
                  View Full Trail
                </Button>
              </div>
              <div className="space-y-3">
                {auditTrailEntries.slice(0, 5).map((entry, index) => (
                  <div
                    key={`${entry?.timestamp ?? index}-${index}`}
                    className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                  >
                    <div className="mt-1 flex h-8 w-8 items-center justify-center rounded-full bg-sky-100 text-sky-600">
                      <Clock className="h-4 w-4" />
                    </div>
                    <div className="space-y-1 text-sm text-slate-600">
                      <div className="font-semibold text-slate-900">{entry?.action ?? "Lifecycle event"}</div>
                      <div className="text-xs text-slate-500">
                        {entry?.timestamp ? new Date(entry.timestamp).toLocaleString() : "Timestamp unavailable"}
                        {entry?.actor ? ` • ${entry.actor}` : ""}
                        {entry?.ipAddress ? ` • IP: ${entry.ipAddress}` : ""}
                      </div>
                      {entry?.details && (
                        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-[11px] text-slate-500">
                          {typeof entry.details === "string"
                            ? entry.details
                            : JSON.stringify(entry.details, null, 2)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {auditTrailEntries.length === 0 && !isLoadingAuditTrail && (
                  <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500">
                    No audit entries logged yet. Activity will appear here as reviewers take action.
                  </div>
                )}
                {isLoadingAuditTrail && (
                  <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500">
                    Loading audit trail...
                  </div>
                )}
              </div>
            </section>
          </>
        )}
      </div>

      {/* Full Audit Trail Dialog */}
      <Dialog open={showFullAuditTrail} onOpenChange={setShowFullAuditTrail}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold text-gray-900">
              Complete Audit Trail - {documentTitle}
            </DialogTitle>
            <DialogDescription className="text-sm text-gray-500">
              Complete history of all actions and changes for this document
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-4">
            {isLoadingAuditTrail ? (
              <div className="text-center py-8 text-sm text-slate-500">
                Loading audit trail...
              </div>
            ) : auditTrailEntries.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500">
                No audit entries found for this document.
              </div>
            ) : (
              <div className="space-y-3">
                {auditTrailEntries.map((entry, index) => (
                  <div
                    key={`${entry?.timestamp ?? index}-${index}`}
                    className="flex items-start gap-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                  >
                    <div className="mt-1 flex h-10 w-10 items-center justify-center rounded-full bg-sky-100 text-sky-600 flex-shrink-0">
                      <Clock className="h-5 w-5" />
                    </div>
                    <div className="flex-1 space-y-2 text-sm text-slate-600">
                      <div className="font-semibold text-slate-900">{entry?.action ?? "Lifecycle event"}</div>
                      <div className="text-xs text-slate-500 space-y-1">
                        <div>
                          <span className="font-medium">When:</span>{" "}
                          {entry?.timestamp ? new Date(entry.timestamp).toLocaleString() : "Timestamp unavailable"}
                        </div>
                        {entry?.actor && (
                          <div>
                            <span className="font-medium">Who:</span> {entry.actor}
                          </div>
                        )}
                        {entry?.ipAddress && (
                          <div>
                            <span className="font-medium">IP Address:</span> {entry.ipAddress}
                          </div>
                        )}
                      </div>
                      {entry?.details && (
                        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
                          <div className="font-medium mb-1 text-slate-700">Details:</div>
                          <pre className="whitespace-pre-wrap text-xs">
                            {typeof entry.details === "string"
                              ? entry.details
                              : JSON.stringify(entry.details, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={isStageSheetOpen} onOpenChange={handleStageSheetToggle}>
        <DialogContent
          className="w-full lg:max-w-6xl overflow-y-auto max-h-[90vh]"
          aria-describedby={activeStageDetail ? undefined : "stage-detail-placeholder"}
        >
          {activeStageDetail ? (
            <div className="flex h-full flex-col gap-6">
              <DialogHeader className="space-y-3 text-left">
                <DialogTitle className="text-lg font-semibold text-slate-900">
                  {activeStageDetail.title}
                </DialogTitle>
                <DialogDescription className="text-sm text-slate-500">
                  {activeStageDetail.subtitle}
                </DialogDescription>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className={cn("rounded-full border text-[11px] font-semibold", activeStageDetail.statusConfig?.tone)}>
                    {activeStageDetail.statusLabel || activeStageDetail.statusConfig?.label}
                  </Badge>
                  <Badge className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                    Progress {(() => {
                      // Use real-time progress from draft for active stages
                      let progress = activeStageDetail.progress;
                      if (activeStageDetail.key === "INTAKE") {
                        progress = intakeDraftProgress;
                      } else if (activeStageDetail.key === "QC_VALIDATION") {
                        progress = qcDraftMetrics?.progress ?? 0;
                      }
                      return Number.isFinite(progress) ? `${Math.min(Math.max(progress, 0), 100)}%` : "—";
                    })()}
                  </Badge>
                </div>
              </DialogHeader>
              <div className="space-y-4 pr-2">
                <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-3">
                    Key Metrics
                  </p>

                  <div className="mt-4 grid grid-cols-4 gap-3">
                    {(() => {
                      const metrics = (() => {
                        // 🔒 LOGIC UNCHANGED
                        if (activeStageDetail.key === "INTAKE") {
                          return [
                            { label: "Security Checks", value: `${intakeDraftMetrics.security.complete}/${intakeDraftMetrics.security.total} (${intakeDraftMetrics.security.percent}%)` },
                            { label: "TMF Verification", value: intakeDraftMetrics.metadata.total > 0 ? `${intakeDraftMetrics.metadata.verified}/${intakeDraftMetrics.metadata.total} (${intakeDraftMetrics.metadata.percent}%)` : "N/A" },
                            {
                              label: "Ingestion & Legibility",
                              value: `${intakeDraftMetrics.ingestionLegibility.complete}/${intakeDraftMetrics.ingestionLegibility.total} (${intakeDraftMetrics.ingestionLegibility.percent}%)`
                            },

                            { label: "Pending Checks", value: intakeDraftPendingChecks },
                          ];
                        } else if (activeStageDetail.key === "QC_VALIDATION") {
                          return [
                            {
                              label: "QC + Publication",
                              value: `${qcDraftMetrics.completed}/${qcDraftMetrics.total} (${qcDraftMetrics.progress}%)`,
                            },
                          ];
                        } else if (activeStageDetail.key === "REVIEW") {
                          const allReviewStages = reviewApprovalDraft?.reviewStages ?? [];
                          const allApprovalStages = reviewApprovalDraft?.approvalStages ?? [];

                          const activeReviewStagesForMetrics = allReviewStages.filter(
                            stage => stage.status !== "PENDING" || stage.startedAt || stage.completedAt
                          );
                          const activeApprovalStagesForMetrics = allApprovalStages.filter(
                            stage => stage.status !== "PENDING" || stage.startedAt || stage.completedAt
                          );

                          const reviewCompleted = activeReviewStagesForMetrics.filter(s => s.status === "COMPLETED").length;
                          const approvalCompleted = activeApprovalStagesForMetrics.filter(
                            s => s.status === "COMPLETED" || s.status === "SIGNED"
                          ).length;

                          const calculateStageProgress = (stage) => {
                            const isDefaultStage = stage.status === "PENDING" && !stage.startedAt && !stage.completedAt;
                            if (isDefaultStage) return 0;
                            const fields = [
                              stage.name && stage.name.trim() !== "",
                              stage.role && stage.role.trim() !== "",
                              stage.dueDate && stage.dueDate !== null && stage.dueDate !== "",
                            ];
                            const filledFields = fields.filter(Boolean).length;
                            return fields.length > 0 ? (filledFields / fields.length) * 100 : 0;
                          };

                          const reviewStageProgresses = activeReviewStagesForMetrics.map(calculateStageProgress);
                          const reviewStagesProgress =
                            activeReviewStagesForMetrics.length > 0
                              ? reviewStageProgresses.reduce((sum, p) => sum + p, 0) / activeReviewStagesForMetrics.length
                              : 0;

                          const reviewNotesProgress = reviewApprovalDraft?.reviewNotes?.trim() ? 100 : 0;
                          const initialDateProgress = reviewApprovalDraft?.initialInReviewDate ? 100 : 0;

                          let localReviewProgressPct =
                            activeReviewStagesForMetrics.length > 0
                              ? reviewStagesProgress * 0.8 + reviewNotesProgress * 0.1 + initialDateProgress * 0.1
                              : [reviewNotesProgress, initialDateProgress].filter(p => p > 0).reduce((a, b) => a + b, 0) || 0;

                          localReviewProgressPct = Math.min(Math.max(localReviewProgressPct, 0), 100);

                          const approvalStageProgresses = activeApprovalStagesForMetrics.map(calculateStageProgress);
                          const approvalStagesProgress =
                            activeApprovalStagesForMetrics.length > 0
                              ? approvalStageProgresses.reduce((sum, p) => sum + p, 0) / activeApprovalStagesForMetrics.length
                              : 0;

                          const approvalNotesProgress = reviewApprovalDraft?.approvalNotes?.trim() ? 100 : 0;

                          let localApprovalProgressPct =
                            activeApprovalStagesForMetrics.length > 0
                              ? approvalStagesProgress * 0.9 + approvalNotesProgress * 0.1
                              : approvalNotesProgress;

                          localApprovalProgressPct = Math.min(Math.max(localApprovalProgressPct, 0), 100);

                          return [
                            { label: "Review Stages", value: `${reviewCompleted}/${activeReviewStagesForMetrics.length}` },
                            { label: "Approval Stages", value: `${approvalCompleted}/${activeApprovalStagesForMetrics.length}` },
                            { label: "Review Progress", value: `${Math.round(localReviewProgressPct)}%` },
                            { label: "Approval Progress", value: `${Math.round(localApprovalProgressPct)}%` },
                          ];
                        }

                        return activeStageDetail.metrics;
                      })();

                      const cardStyles = [
                        "bg-gradient-to-br from-slate-50 to-slate-100 text-slate-800 border border-slate-200",
                        "bg-gradient-to-br from-emerald-50 to-emerald-100 text-emerald-700 border border-emerald-200",
                        "bg-gradient-to-br from-amber-50 to-amber-100 text-amber-700 border border-amber-200",
                        "bg-gradient-to-br from-rose-50 to-rose-100 text-rose-700 border border-rose-200",
                      ];

                      return metrics?.map((metric, idx) => (
                        <div
                          key={metric.label || idx}
                          className={`rounded-lg p-3 text-center ${cardStyles[idx % cardStyles.length]}`}
                        >
                          <p className="text-lg font-bold truncate">
                            {metric.value ?? "—"}
                          </p>
                          <p className="text-sm font-bold tracking-wider">
                            {metric.label}
                          </p>
                        </div>
                      ));
                    })()}
                  </div>
                </div>



                {isIntakeStage ? (
                  <ISFIntakeStageForm
                    draft={intakeDraft}
                    onChange={updateIntakeDraft}
                    studyTitle={studyTitle}
                    disabled={intakeMutation.isPending}
                    canMarkComplete={canMarkIntakeComplete}
                    document={document}
                    onReplaceDocument={handleReplaceDocument}
                    onLegibilityChange={handleLegibilityChange}
                  />
                ) : isQcStage ? (
                  <ISFQcValidationForm
                    draft={qcDraft}
                    updateDraft={updateQcDraft}
                    studyTitle={studyTitle}
                    disabled={qcMutation.isPending}
                    canMarkComplete={canMarkQcComplete}
                    isLoading={qcMutation.isPending}
                    intakeData={workflow?.intake}
                    document={document}
                    onReplaceDocument={handleReplaceDocument}
                  />
                ) : isRevisionStage ? (
                  <RevisionForm
                    draft={revisionDraft}
                    updateDraft={updateRevisionDraft}
                    disabled={revisionMutation.isPending}
                    isLoading={revisionMutation.isPending}
                    document={document}
                    onSave={handleSubmitRevision}
                  />
                ) : (
                  <>
                    {activeStageDetail.compliance?.length ? (
                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                          Compliance & Controls
                        </p>
                        <ComplianceTagList tags={activeStageDetail.compliance} className="mt-3" />
                      </div>
                    ) : null}
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Suggested Actions
                      </p>
                      <StageActionButtons
                        actions={STAGE_ACTIONS[activeStageDetail.key] || STAGE_ACTIONS.AUDIT_REPORTING}
                        className="mt-3"
                        disabled
                      />
                    </div>
                  </>
                )}
              </div>
              <DialogFooter className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <DialogClose asChild>
                    <Button variant="outline" className="border-slate-200" disabled={isSavingStage}>
                      Close
                    </Button>
                  </DialogClose>
                  {/* Reject Button - shown for QC, Review Prep, Review, and Approval stages */}
                  {(isQcStage || isReviewPrepStage) && (
                    <Button
                      variant="outline"
                      className="gap-2 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
                      onClick={() => handleOpenRejectionDialog(activeStageDetail?.key)}
                      disabled={isSavingStage || rejectionMutation.isPending}
                    >
                      <XCircle className="h-4 w-4" />
                      Reject
                    </Button>
                  )}
                </div>
                {isIntakeStage ? (
                  <Button
                    className="gap-2 bg-sky-600 text-white hover:bg-sky-600/90"
                    onClick={handleSubmitIntake}
                    disabled={intakeMutation.isPending}
                  >
                    {intakeMutation.isPending ? "Saving..." : "Save Intake"}
                  </Button>
                ) : isQcStage ? (
                  <Button
                    className="gap-2 bg-sky-600 text-white hover:bg-sky-600/90"
                    onClick={handleSubmitQc}
                    disabled={qcMutation.isPending}
                  >
                    {qcMutation.isPending ? "Saving..." : "Save QC Validation"}
                  </Button>
                ) : isReviewPrepStage ? (
                  <Button
                    className="gap-2 bg-sky-600 text-white hover:bg-sky-600/90"
                    onClick={handleSubmitReviewPrep}
                    disabled={reviewPrepMutation.isPending}
                  >
                    {reviewPrepMutation.isPending ? "Saving..." : "Save Review Prep"}
                  </Button>
                ) : isRevisionStage ? (
                  <Button
                    className="gap-2 bg-sky-600 text-white hover:bg-sky-600/90"
                    onClick={handleSubmitRevision}
                    disabled={revisionMutation.isPending}
                  >
                    {revisionMutation.isPending ? "Saving..." : "Save Revision"}
                  </Button>
                ) : (
                  <Button className="gap-2 bg-sky-600 text-white hover:bg-sky-600/90">
                    <FileText className="h-4 w-4" />
                    View Stage Tasks
                  </Button>
                )}
              </DialogFooter>
            </div>
          ) : (
            <div
              id="stage-detail-placeholder"
              className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-slate-500"
            >
              <Layers className="h-10 w-10 text-slate-300" />
              Select a stage to see detailed activity, compliance controls, and next actions.
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Right Drawer for AI Upload */}
      <RightDrawer
        isOpen={showAIUploadDrawer}
        onClose={() => setShowAIUploadDrawer(false)}
        title="AI Upload / Bulk Upload"
        size="xl"
      >
        <ISFAIUploadDrawer
          isOpen={showAIUploadDrawer}
          onClose={() => setShowAIUploadDrawer(false)}
          onUploadComplete={() => {
            // Refresh if needed
            setShowAIUploadDrawer(false);
          }}
          selectedStudy={document?.study || document?.studyId || null}
        />
      </RightDrawer>

      {/* Rejection Dialog */}
      <RejectionDialog
        open={showRejectionDialog}
        onOpenChange={setShowRejectionDialog}
        currentStage={rejectionStage}
        documentTitle={document?.title}
        onReject={handleRejectDocument}
        isLoading={rejectionMutation.isPending}
      />

    </div>
  );
};

export default ISFDocumentWorkflow;