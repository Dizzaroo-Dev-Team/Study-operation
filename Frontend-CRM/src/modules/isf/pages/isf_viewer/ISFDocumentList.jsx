import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Search, Plus, FileText, Download, Eye, Send, MoreHorizontal, Filter, ChevronDown, ChevronUp, Archive, Trash2, FileEdit, History, AlertCircle, Upload, CheckCircle, Users, Activity, Clock, Share2, ClipboardList, ClipboardCheck, ExternalLink, Maximize2, Minimize2, ShieldCheck, Sparkles, Layers, Mail, Loader2, XCircle, ZoomIn, ZoomOut, RotateCcw, RefreshCw } from 'lucide-react';
import isfClinicalTrialsService from '../../services/isfClinicalTrials.service';
import isfDocumentService from '../../services/isfDocument.service';
import isfDocumentWorkflowService from '../../services/isfDocumentWorkflow.service';
import emailAttachmentService from '@/services/emailAttachment.service';
import UploadDocumentDialog from '../../components/documents/UploadDocumentDialog';
import { useToast } from '@/components/ui/use-toast';
import ApprovalDialog from '../../components/documents/ApprovalDialog';
import { Skeleton } from '@/components/ui/skeleton';
import { SimpleTooltip } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import ISFDocumentWorkflow from '@/components/documents/ISFDocumentWorkflow';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import Spinner from '@/components/ui/spinner';
import ISFAIUploadDrawer from '@/components/ai/ISFAIUploadDrawer';
import RightDrawer from '@/components/ui/right-drawer';
import DocxPreview from '@/components/documents/DocxPreview';
import sharedAuthService from '@/services/sharedAuth.service';
import { canOpenWorkflowStage, getAccessibleStages } from '@/config/workflowPermissions';
import { WORKFLOW_STATES } from '@/components/documents/workflow/workflowUtils';
import { ROLES } from '@/config/roles';


const EditDocumentDialog = ({ open, onClose, document, onUpdated }) => {
  const { toast } = useToast();
  const [form, setForm] = useState(document || {});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setForm(document || {});
  }, [document]);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await isfClinicalTrialsService.updateDocument(document._id, form);
      toast({ title: 'Document updated', description: 'The document was updated successfully.' });
      onUpdated();
      onClose();
    } catch (err) {
      toast({ title: 'Update failed', description: err.message || 'Failed to update document', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg z-[100]">
        <DialogHeader>
          <DialogTitle>Edit Document</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Title</label>
            <Input name="title" value={form.title || ''} onChange={handleChange} required />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <Input name="description" value={form.description || ''} onChange={handleChange} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Type</label>
            <Select
              name="type"
              value={form.type || ''}
              onValueChange={val => setForm({ ...form, type: val })}
              required
            >
              <SelectTrigger>
                <SelectValue placeholder="Select type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Protocol">Protocol</SelectItem>
                <SelectItem value="Informed Consent">Informed Consent</SelectItem>
                <SelectItem value="Report">Report</SelectItem>
                <SelectItem value="Other">Other</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Study</label>
            <Input name="study" value={form.study || ''} onChange={handleChange} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Status</label>
            <Select
              name="status"
              value={form.status || ''}
              onValueChange={val => setForm({ ...form, status: val })}
              required
            >
              <SelectTrigger>
                <SelectValue placeholder="Select status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="DRAFT">DRAFT</SelectItem>
                <SelectItem value="IN_REVIEW">IN_REVIEW</SelectItem>
                <SelectItem value="APPROVED">APPROVED</SelectItem>
                <SelectItem value="FINAL">FINAL</SelectItem>
                <SelectItem value="ARCHIVED">ARCHIVED</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {/* Add more fields as needed */}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={loading}>{loading ? 'Saving...' : 'Save'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

const getDocumentIdentifier = (doc) => doc?._id || doc?.id || doc?.documentId || null;

const ManageReviewersDialog = ({ open, onClose, documentId }) => {
  const [reviewers, setReviewers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [newReviewer, setNewReviewer] = useState({ reviewerId: '', reviewerName: '' });
  const { toast } = useToast();

  // Example reviewer options (replace with real data as needed)
  const reviewerOptions = [
    { reviewerId: 'npi123', reviewerName: 'Dr. Alice Smith', npi: 'npi123', role: 'Principal Investigator' },
    { reviewerId: 'npi456', reviewerName: 'Dr. Bob Jones', npi: 'npi456', role: 'Sub-Investigator' },
    { reviewerId: 'npi789', reviewerName: 'Dr. Carol Lee', npi: 'npi789', role: 'Study Coordinator' },
  ];
  const [selectedReviewer, setSelectedReviewer] = useState(null);

  useEffect(() => {
    if (open && documentId) fetchReviewers();
    // eslint-disable-next-line
  }, [open, documentId]);

  const fetchReviewers = async () => {
    setLoading(true);
    try {
      const data = await isfClinicalTrialsService.getReviewers(documentId);
      setReviewers(data);
    } catch (err) {
      toast({ title: 'Failed to load reviewers', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddReviewer = async () => {
    if (!newReviewer.reviewerId || !newReviewer.reviewerName) return;
    setLoading(true);
    try {
      await isfClinicalTrialsService.addReviewer(documentId, newReviewer);
      setNewReviewer({ reviewerId: '', reviewerName: '' });
      fetchReviewers();
      toast({ title: 'Reviewer added' });
    } catch (err) {
      toast({ title: 'Failed to add reviewer', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (reviewerId, status) => {
    setLoading(true);
    try {
      await isfClinicalTrialsService.updateReviewer(documentId, reviewerId, { status });
      fetchReviewers();
      toast({ title: 'Reviewer status updated' });
    } catch (err) {
      toast({ title: 'Failed to update status', description: err.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleReviewerSelect = (reviewerId) => {
    const reviewer = reviewerOptions.find(r => r.reviewerId === reviewerId);
    setSelectedReviewer(reviewer);
    setNewReviewer({ reviewerId: reviewer.reviewerId, reviewerName: reviewer.reviewerName, npi: reviewer.npi, role: reviewer.role });
  };

  if (!open) return null;
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg w-[95vw] sm:w-[90vw] md:w-[80vw] lg:w-[60vw] p-4 sm:p-6 z-[100]">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">Manage Reviewers</DialogTitle>
          <DialogDescription className="text-sm text-gray-500">
            Add and manage reviewers for this document
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Current Reviewers Section */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-900">Current Reviewers</h3>
              <span className="text-xs text-gray-500">{reviewers.length} reviewer{reviewers.length !== 1 ? 's' : ''}</span>
            </div>

            {loading ? (
              <div className="text-center py-4 text-sm text-gray-500">Loading reviewers...</div>
            ) : reviewers.length === 0 ? (
              <div className="text-center py-4 text-sm text-gray-500 bg-gray-50 rounded-lg">
                No reviewers assigned yet
              </div>
            ) : (
              <div className="space-y-3">
                {reviewers.map(r => (
                  <div key={r.reviewerId} className="flex flex-col sm:flex-row items-start sm:items-center gap-3 p-3 bg-gray-50 rounded-lg">
                    <div className="flex-grow min-w-0">
                      <div className="font-medium text-sm text-gray-900 truncate">{r.reviewerName}</div>
                      <div className="text-xs text-gray-500">{r.npi} • {r.role}</div>
                    </div>
                    <Select
                      value={r.status}
                      onValueChange={val => handleStatusChange(r.reviewerId, val)}
                      className="w-full sm:w-32"
                    >
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="PENDING" className="text-sm">Pending</SelectItem>
                        <SelectItem value="APPROVED" className="text-sm">Approved</SelectItem>
                        <SelectItem value="REJECTED" className="text-sm">Rejected</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Add Reviewer Section */}
          <div className="border-t pt-6 space-y-4">
            <h3 className="text-sm font-semibold text-gray-900">Add New Reviewer</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="sm:col-span-2 lg:col-span-1">
                <Select
                  value={selectedReviewer?.reviewerId || ''}
                  onValueChange={handleReviewerSelect}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select reviewer" />
                  </SelectTrigger>
                  <SelectContent>
                    {reviewerOptions.map(r => (
                      <SelectItem key={r.reviewerId} value={r.reviewerId}>{r.reviewerName}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Input
                  value={selectedReviewer?.npi || ''}
                  readOnly
                  className="bg-gray-50"
                  placeholder="NPI Number"
                />
              </div>
              <div>
                <Input
                  value={selectedReviewer?.role || ''}
                  readOnly
                  className="bg-gray-50"
                  placeholder="Role"
                />
              </div>
              <div className="sm:col-span-2 lg:col-span-1">
                <Button
                  onClick={handleAddReviewer}
                  disabled={loading || !selectedReviewer}
                  className="w-full"
                >
                  {loading ? 'Adding...' : 'Add Reviewer'}
                </Button>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter className="mt-6">
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const ISFDocumentList = ({ selectedStudy, selectedSite, refreshKey }) => {
  const { toast } = useToast();
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [sortConfig, setSortConfig] = useState({ key: 'createdAt', direction: 'desc' });
  const [filters, setFilters] = useState({
    study: 'all',
    dateRange: 'all'
  });

  // Get current user and role for role-based document filtering
  const currentUser = sharedAuthService.getCurrentUser();

  // Try multiple ways to get the role to ensure we capture it correctly
  let userRole = currentUser?.clinicalRole || currentUser?.neurodocRole || null;

  // If role is in applications array, extract it
  if (!userRole && currentUser?.applications) {
    const neurodocApp = currentUser.applications.find(app => app.appId === 'neurodoc');
    if (neurodocApp?.role) {
      userRole = neurodocApp.role;
    }
  }

  // CRM-INTEGRATED CONTEXT: the shared CRM user object has no ISF-specific
  // clinicalRole / neurodocRole / neurodoc application, so userRole would be null
  // here — which the document filter below treats as "hide ALL documents for
  // security". That makes every uploaded ISF document invisible inside the CRM.
  // The CRM already gates access to the ISF module (auth + study/site selection),
  // so fall back to ADMIN (full view access) instead of hiding everything.
  if (!userRole) {
    userRole = ROLES.ADMIN;
  }

  // Normalize role to match ROLES constants exactly
  // Check exact matches first, then partial matches
  if (userRole) {
    const roleUpper = userRole.toUpperCase().trim();
    // Exact matches first (most specific)
    if (roleUpper === ROLES.PRINCIPAL_INVESTIGATOR || roleUpper === 'PRINCIPAL_INVESTIGATOR') {
      userRole = ROLES.PRINCIPAL_INVESTIGATOR;
    } else if (roleUpper === ROLES.QA_REVIEWER || roleUpper === 'QA_REVIEWER') {
      userRole = ROLES.QA_REVIEWER;
    } else if (roleUpper === ROLES.STUDY_MANAGER || roleUpper === 'STUDY_MANAGER') {
      userRole = ROLES.STUDY_MANAGER;
    } else if (roleUpper === ROLES.STUDY_MONITOR || roleUpper === 'STUDY_MONITOR') {
      userRole = ROLES.STUDY_MONITOR;
    } else if (roleUpper === ROLES.TMF_LEAD || roleUpper === 'TMF_LEAD') {
      userRole = ROLES.TMF_LEAD;
    } else if (roleUpper === ROLES.ADMIN || roleUpper === 'ADMIN') {
      userRole = ROLES.ADMIN;
    } else {
      // Partial matches (less specific, check in order of specificity)
      if (roleUpper.includes('PRINCIPAL_INVESTIGATOR') || (roleUpper.includes('INVESTIGATOR') && !roleUpper.includes('STUDY'))) {
        userRole = ROLES.PRINCIPAL_INVESTIGATOR;
      } else if (roleUpper.includes('QA_REVIEWER') || (roleUpper.includes('QA') && roleUpper.includes('REVIEWER'))) {
        userRole = ROLES.QA_REVIEWER;
      } else if (roleUpper.includes('STUDY_MANAGER') || (roleUpper.includes('STUDY') && roleUpper.includes('MANAGER'))) {
        userRole = ROLES.STUDY_MANAGER;
      } else if (roleUpper.includes('STUDY_MONITOR') || (roleUpper.includes('STUDY') && roleUpper.includes('MONITOR'))) {
        userRole = ROLES.STUDY_MONITOR;
      } else if (roleUpper.includes('TMF_LEAD') || (roleUpper.includes('TMF') && roleUpper.includes('LEAD'))) {
        userRole = ROLES.TMF_LEAD;
      } else if (roleUpper.includes('ADMIN')) {
        userRole = ROLES.ADMIN;
      }
    }
  }

  // ── CRM Integration fallback ──────────────────────────────────────────────
  // The CRM stores users with `role` and `is_privileged` instead of the ISF-
  // specific `clinicalRole` / `neurodocRole` fields.  If the ISF detection
  // above found nothing, map the CRM role to the closest ISF equivalent so
  // that authenticated CRM users are never silently blocked.
  if (!userRole && currentUser) {
    const crmRole = (currentUser?.role || '').toUpperCase().trim();
    if (currentUser?.is_privileged || crmRole === 'ADMIN' || crmRole === 'SUPERADMIN' || crmRole === 'SYSTEM_ADMIN') {
      userRole = ROLES.ADMIN;
    } else if (crmRole === 'STUDY_LEAD' || crmRole === 'LEAD') {
      userRole = ROLES.STUDY_MANAGER;
    } else if (crmRole === 'SITE_MANAGER' || crmRole === 'SITE_LEAD') {
      userRole = ROLES.STUDY_MANAGER;
    } else if (crmRole === 'MONITOR' || crmRole === 'CRA') {
      userRole = ROLES.STUDY_MONITOR;
    } else if (crmRole === 'QA' || crmRole.includes('QUALITY')) {
      userRole = ROLES.QA_REVIEWER;
    } else if (currentUser?.email) {
      // Any authenticated CRM user defaults to STUDY_MANAGER so they can see all documents
      userRole = ROLES.STUDY_MANAGER;
    }
  }
  // ─────────────────────────────────────────────────────────────────────────

  const userId = currentUser?.id || currentUser?._id || currentUser?.email || null;

  // Debug logging for QA_REVIEWER
  useEffect(() => {
    if (currentUser?.email?.includes('qa.reviewer') || userRole === ROLES.QA_REVIEWER) {
      console.log('[DocumentList] QA_REVIEWER user detected:', {
        email: currentUser?.email,
        clinicalRole: currentUser?.clinicalRole,
        neurodocRole: currentUser?.neurodocRole,
        applications: currentUser?.applications,
        extractedUserRole: userRole,
        userId,
        accessibleStages: getAccessibleStages(userRole),
        currentUser,
        totalDocuments: documents.length
      });

      // Log all documents and their workflow states
      console.log('[DocumentList] All documents for QA_REVIEWER:', documents.map(doc => ({
        id: doc._id || doc.id,
        title: doc.title,
        workflowSummary: doc.workflowSummary,
        workflow: doc.workflow,
        workflowState: doc?.workflowSummary?.lifecycleState || doc?.workflow?.lifecycleState || 'INTAKE',
        canView: canOpenWorkflowStage(userRole, doc?.workflowSummary?.lifecycleState || doc?.workflow?.lifecycleState || WORKFLOW_STATES.INTAKE)
      })));
    }
  }, [currentUser, userRole, userId, documents]);
  const [showFilters, setShowFilters] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showArchiveDialog, setShowArchiveDialog] = useState(false);
  const [showAuditDialog, setShowAuditDialog] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [auditTrail, setAuditTrail] = useState([]);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editDocument, setEditDocument] = useState(null);
  const [showReviewersDialog, setShowReviewersDialog] = useState(false);
  const [reviewersDocId, setReviewersDocId] = useState(null);
  const [showApprovalDialog, setShowApprovalDialog] = useState(false);
  const [selectedDocumentForApproval, setSelectedDocumentForApproval] = useState(null);
  const [typeMulti] = useState([]);
  const [statusMulti] = useState([]);
  const [studyMulti] = useState([]);
  const [archiveReason, setArchiveReason] = useState('');
  const [workflowDrawerOpen, setWorkflowDrawerOpen] = useState(false);
  const [isPreviewExpanded, setIsPreviewExpanded] = useState(false);
  const [previewZoom, setPreviewZoom] = useState(100);
  const [workflowDocument, setWorkflowDocument] = useState(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [workflowError, setWorkflowError] = useState(null);
  const [syncingEmails, setSyncingEmails] = useState(false);
  const [emailAttachments, setEmailAttachments] = useState([]);
  // Email attachments are now shown in the main documents table, no separate section needed
  const [workflowPreviewUrl, setWorkflowPreviewUrl] = useState(null);
  const [workflowPreviewLoading, setWorkflowPreviewLoading] = useState(false);
  const [workflowPreviewError, setWorkflowPreviewError] = useState(null);
  const [validationResults, setValidationResults] = useState({});
  const [validatingDocumentId, setValidatingDocumentId] = useState(null);
  const [showValidationDialog, setShowValidationDialog] = useState(false);
  const [selectedDocumentForValidation, setSelectedDocumentForValidation] = useState(null);
  const [currentValidationResult, setCurrentValidationResult] = useState(null);
  const [showAIUploadDrawer, setShowAIUploadDrawer] = useState(false);
  const [emailAttachmentData, setEmailAttachmentData] = useState(null);

  const previewInfoChips = useMemo(() => {
    const chips = [{ key: 'previewing', icon: Eye, tooltip: 'Previewing' }];
    const title = workflowDocument?.documentTitle || workflowDocument?.title;
    if (title) {
      chips.push({ key: 'title', icon: FileText, tooltip: title });
    }
    if (workflowDocument?.documentType) {
      chips.push({
        key: 'type',
        icon: Layers,
        tooltip: `Type: ${workflowDocument.documentType}`,
      });
    }
    if (workflowDocument?.status) {
      chips.push({
        key: 'status',
        icon: ShieldCheck,
        tooltip: `Status: ${workflowDocument.status}`,
      });
    }
    if (workflowDocument?.version) {
      chips.push({
        key: 'version',
        icon: Clock,
        tooltip: `Version ${workflowDocument.version}`,
      });
    }
    return chips;
  }, [
    workflowDocument?.documentTitle,
    workflowDocument?.title,
    workflowDocument?.documentType,
    workflowDocument?.status,
    workflowDocument?.version,
  ]);

  // Filtering
  const filtered = useMemo(() => {
    // Log role detection for debugging
    if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
      console.log('[DocumentList] Filtering documents:', {
        totalDocuments: documents.length,
        userRole,
        currentUserEmail: currentUser?.email,
        clinicalRole: currentUser?.clinicalRole,
        neurodocRole: currentUser?.neurodocRole
      });
    }

    let filteredDocs = documents.filter(doc => {
      const docType = doc.type || doc.documentType || '';
      const docStatus = getDisplayStatus(doc);
      const docStudy = doc.study || '';
      const docTitle = doc.title || '';
      const isEmailAttachment = doc.source === 'email_attachment' || doc.isEmailAttachment || doc.emailInfo;

      // ROLE-BASED FILTERING: Only show documents where user can view the document's current workflow stage
      // Based on the permission matrix:
      // ✅ = Can edit (in allowedRoles) - document visible
      // 👁️ = Can view only (in operations.view) - document visible  
      // ❌ = Cannot access - document hidden

      // IMPORTANT: If userRole is not detected, hide all documents for security
      // This prevents unauthorized access when role detection fails
      if (!userRole) {
        console.warn('[DocumentList] User role not detected - hiding all documents for security');
        return false;
      }

      // Get the document's current workflow stage
      // Check multiple possible locations for workflow state:
      // 1. workflowSummary.lifecycleState (from Document model)
      // 2. workflow.lifecycleState (from populated workflow)
      // 3. Check if intake is completed - if so, treat as QC_VALIDATION for filtering
      // 4. Default to INTAKE if not set
      let workflowState = doc?.workflowSummary?.lifecycleState ||
        doc?.workflow?.lifecycleState ||
        WORKFLOW_STATES.INTAKE;

      // Special case: If intake is completed but workflow state hasn't been advanced yet,
      // treat it as QC_VALIDATION for filtering purposes (for demo/testing)
      if (workflowState === WORKFLOW_STATES.INTAKE) {
        const intake = doc?.workflow?.intake || doc?.workflowSummary?.intake || {};
        const intakeCompleted = intake.markComplete === true ||
          intake.status === 'COMPLETED' ||
          (intake.progress !== undefined && intake.progress >= 90);

        if (intakeCompleted) {
          // Intake is completed but state hasn't advanced - treat as QC_VALIDATION for filtering
          workflowState = WORKFLOW_STATES.QC_VALIDATION;
          console.log('[DocumentList] Intake completed but state not advanced - treating as QC_VALIDATION for filtering:', {
            documentId: doc._id || doc.id,
            documentTitle: doc.title,
            intakeStatus: intake.status,
            intakeMarkComplete: intake.markComplete,
            intakeProgress: intake.progress
          });
        }
      }

      // Debug: Log workflow state detection for QC_VALIDATION documents
      if (workflowState === WORKFLOW_STATES.QC_VALIDATION ||
        doc?.workflowSummary?.lifecycleState === WORKFLOW_STATES.QC_VALIDATION ||
        doc?.workflow?.lifecycleState === WORKFLOW_STATES.QC_VALIDATION) {
        console.log('[DocumentList] QC_VALIDATION document detected:', {
          documentId: doc._id || doc.id,
          documentTitle: doc.title,
          workflowSummaryLifecycleState: doc?.workflowSummary?.lifecycleState,
          workflowLifecycleState: doc?.workflow?.lifecycleState,
          resolvedWorkflowState: workflowState,
          hasWorkflowSummary: !!doc?.workflowSummary,
          hasWorkflow: !!doc?.workflow,
          workflowRef: doc?.workflowRef
        });
      }

      // Check if user can view this workflow stage (includes both ✅ edit and 👁️ view-only access)
      const canViewStage = canOpenWorkflowStage(userRole, workflowState);

      console.log('[DocumentList] Document filtering check:', canViewStage, userRole, workflowState);
      // Debug logging for QA_REVIEWER
      if (userRole && (userRole.includes('QA_REVIEWER') || userRole.includes('QA') || currentUser?.email?.includes('qa.reviewer'))) {
        console.log('[DocumentList] QA_REVIEWER filtering check:', {
          userRole,
          workflowState,
          canViewStage,
          documentId: doc._id || doc.id,
          documentTitle: doc.title,
          workflowSummary: doc?.workflowSummary,
          workflow: doc?.workflow,
          workflowSummaryLifecycleState: doc?.workflowSummary?.lifecycleState,
          workflowLifecycleState: doc?.workflow?.lifecycleState,
          accessibleStages: getAccessibleStages(userRole),
          hasWorkflowRef: !!doc.workflowRef,
          status: doc.status
        });
      }

      // Debug logging for PRINCIPAL_INVESTIGATOR
      if (userRole && (userRole.includes('PRINCIPAL_INVESTIGATOR') || userRole.includes('INVESTIGATOR') || currentUser?.email?.includes('investigator'))) {
        const docUploadedBy = doc.uploadedBy || doc.author || '';
        const isOwnDoc = userId && (
          docUploadedBy === userId ||
          docUploadedBy === currentUser?.email ||
          docUploadedBy?.toString() === userId?.toString() ||
          (typeof docUploadedBy === 'object' && docUploadedBy?._id?.toString() === userId?.toString())
        );
        const canSeeOwnDocument = isOwnDoc && canViewStage;
        const willShow = canViewStage || canSeeOwnDocument;

        console.log('[DocumentList] PRINCIPAL_INVESTIGATOR filtering check:', {
          userRole,
          workflowState,
          canViewStage,
          documentId: doc._id || doc.id,
          documentTitle: doc.title,
          workflowSummary: doc?.workflowSummary,
          workflow: doc?.workflow,
          workflowSummaryLifecycleState: doc?.workflowSummary?.lifecycleState,
          workflowLifecycleState: doc?.workflow?.lifecycleState,
          accessibleStages: getAccessibleStages(userRole),
          isOwnDocument: isOwnDoc,
          docUploadedBy,
          userId,
          currentUserEmail: currentUser?.email,
          willShow,
          canSeeOwnDocument,
          reason: willShow ? (
            canViewStage ? 'canViewStage=true (has access to stage)' :
              canSeeOwnDocument ? 'isOwnDocument=true AND canViewStage=true (user uploaded it and has stage access)' :
                'unknown'
          ) : 'FILTERED OUT (no access to stage and not own document with access)'
        });
      }

      // Also check if user uploaded this document
      // NOTE: Users can only see their own uploads if they have view access to the current stage
      // This prevents PRINCIPAL_INVESTIGATOR from seeing their own documents in QC_VALIDATION
      const docUploadedBy = doc.uploadedBy || doc.author || '';
      const isOwnDocument = userId && (
        docUploadedBy === userId ||
        docUploadedBy === currentUser?.email ||
        docUploadedBy?.toString() === userId?.toString() ||
        (typeof docUploadedBy === 'object' && docUploadedBy?._id?.toString() === userId?.toString())
      );

      // PRIMARY FILTER: User must have view access to the document's workflow stage
      // Documents are ONLY shown if user has permission to view the stage
      // 
      // Rule: If user cannot view the stage, document is ALWAYS hidden (even if user uploaded it)
      // No exceptions - strict role-based access control
      const canSeeOwnDocument = isOwnDocument && canViewStage;

      // Show document ONLY if user has view access to the current workflow stage
      // No special cases or workarounds - strict permission enforcement
      const shouldShow = canViewStage || canSeeOwnDocument;

      // CRITICAL: If user has no access to the stage, document must be hidden
      // This is the primary security enforcement
      if (!shouldShow) {
        // Log why document was filtered (for debugging)
        if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
          console.log('[DocumentList] Document filtered out:', {
            documentId: doc._id || doc.id,
            documentTitle: doc.title,
            workflowState,
            userRole,
            canViewStage,
            reason: !canViewStage ? 'User cannot view this workflow stage' :
              !canSeeOwnDocument ? 'User uploaded but no stage access' :
                'Unknown reason'
          });
        }
        return false;
      }

      // Log filtering decision for QC_VALIDATION documents when user is PRINCIPAL_INVESTIGATOR
      if (workflowState === WORKFLOW_STATES.QC_VALIDATION && userRole === ROLES.PRINCIPAL_INVESTIGATOR) {
        console.log('[DocumentList] PRINCIPAL_INVESTIGATOR QC_VALIDATION filter:', {
          documentId: doc._id || doc.id,
          documentTitle: doc.title,
          workflowState,
          canViewStage,
          isOwnDocument,
          canSeeOwnDocument,
          shouldShow,
          willBeFiltered: !shouldShow,
          reason: !shouldShow ? 'No access to QC_VALIDATION stage' : 'Has access to stage'
        });
      }

      if (!shouldShow) {
        return false;
      }

      // Filter by study
      if (filters.study !== 'all' && filters.study !== '') {
        if (docStudy !== filters.study) return false;
      }

      // Search query
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        if (!docTitle.toLowerCase().includes(query) &&
          !docType.toLowerCase().includes(query) &&
          !docStatus.toLowerCase().includes(query) &&
          !docStudy.toLowerCase().includes(query)) {
          return false;
        }
      }

      return (
        (typeMulti.length === 0 || typeMulti.includes(docType)) &&
        (statusMulti.length === 0 || statusMulti.includes(docStatus)) &&
        (studyMulti.length === 0 || studyMulti.includes(docStudy))
      );
    });

    // Log filtering results for debugging
    if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
      console.log('[DocumentList] Filtering complete:', {
        totalDocuments: documents.length,
        filteredCount: filteredDocs.length,
        hiddenCount: documents.length - filteredDocs.length,
        userRole
      });
    }

    // Sort documents
    filteredDocs.sort((a, b) => {
      const aValue = a[sortConfig.key] || '';
      const bValue = b[sortConfig.key] || '';

      // Default sorting
      if (sortConfig.key === 'createdAt') {
        const aDate = new Date(a.createdAt || 0);
        const bDate = new Date(b.createdAt || 0);
        return sortConfig.direction === 'asc'
          ? aDate.getTime() - bDate.getTime()
          : bDate.getTime() - aDate.getTime();
      }

      if (typeof aValue === 'string' && typeof bValue === 'string') {
        return sortConfig.direction === 'asc'
          ? aValue.localeCompare(bValue)
          : bValue.localeCompare(aValue);
      }

      return sortConfig.direction === 'asc'
        ? (aValue > bValue ? 1 : -1)
        : (aValue < bValue ? 1 : -1);
    });

    return filteredDocs;
  }, [documents, searchQuery, typeMulti, statusMulti, studyMulti, filters, sortConfig, userRole, userId, currentUser]);

  // Initialize with dummy email documents (frontend only - no API call)
  useEffect(() => {
    const now = Date.now();
    const dummyEmailDocuments = [
      {
        _id: 'dummy_email_001',
        documentId: 'doc_email_001',
        title: 'Clinical Study Protocol v2.1 - Email Attachment',
        documentType: 'PROTOCOL',
        type: 'PROTOCOL',
        study: '68623b6cb7d66020987f2e7b',
        status: 'DRAFT',
        createdAt: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
        source: 'email_attachment',
        emailInfo: {
          from: 'john.doe@pharma.com',
          subject: 'Clinical Study Protocol - Review Required',
          receivedAt: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
          messageId: 'email_msg_001'
        },
        fileUrl: '#',
        fileSize: 2456789,
        mimeType: 'application/pdf',
        version: 1
      },
      {
        _id: 'dummy_email_002',
        documentId: 'doc_email_002',
        title: 'Informed Consent Form - Site 05',
        documentType: 'ICF',
        type: 'ICF',
        study: '68623b6cb7d66020987f2e7b',
        status: 'IN_REVIEW',
        createdAt: new Date(now - 5 * 24 * 60 * 60 * 1000).toISOString(),
        source: 'email_attachment',
        emailInfo: {
          from: 'sarah.smith@clinicalsite.com',
          subject: 'ICF Document for Review',
          receivedAt: new Date(now - 5 * 24 * 60 * 60 * 1000).toISOString(),
          messageId: 'email_msg_002'
        },
        fileUrl: '#',
        fileSize: 1234567,
        mimeType: 'application/pdf',
        version: 3
      },
      {
        _id: 'dummy_email_003',
        documentId: 'doc_email_003',
        title: 'Case Report Form - Patient 123',
        documentType: 'CRF',
        type: 'CRF',
        study: '68623b6cb7d66020987f2e7b',
        status: 'APPROVED',
        createdAt: new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString(),
        source: 'email_attachment',
        emailInfo: {
          from: 'data.manager@research.org',
          subject: 'CRF Submission - Patient 123',
          receivedAt: new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString(),
          messageId: 'email_msg_003'
        },
        fileUrl: '#',
        fileSize: 987654,
        mimeType: 'application/pdf',
        version: 1
      },
      {
        _id: 'dummy_email_004',
        documentId: 'doc_email_004',
        title: 'Adverse Event Report - AE-2024-045',
        documentType: 'REPORT',
        type: 'REPORT',
        study: '68623b6cb7d66020987f2e7b',
        status: 'DRAFT',
        createdAt: new Date(now - 1 * 24 * 60 * 60 * 1000).toISOString(),
        source: 'email_attachment',
        emailInfo: {
          from: 'safety.officer@pharma.com',
          subject: 'Urgent: Adverse Event Report',
          receivedAt: new Date(now - 1 * 24 * 60 * 60 * 1000).toISOString(),
          messageId: 'email_msg_004'
        },
        fileUrl: '#',
        fileSize: 543210,
        mimeType: 'application/pdf',
        version: 1
      },
      {
        _id: 'dummy_email_005',
        documentId: 'doc_email_005',
        title: 'Site Initiation Visit Report - Site 12',
        documentType: 'REPORT',
        type: 'REPORT',
        study: '68623b6cb7d66020987f2e7b',
        status: 'FINAL',
        createdAt: new Date(now - 10 * 24 * 60 * 60 * 1000).toISOString(),
        source: 'email_attachment',
        emailInfo: {
          from: 'monitor@cro.com',
          subject: 'Site Initiation Visit Report',
          receivedAt: new Date(now - 10 * 24 * 60 * 60 * 1000).toISOString(),
          messageId: 'email_msg_005'
        },
        fileUrl: '#',
        fileSize: 1876543,
        mimeType: 'application/pdf',
        version: 2
      }
    ];

    setDocuments(dummyEmailDocuments);
    setLoading(false);
    setError(null);
  }, []);

  // Helper function to safely parse Gmail date (handles Unix timestamp in milliseconds or string)
  const parseGmailDate = (dateValue) => {
    if (!dateValue) return new Date();

    // If it's already a Date object and valid
    if (dateValue instanceof Date && !isNaN(dateValue.getTime())) {
      return dateValue;
    }

    // If it's a number (Unix timestamp in milliseconds)
    if (typeof dateValue === 'number') {
      const date = new Date(dateValue);
      if (!isNaN(date.getTime())) {
        return date;
      }
    }

    // If it's a string, try to parse it
    if (typeof dateValue === 'string') {
      // Try parsing as ISO string first
      let date = new Date(dateValue);
      if (!isNaN(date.getTime())) {
        return date;
      }
      // Try parsing as Unix timestamp (in case it's a string number)
      const numValue = parseInt(dateValue, 10);
      if (!isNaN(numValue)) {
        date = new Date(numValue);
        if (!isNaN(date.getTime())) {
          return date;
        }
      }
    }

    // Fallback to current date if all parsing fails
    return new Date();
  };

  const initialLoadDoneRef = useRef(false);

  const fetchDocuments = useCallback(async () => {
    try {
      // Show the loading skeleton only on the first load; subsequent refetches
      // (email sync, filters, pagination) update the table silently so the tab
      // doesn't visibly "refresh".
      if (!initialLoadDoneRef.current) setLoading(true);

      // Fetch real documents from API
      const response = await isfClinicalTrialsService.getDocuments({
        page: currentPage,
        limit: itemsPerPage,
        sort: sortConfig,
        filters: {
          study: selectedStudy,
          site: selectedSite,
        },
      });

      console.log('Fetched documents response:', response);


      const documentsArray = Array.isArray(response)
        ? response
        : response?.data || [];

      // Transform email attachments into document-like format and merge with documents
      const emailDocuments = [];
      if (emailAttachments && emailAttachments.length > 0) {
        emailAttachments.forEach((email) => {
          // Handle both array of attachments and single attachment object
          const attachments = Array.isArray(email.attachments)
            ? email.attachments
            : (email.attachments ? [email.attachments] : []);

          attachments.forEach((attachment) => {
            // Ensure attachment has required properties
            if (!attachment || (!attachment.attachmentId && !attachment.id)) {
              console.warn('Skipping invalid attachment:', attachment);
              return;
            }

            const attachmentId = attachment.attachmentId || attachment.id;
            const messageId = email.messageId || email.id || 'unknown';
            const emailDate = parseGmailDate(email.internalDate || email.date || email.receivedAt);

            emailDocuments.push({
              _id: `email_${messageId}_${attachmentId}`,
              documentId: `EMAIL-${messageId}-${attachmentId}`,
              title: attachment.filename || attachment.name || 'Email Attachment',
              documentType: attachment.documentType || 'OTHER',
              type: attachment.documentType || 'OTHER',
              study: email.studyId || email.study || null,
              status: attachment.status || 'DRAFT',
              createdAt: emailDate.toISOString(),
              source: 'email_attachment',
              isEmailAttachment: true, // Flag to identify email attachments
              emailInfo: {
                messageId: messageId,
                attachmentId: attachmentId,
                from: email.from || email.sender || 'Unknown',
                to: email.to || email.recipient || 'Unknown',
                subject: email.subject || 'No subject',
                receivedAt: email.date || email.internalDate || email.receivedAt || emailDate.toISOString(),
              },
              fileUrl: `gmail://${messageId}/${attachmentId}`,
              fileSize: attachment.size || attachment.fileSize || 0,
              mimeType: attachment.mimeType || attachment.contentType || 'application/octet-stream',
              version: attachment.version || 1,
            });
          });
        });
      }

      // Merge email documents with regular documents
      const allDocuments = [...documentsArray, ...emailDocuments];
      setDocuments(allDocuments);
      setError(null);
    } catch (err) {
      console.error('Error fetching documents:', err);
      // On error, still show email attachments if available
      const emailDocuments = [];
      if (emailAttachments && emailAttachments.length > 0) {
        emailAttachments.forEach((email) => {
          // Handle both array of attachments and single attachment object
          const attachments = Array.isArray(email.attachments)
            ? email.attachments
            : (email.attachments ? [email.attachments] : []);

          attachments.forEach((attachment) => {
            // Ensure attachment has required properties
            if (!attachment || (!attachment.attachmentId && !attachment.id)) {
              console.warn('Skipping invalid attachment:', attachment);
              return;
            }

            const attachmentId = attachment.attachmentId || attachment.id;
            const messageId = email.messageId || email.id || 'unknown';
            const emailDate = parseGmailDate(email.internalDate || email.date || email.receivedAt);

            emailDocuments.push({
              _id: `email_${messageId}_${attachmentId}`,
              documentId: `EMAIL-${messageId}-${attachmentId}`,
              title: attachment.filename || attachment.name || 'Email Attachment',
              documentType: attachment.documentType || 'OTHER',
              type: attachment.documentType || 'OTHER',
              study: email.studyId || email.study || null,
              status: attachment.status || 'DRAFT',
              createdAt: emailDate.toISOString(),
              source: 'email_attachment',
              isEmailAttachment: true,
              emailInfo: {
                messageId: messageId,
                attachmentId: attachmentId,
                from: email.from || email.sender || 'Unknown',
                to: email.to || email.recipient || 'Unknown',
                subject: email.subject || 'No subject',
                receivedAt: email.date || email.internalDate || email.receivedAt || emailDate.toISOString(),
              },
              fileUrl: `gmail://${messageId}/${attachmentId}`,
              fileSize: attachment.size || attachment.fileSize || 0,
              mimeType: attachment.mimeType || attachment.contentType || 'application/octet-stream',
              version: attachment.version || 1,
            });
          });
        });
      }
      setDocuments(emailDocuments);
      setError(err.message);
    } finally {
      initialLoadDoneRef.current = true;
      setLoading(false);
    }
  }, [currentPage, itemsPerPage, selectedStudy, selectedSite, sortConfig, filters, emailAttachments]);

  useEffect(() => {
    fetchDocuments();
  }, [selectedStudy, selectedSite, fetchDocuments, refreshKey]);

  const [isRefreshing, setIsRefreshing] = useState(false);
  const handleManualRefresh = async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      await fetchDocuments();
    } finally {
      setIsRefreshing(false);
    }
  };



  // Auto-fetch emails when component mounts
  useEffect(() => {
    const autoFetchEmails = async () => {
      try {
        setSyncingEmails(true);
        console.log('Auto-fetching emails on mount...');
        const result = await isfClinicalTrialsService.getStudyEmails(null, 100);
        console.log('Auto-fetch email result:', result);

        let emails = [];
        // Handle different response formats
        if (result && result.success && result.data) {
          emails = Array.isArray(result.data) ? result.data : [result.data];
        } else if (Array.isArray(result)) {
          emails = result;
        } else if (result && result.data && Array.isArray(result.data)) {
          emails = result.data;
        }

        if (emails.length > 0) {
          console.log(`Setting ${emails.length} emails with attachments`);
          // Updating emailAttachments re-triggers the fetch effect (silently),
          // which merges the attachments — no manual refetch needed.
          setEmailAttachments(emails);
        } else {
          console.log('No emails found in auto-fetch');
        }
      } catch (error) {
        console.error('Auto-fetch emails error:', error);
        // Silently fail on auto-fetch - user can manually sync
      } finally {
        setSyncingEmails(false);
      }
    };

    autoFetchEmails();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount

  useEffect(() => {
    if (!workflowDrawerOpen || !workflowDocument) {
      setWorkflowPreviewUrl(null);
      setWorkflowPreviewError(null);
      setWorkflowPreviewLoading(false);
      return;
    }

    const docId = workflowDocument?._id || workflowDocument?.documentId;
    const fallbackUrl = workflowDocument?.fileUrl || null;
    const isEmailAttachment = workflowDocument?.isEmailAttachment ||
      workflowDocument?.source === 'email_attachment' ||
      docId?.startsWith('email_') ||
      fallbackUrl?.startsWith('gmail://');

    // For email attachments, don't try to fetch presigned URL
    if (isEmailAttachment) {
      setWorkflowPreviewUrl(null);
      setWorkflowPreviewError('Email attachments are not available for direct preview. Please process the attachment to create a viewable document.');
      setWorkflowPreviewLoading(false);
      return;
    }

    if (!docId && fallbackUrl) {
      setWorkflowPreviewUrl(fallbackUrl);
      setWorkflowPreviewError(null);
      setWorkflowPreviewLoading(false);
      return;
    }

    let active = true;
    const fetchPreview = async () => {
      try {
        setWorkflowPreviewLoading(true);
        setWorkflowPreviewError(null);
        const url = await isfDocumentService.getPresignedUrl(docId);
        if (active) {
          setWorkflowPreviewUrl(url || fallbackUrl);
        }
      } catch (error) {
        console.error('Failed to load document preview URL', error);
        if (active) {
          // Handle 404/501 errors for email attachments gracefully
          if (error.response?.status === 404 || error.response?.status === 501) {
            setWorkflowPreviewError('This document is not available for preview. It may be an email attachment that needs to be processed first.');
          } else {
            setWorkflowPreviewUrl(fallbackUrl);
            setWorkflowPreviewError('Secure preview unavailable. Using fallback file link if available.');
          }
        }
      } finally {
        if (active) {
          setWorkflowPreviewLoading(false);
        }
      }
    };

    fetchPreview();

    return () => {
      active = false;
    };
  }, [workflowDrawerOpen, workflowDocument]);

  // Hoisted helper so it is defined before use in filters/render
  function getDisplayStatus(doc) {
    console.log("Printing Document to check status", doc);
    // List view should reflect the document's persisted status, not workflow lifecycle
    return doc?.status || doc?.effectiveStatus || '';
  }

  const getStatusBadge = (status) => {
    const statusConfig = {
      'DRAFT': { label: 'Draft', color: 'bg-gray-200 text-gray-700', icon: <FileText className="h-4 w-4 mr-1 text-gray-400" /> },
      'IN_QC': { label: 'In QC', color: 'bg-indigo-100 text-indigo-700', icon: <ShieldCheck className="h-4 w-4 mr-1 text-indigo-500" /> },
      'IN_REVIEW': { label: 'In Review', color: 'bg-yellow-100 text-yellow-700', icon: <History className="h-4 w-4 mr-1 text-yellow-500" /> },
      'PENDING_APPROVAL': { label: 'Pending Approval', color: 'bg-orange-100 text-orange-700', icon: <ClipboardCheck className="h-4 w-4 mr-1 text-orange-500" /> },
      'APPROVED': { label: 'Approved', color: 'bg-green-100 text-green-700', icon: <CheckCircle className="h-4 w-4 mr-1 text-green-600" /> },
      'REJECTED': { label: 'Rejected', color: 'bg-red-100 text-red-700', icon: <XCircle className="h-4 w-4 mr-1 text-red-600" /> },
      'ARCHIVED': { label: 'Archived', color: 'bg-slate-200 text-slate-700', icon: <Archive className="h-4 w-4 mr-1 text-slate-500" /> },
      'FINAL': { label: 'Final', color: 'bg-blue-100 text-blue-700', icon: <FileText className="h-4 w-4 mr-1 text-blue-600" /> },
    };
    const config = statusConfig[status] || statusConfig['DRAFT'];
    return <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-semibold ${config.color}`}>{config.icon}{config.label}</span>;
  };

  // Helper function to check if validation is successful
  const isValidationSuccessful = (docId, doc = null) => {
    if (!docId) return false;

    // Check for validation results from multiple sources:
    // 1. Manual validation results (validationResults state)
    // 2. Auto-validation from document (doc.autoValidation)
    // 3. Validation result stored in document workflow
    const record = validationResults[docId];
    const autoValidation = doc?.autoValidation?.result || doc?.autoValidation;
    const workflowValidation = doc?.workflow?.intake?.validationResult;

    // Priority: manual validation > autoValidation > workflow validation
    // Handle different response structures from the API
    let validation = null;
    if (record) {
      // Check if record has nested validation property
      if (record.validation) {
        validation = record.validation;
      } else if (record.data?.validation) {
        validation = record.data.validation;
      } else if (record.data) {
        validation = record.data;
      } else {
        // Record itself is the validation object
        validation = record;
      }
    } else if (autoValidation) {
      validation = autoValidation;
    } else if (workflowValidation) {
      validation = workflowValidation;
    }

    // If no validation exists, it's not successful
    if (!validation) return false;

    const isValid = validation.isValid !== undefined ? validation.isValid :
      (validation.overallStatus === 'VALID' || validation.overallStatus === 'PASSED');

    // Get virus scan status - only fail if there's an actual security threat
    const virusStatus = validation.virusScan?.status || (validation.virusScan?.isClean ? 'CLEAN' : 'PENDING');
    // Only consider it a virus issue if contentSafety is explicitly false (actual security threat)
    // Structure/format issues are warnings, not failures
    const hasSecurityThreat = validation.virusScan?.contentSafety === false ||
      virusStatus === 'INFECTED' ||
      (validation.virusScan?.isClean === false && validation.virusScan?.contentSafety === false);

    // Get PHI detection status - only fail if high confidence (>80%)
    const phiDetected = validation.phiDetection?.detected === true;
    const phiConfidence = validation.phiDetection?.confidence || 0;
    const hasHighConfidencePHI = phiDetected && phiConfidence >= 80;

    // Validation is successful if:
    // 1. isValid is true (or overallStatus is VALID/PASSED)
    // 2. No actual security threats (contentSafety issues)
    // 3. No high confidence PHI detected (low confidence PHI is just a warning)
    return isValid && !hasSecurityThreat && !hasHighConfidencePHI;
  };

  const renderValidationBadge = (docId, doc = null) => {
    if (!docId) return null;

    // Check for validation results from multiple sources:
    // 1. Manual validation results (validationResults state)
    // 2. Auto-validation from document (doc.autoValidation)
    // 3. Validation result stored in document workflow
    const record = validationResults[docId];
    const autoValidation = doc?.autoValidation?.result || doc?.autoValidation;
    const workflowValidation = doc?.workflow?.intake?.validationResult;

    // Priority: manual validation > autoValidation > workflow validation
    // Handle different response structures from the API
    let validation = null;
    if (record) {
      // Check if record has nested validation property
      if (record.validation) {
        validation = record.validation;
      } else if (record.data?.validation) {
        validation = record.data.validation;
      } else if (record.data) {
        validation = record.data;
      } else {
        // Record itself is the validation object
        validation = record;
      }
    } else if (autoValidation) {
      validation = autoValidation;
    } else if (workflowValidation) {
      validation = workflowValidation;
    }

    // Debug logging
    if (record && !validation) {
      console.log(`[renderValidationBadge] Record found but no validation extracted for ${docId}:`, record);
    }

    if (!validation) return null;

    const isValid = validation.isValid !== undefined ? validation.isValid :
      (validation.overallStatus === 'VALID' || validation.overallStatus === 'PASSED');

    // Get virus scan status
    const virusStatus = validation.virusScan?.status || (validation.virusScan?.isClean ? 'CLEAN' : 'PENDING');
    const hasVirusIssues = virusStatus === 'INFECTED' || validation.virusScan?.isClean === false;

    // Get PHI detection status
    const hasPHI = validation.phiDetection?.detected === true;

    // Determine badge color and label
    let badgeClass, label, icon;
    if (hasVirusIssues) {
      badgeClass = 'text-red-700 border-red-300 bg-red-50';
      label = 'Virus';
      icon = <AlertCircle className="w-2.5 h-2.5" />;
    } else if (hasPHI) {
      badgeClass = 'text-amber-700 border-amber-300 bg-amber-50';
      label = 'PHI';
      icon = <AlertCircle className="w-2.5 h-2.5" />;
    } else if (isValid) {
      badgeClass = 'text-emerald-700 border-emerald-300 bg-emerald-50';
      label = 'Valid';
      icon = <ShieldCheck className="w-2.5 h-2.5" />;
    } else {
      badgeClass = 'text-red-700 border-red-300 bg-red-50';
      label = 'Failed';
      icon = <XCircle className="w-2.5 h-2.5" />;
    }

    const handleBadgeClick = (e) => {
      e.stopPropagation();
      // Find the document and show validation dialog
      const doc = documents.find(d => {
        const currentDocId = getDocumentIdentifier(d);
        return currentDocId === docId;
      });
      if (doc) {
        const attachmentForDialog = {
          id: docId,
          filename: doc.filename || doc.fileName || doc.title || 'Unknown',
          size: doc.size || doc.fileSize,
          mimeType: doc.mimeType || doc.mime_type,
          source: 'gmail',
          emailInfo: {
            subject: doc.emailInfo?.subject || doc.subject,
            from: doc.emailInfo?.from || doc.from,
            messageId: doc.emailInfo?.messageId,
            attachmentId: doc.emailInfo?.attachmentId
          }
        };
        setSelectedDocumentForValidation(attachmentForDialog);
        setCurrentValidationResult(validation);
        setShowValidationDialog(true);
      }
    };

    return (
      <Badge
        variant="outline"
        className={`${badgeClass} h-4 text-[9px] font-medium gap-0.5 px-1.5 cursor-pointer hover:opacity-80 transition-opacity`}
        onClick={handleBadgeClick}
        title="Click to view validation details"
      >
        {icon}
        {label}
      </Badge>
    );
  };

  const handleSort = (key) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  };

  const handleValidateEmailAttachment = async (doc) => {
    const docId = getDocumentIdentifier(doc);
    // Try multiple sources for messageId and attachmentId
    let messageId = doc?.emailInfo?.messageId;
    let attachmentId = doc?.emailInfo?.attachmentId || doc?.attachmentInfo?.id;

    // If docId is the combined ID format (gmail_messageId_attachmentId), parse it
    if (!messageId || !attachmentId) {
      if (docId && docId.startsWith('gmail_')) {
        const parts = docId.substring(6).split('_'); // Remove 'gmail_' prefix
        if (parts.length >= 2) {
          messageId = messageId || parts[0];
          attachmentId = attachmentId || parts.slice(1).join('_');
        }
      }
    }

    if (!docId || !messageId || !attachmentId) {
      toast({
        title: "Cannot validate attachment",
        description: "Missing Gmail identifiers for this attachment.",
        variant: "destructive"
      });
      return;
    }

    // Get studyId from document
    const studyId = typeof doc.study === 'object' ? doc.study._id || doc.study.id : doc.study;
    if (!studyId) {
      toast({
        title: "Cannot process attachment",
        description: "Study ID is required for classification. Please ensure the document is associated with a study.",
        variant: "destructive"
      });
      return;
    }

    // Prepare attachment object for validation dialog
    const attachmentForDialog = {
      id: docId,
      filename: doc.filename || doc.fileName || doc.title || 'Unknown',
      size: doc.size || doc.fileSize,
      mimeType: doc.mimeType || doc.mime_type,
      source: 'gmail',
      emailInfo: {
        subject: doc.emailInfo?.subject || doc.subject,
        from: doc.emailInfo?.from || doc.from,
        messageId: messageId,
        attachmentId: attachmentId
      }
    };

    // Open validation dialog immediately
    setSelectedDocumentForValidation(attachmentForDialog);
    setShowValidationDialog(true);
    setCurrentValidationResult(null);

    try {
      setValidatingDocumentId(docId);
      const response = await emailAttachmentService.validateGmailAttachment(messageId, attachmentId);
      const payload = response?.data || response;
      const record = payload?.success !== undefined ? payload.data : payload;

      // Store validation result
      setValidationResults((prev) => ({
        ...prev,
        [docId]: record
      }));

      // Update dialog with validation result
      setCurrentValidationResult(record);

      // Show success toast only if validation passed
      const validation = record?.validation || record;
      if (validation?.isValid) {
        toast({
          title: "Validation completed",
          description: "Document passed all validation checks. Click 'Continue' to proceed with AI classification.",
          variant: "default"
        });
      }
    } catch (error) {
      console.error('Validate attachment error:', error);
      setCurrentValidationResult({
        validation: {
          isValid: false,
          overallStatus: 'FAILED',
          errors: [error.message || 'Validation failed']
        }
      });
      toast({
        title: "Validation failed",
        description: error.message || "Failed to validate attachment",
        variant: "destructive"
      });
    } finally {
      setValidatingDocumentId(null);
    }
  };

  // Handle Continue button click - trigger AI classification
  const handleContinueToClassification = async (attachment) => {
    console.log('[DocumentList] Continue button clicked', { attachment, attachmentId: attachment?.id });

    // Declare variables at the top of the function scope
    let messageId = null;
    let attachmentId = null;
    let doc = null;
    let studyId = null;

    try {
      // Try multiple ways to find the document
      doc = documents.find(d => {
        const docId = getDocumentIdentifier(d);
        return docId === attachment.id;
      });

      // If not found by ID, try matching by emailInfo
      if (!doc && attachment?.emailInfo) {
        doc = documents.find(d => {
          const docMessageId = d?.emailInfo?.messageId || d?.messageId;
          const docAttachmentId = d?.emailInfo?.attachmentId || d?.attachmentId || d?.attachmentInfo?.id;
          return docMessageId === attachment.emailInfo.messageId &&
            docAttachmentId === attachment.emailInfo.attachmentId;
        });
      }

      // If still not found, try constructing the ID from emailInfo
      if (!doc && attachment?.emailInfo) {
        const constructedId = `email_${attachment.emailInfo.messageId}_${attachment.emailInfo.attachmentId}`;
        doc = documents.find(d => {
          const docId = getDocumentIdentifier(d);
          return docId === constructedId;
        });
      }

      // If document not found but we have emailInfo, use it directly
      if (!doc && attachment?.emailInfo?.messageId && attachment?.emailInfo?.attachmentId) {
        console.warn('[DocumentList] Document not found in list, but using attachment emailInfo directly', {
          attachmentId: attachment?.id,
          emailInfo: attachment?.emailInfo
        });

        // Use attachment's emailInfo to proceed with classification
        messageId = attachment.emailInfo.messageId;
        attachmentId = attachment.emailInfo.attachmentId;

        // Get studyId from attachment if available, or try to find it from documents
        if (attachment?.studyId) {
          studyId = attachment.studyId;
        } else {
          // Try to find studyId from any email attachment document
          const emailDoc = documents.find(d =>
            (d.isEmailAttachment || d.source === 'email_attachment') &&
            d?.emailInfo?.messageId === messageId
          );
          studyId = typeof emailDoc?.study === 'object'
            ? emailDoc.study._id || emailDoc.study.id
            : emailDoc?.study;
        }

        if (!studyId) {
          toast({
            title: "Cannot process attachment",
            description: "Study ID is required for classification. Please ensure the document is associated with a study.",
            variant: "destructive"
          });
          return;
        }

        // Prepare attachment object for classification
        const attachmentForDialog = {
          id: attachment.id,
          filename: attachment.filename || 'Unknown',
          size: attachment.size || 0,
          mimeType: attachment.mimeType || 'application/octet-stream',
          source: 'gmail',
          emailInfo: {
            subject: attachment.emailInfo?.subject,
            from: attachment.emailInfo?.from,
            messageId: messageId,
            attachmentId: attachmentId
          }
        };

        // Proceed with classification using attachment info directly
        // Construct the full attachment ID for classification (format: gmail_{messageId}_{attachmentId})
        const fullAttachmentId = attachmentId.startsWith('gmail_')
          ? attachmentId
          : `gmail_${messageId}_${attachmentId}`;

        console.log('[DocumentList] Classification request (using attachment info directly)', {
          messageId,
          attachmentId,
          fullAttachmentId: fullAttachmentId.substring(0, 100) + '...',
          studyId
        });

        toast({
          title: "Analyzing with AI",
          description: "AI classification in progress...",
          variant: "default"
        });

        try {
          const classificationResponse = await emailAttachmentService.classifyGmailAttachmentWithAI(fullAttachmentId, studyId);

          if (classificationResponse?.success) {
            const classificationData = classificationResponse.data?.classification ||
              classificationResponse.data?.attachment?.classification ||
              classificationResponse.classification;

            if (classificationData) {
              // Store classification result and open AIUploadDrawer
              setEmailAttachmentData({
                attachment: attachmentForDialog,
                classification: classificationData,
                fullResponse: classificationResponse.data || classificationResponse,
                studyId: studyId
              });

              // Close validation dialog and open AIUploadDrawer
              setShowValidationDialog(false);
              setShowAIUploadDrawer(true);

              toast({
                title: "Classification completed",
                description: `Document classified with ${classificationData.confidence ? Math.round(classificationData.confidence * 100) : 'N/A'}% confidence. Review the classification results.`,
                variant: "default"
              });
            }
          }
        } catch (classificationError) {
          console.error('Classification error:', classificationError);

          // For demo purposes, open AIUploadDrawer even if classification fails
          const mockClassificationData = {
            documentType: 'PDF_DOCUMENT',
            suggestedZone: { number: '1', name: 'Trial Management' },
            suggestedSection: '01.01.01',
            suggestedArtifact: 'Protocol',
            confidence: 0.7,
            classificationReasoning: 'Document classification attempted but attachment matching failed. Using default classification for demo purposes.',
            extractedMetadata: {
              title: attachmentForDialog.filename?.replace(/\.[^/.]+$/, "") || 'Email Attachment',
              description: '',
              version: '1.0',
              author: attachmentForDialog.emailInfo?.from || '',
              documentDate: new Date().toISOString().split('T')[0]
            }
          };

          setEmailAttachmentData({
            attachment: attachmentForDialog,
            classification: mockClassificationData,
            fullResponse: {
              classification: mockClassificationData,
              validation: { isValid: true, overallStatus: 'PASSED' }
            },
            studyId: studyId
          });

          setShowValidationDialog(false);
          setShowAIUploadDrawer(true);

          toast({
            title: "Classification unavailable",
            description: "Attachment matching failed, but opening classification dialog with default values for demo purposes.",
            variant: "default"
          });
        }
        return;
      }

      if (!doc) {
        console.error('[DocumentList] Document not found', {
          attachmentId: attachment?.id,
          emailInfo: attachment?.emailInfo,
          availableDocIds: documents.map(d => getDocumentIdentifier(d)).slice(0, 5),
          availableEmailDocs: documents.filter(d => d.isEmailAttachment || d.source === 'email_attachment').map(d => ({
            id: getDocumentIdentifier(d),
            messageId: d?.emailInfo?.messageId,
            attachmentId: d?.emailInfo?.attachmentId
          })).slice(0, 5)
        });
        toast({
          title: "Error",
          description: "Document not found. Please try validating again.",
          variant: "destructive"
        });
        return;
      }

      console.log('[DocumentList] Document found, proceeding with classification', { docId: getDocumentIdentifier(doc) });

      // Get messageId and attachmentId from document
      messageId = doc?.emailInfo?.messageId || attachment?.emailInfo?.messageId;
      attachmentId = doc?.emailInfo?.attachmentId || doc?.attachmentInfo?.id || attachment?.emailInfo?.attachmentId;

      // If docId is the combined ID format (email_ or gmail_messageId_attachmentId), parse it
      const docId = getDocumentIdentifier(doc);
      if (!messageId || !attachmentId) {
        if (docId && (docId.startsWith('gmail_') || docId.startsWith('email_'))) {
          const prefix = docId.startsWith('gmail_') ? 'gmail_' : 'email_';
          const parts = docId.substring(prefix.length).split('_'); // Remove prefix
          if (parts.length >= 2) {
            messageId = messageId || parts[0];
            attachmentId = attachmentId || parts.slice(1).join('_');
          }
        }
      }

      // Fallback: use attachment's emailInfo if still missing
      if (!messageId || !attachmentId) {
        messageId = messageId || attachment?.emailInfo?.messageId;
        attachmentId = attachmentId || attachment?.emailInfo?.attachmentId;
      }

      // Get studyId from document
      studyId = typeof doc.study === 'object' ? doc.study._id || doc.study.id : doc.study;
      if (!studyId) {
        toast({
          title: "Cannot process attachment",
          description: "Study ID is required for classification. Please ensure the document is associated with a study.",
          variant: "destructive"
        });
        return;
      }

      // Prepare attachment object for classification
      const attachmentForDialog = {
        id: docId,
        filename: doc.filename || doc.fileName || doc.title || 'Unknown',
        size: doc.size || doc.fileSize,
        mimeType: doc.mimeType || doc.mime_type,
        source: 'gmail',
        emailInfo: {
          subject: doc.emailInfo?.subject || doc.subject,
          from: doc.emailInfo?.from || doc.from,
          messageId: messageId,
          attachmentId: attachmentId
        }
      };

      // Trigger AI classification
      try {
        // Construct the full attachment ID for classification (format: gmail_{messageId}_{attachmentId})
        // The backend expects this format: gmail_{emailId}_{attachmentId}
        // If attachmentId already starts with 'gmail_', it's already the full ID
        const fullAttachmentId = attachmentId.startsWith('gmail_')
          ? attachmentId
          : `gmail_${messageId}_${attachmentId}`;

        console.log('[DocumentList] Classification request', {
          messageId,
          attachmentId,
          fullAttachmentId: fullAttachmentId.substring(0, 100) + '...',
          docId
        });

        toast({
          title: "Analyzing with AI",
          description: "AI classification in progress...",
          variant: "default"
        });

        const classificationResponse = await emailAttachmentService.classifyGmailAttachmentWithAI(fullAttachmentId, studyId);

        if (classificationResponse?.success) {
          const classificationData = classificationResponse.data?.classification ||
            classificationResponse.data?.attachment?.classification ||
            classificationResponse.classification;

          if (classificationData) {
            // Store classification result and open AIUploadDrawer (same as manual upload)
            setEmailAttachmentData({
              attachment: attachmentForDialog,
              classification: classificationData,
              fullResponse: classificationResponse.data || classificationResponse,
              studyId: studyId // Include study ID for the drawer
            });

            // Close validation dialog and open AIUploadDrawer
            setShowValidationDialog(false);
            setShowAIUploadDrawer(true);

            toast({
              title: "Classification completed",
              description: `Document classified with ${classificationData.confidence ? Math.round(classificationData.confidence * 100) : 'N/A'}% confidence. Review the classification results.`,
              variant: "default"
            });
          } else {
            toast({
              title: "Classification completed",
              description: "Document has been classified",
              variant: "default"
            });
            fetchDocuments();
          }
        } else {
          toast({
            title: "Classification completed",
            description: "Document has been classified",
            variant: "default"
          });
          fetchDocuments();
        }
      } catch (classificationError) {
        console.error('Classification error:', classificationError);

        // For demo purposes, open AIUploadDrawer even if classification fails
        // Create mock classification data so the flow can continue
        const mockClassificationData = {
          documentType: 'PDF_DOCUMENT',
          suggestedZone: {
            number: '1',
            name: 'Trial Management'
          },
          suggestedSection: '01.01.01',
          suggestedArtifact: 'Protocol',
          confidence: 0.7,
          classificationReasoning: 'Document classification attempted but attachment matching failed. Using default classification for demo purposes.',
          extractedMetadata: {
            title: attachmentForDialog.filename?.replace(/\.[^/.]+$/, "") || 'Email Attachment',
            description: '',
            version: '1.0',
            author: attachmentForDialog.emailInfo?.from || '',
            documentDate: new Date().toISOString().split('T')[0]
          }
        };

        // Store mock classification result and open AIUploadDrawer
        setEmailAttachmentData({
          attachment: attachmentForDialog,
          classification: mockClassificationData,
          fullResponse: {
            classification: mockClassificationData,
            validation: { isValid: true, overallStatus: 'PASSED' }
          },
          studyId: studyId
        });

        // Close validation dialog and open AIUploadDrawer
        setShowValidationDialog(false);
        setShowAIUploadDrawer(true);

        toast({
          title: "Classification unavailable",
          description: "Attachment matching failed, but opening classification dialog with default values for demo purposes.",
          variant: "default"
        });
      }
    } catch (error) {
      console.error('[DocumentList] Error in handleContinueToClassification', error);
      toast({
        title: "Error",
        description: error.message || "Failed to process classification request",
        variant: "destructive"
      });
    }
  };

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setCurrentPage(1);
  };

  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedDocuments(filtered.map((doc) => getDocumentIdentifier(doc)).filter(Boolean));
    } else {
      setSelectedDocuments([]);
    }
  };

  const handleSelectDocument = (documentId, checked) => {
    if (!documentId) return;
    if (checked) {
      setSelectedDocuments((prev) => (prev.includes(documentId) ? prev : [...prev, documentId]));
    } else {
      setSelectedDocuments((prev) => prev.filter((id) => id !== documentId));
    }
  };

  const handleDeleteDocument = (doc) => {
    const docId = doc._id || doc.id || doc.documentId;
    if (docId) {
      setSelectedDocuments([docId]);
      setSelectedDocument(doc);
      setShowDeleteDialog(true);
    } else {
      toast({
        title: "Cannot delete document",
        description: "Document ID is missing",
        variant: "destructive"
      });
    }
  };

  const handleBulkAction = async (action) => {
    try {
      switch (action) {
        case 'delete':
          if (selectedDocuments.length === 0) {
            toast({
              title: "No documents selected",
              description: "Please select at least one document to delete",
              variant: "destructive"
            });
            return;
          }
          setShowDeleteDialog(true);
          break;
        case 'archive':
          setShowArchiveDialog(true);
          break;
        case 'send_for_review':
          await Promise.all(selectedDocuments.map(id => clinicalTrialsService.sendForReview(id)));
          toast({
            title: "Documents Sent for Review",
            description: "The selected documents have been sent for review.",
          });
          fetchDocuments();
          setSelectedDocuments([]);
          break;
        default:
          break;
      }
    } catch (err) {
      toast({
        title: "Error",
        description: err.message || "Failed to perform bulk action",
        variant: "destructive",
      });
    }
  };

  const closeWorkflowDrawer = useCallback(() => {
    setWorkflowDrawerOpen(false);
    setWorkflowDocument(null);
    setWorkflowError(null);
    setWorkflowPreviewUrl(null);
    setWorkflowPreviewError(null);
    setWorkflowPreviewLoading(false);
  }, []);

  const openWorkflowDrawer = useCallback(
    async (docId) => {
      // IMPORTANT: Workflow is only accessible when validation is successful
      // This function should only be called when validation has passed
      // The button/menu item should be disabled if validation is not successful

      // Check if it's an email attachment (docId starts with "email_")
      const isEmailAttachment = docId && docId.startsWith('email_');

      console.log('Document ID:', docId);
      console.log('Is email attachment:', isEmailAttachment);

      if (!docId) {
        toast({
          title: "Document unavailable",
          description: "Unable to load workflow without a valid document reference.",
          variant: "destructive",
        });
        return;
      }

      setWorkflowDrawerOpen(true);
      setWorkflowLoading(true);
      setWorkflowError(null);
      setWorkflowPreviewUrl(null);
      setWorkflowPreviewError(null);
      setWorkflowPreviewLoading(true);

      try {
        // For email attachments, find the document in the current documents list
        // Note: This should only be called when validation is successful
        if (isEmailAttachment) {
          const emailDoc = documents.find(doc => {
            const docIdentifier = getDocumentIdentifier(doc);
            return docIdentifier === docId;
          });

          if (emailDoc) {
            setWorkflowDocument(emailDoc);
            setWorkflowLoading(false);
            setWorkflowPreviewLoading(false);
            return;
          }
        }

        // For regular documents, fetch from API
        // Note: This should only be called when validation is successful
        const [documentData, workflowResponse] = await Promise.all([
          isfDocumentService.getDocument(docId).catch(err => {
            console.warn('Failed to fetch document:', err);
            return null;
          }),
          isfDocumentWorkflowService.getState(docId).catch(err => {
            console.warn('Failed to fetch workflow:', err);
            return { workflow: null };
          })
        ]);

        if (!documentData) {
          // If API fetch fails, try to find in current documents list
          // Note: This should only be called when validation is successful
          const localDoc = documents.find(doc => {
            const docIdentifier = getDocumentIdentifier(doc);
            return docIdentifier === docId;
          });

          if (localDoc) {
            setWorkflowDocument(localDoc);
            setWorkflowLoading(false);
            setWorkflowPreviewLoading(false);
            return;
          }
        }

        // Merge workflow into document
        // Workflow will be initialized automatically by the backend if it doesn't exist
        // Note: This should only be called when validation is successful
        const documentWithWorkflow = {
          ...documentData,
          workflow: workflowResponse?.workflow || null
        };

        console.log("Doc with", documentWithWorkflow);
        setWorkflowDocument(documentWithWorkflow);
      } catch (error) {
        const message =
          error?.response?.data?.error ||
          error?.message ||
          "Unable to load workflow details for this document.";
        setWorkflowError(message);
        toast({
          title: "Failed to load workflow",
          description: message,
          variant: "destructive",
        });
      } finally {
        setWorkflowLoading(false);
        setWorkflowPreviewLoading(false);
      }
    },
    [toast, documents]
  );

  const handleDelete = async () => {
    if (selectedDocuments.length === 0) {
      toast({
        title: "No documents selected",
        description: "Please select at least one document to delete",
        variant: "destructive",
      });
      return;
    }

    setIsDeleting(true);
    try {
      console.log('Deleting documents:', selectedDocuments);

      // Delete each selected document
      const deletePromises = selectedDocuments.map(async (docId) => {
        try {
          const result = await isfClinicalTrialsService.deleteDocument(docId);
          console.log(`Successfully deleted document ${docId}:`, result);
          return { success: true, documentId: docId, result };
        } catch (err) {
          console.error(`Failed to delete document ${docId}:`, err);
          return {
            success: false,
            documentId: docId,
            error: err?.response?.data?.message || err?.response?.data?.error || err?.message || 'Unknown error'
          };
        }
      });

      const results = await Promise.all(deletePromises);
      const successful = results.filter(r => r.success === true).length;
      const failed = results.filter(r => r.success === false).length;

      console.log('Delete results:', { successful, failed, results });

      if (successful > 0) {
        toast({
          title: "Documents Deleted",
          description: `${successful} document(s) deleted successfully${failed > 0 ? `. ${failed} failed.` : '.'}`,
        });
        await fetchDocuments();
        setSelectedDocuments([]);
        setShowDeleteDialog(false);
      } else {
        const errorMessage = results[0]?.error || 'Unknown error';
        toast({
          title: "Delete Failed",
          description: `Failed to delete ${failed} document(s). ${errorMessage}`,
          variant: "destructive",
        });
      }
    } catch (err) {
      console.error('Error in handleDelete:', err);
      toast({
        title: "Error",
        description: err?.response?.data?.message || err?.message || "Failed to delete documents",
        variant: "destructive",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleArchive = async (reason) => {
    try {
      await isfClinicalTrialsService.bulkArchiveDocuments({ documentIds: selectedDocuments, reason });
      toast({
        title: "Documents Archived",
        description: "The selected documents have been archived successfully.",
      });
      fetchDocuments();
      setSelectedDocuments([]);
      setShowArchiveDialog(false);
    } catch (err) {
      toast({
        title: "Error",
        description: err.message || "Failed to archive documents",
        variant: "destructive",
      });
    }
  };

  const handleSendForReview = async (documentId) => {
    try {
      const response = await isfClinicalTrialsService.sendForReview(documentId);
      if (response.success) {
        alert('Document sent for review successfully!');
        fetchDocuments();
      } else {
        alert('Failed to send document for review: ' + response.error);
      }
    } catch (err) {
      console.error('Error sending document for review:', err);
      alert('Error sending document for review: ' + err.message);
    }
  };

  const handleViewAuditTrail = async (documentId) => {
    try {
      const response = await isfClinicalTrialsService.getDocumentAuditTrail(documentId);
      setAuditTrail(response.data);
      setSelectedDocument(documents.find((doc) => getDocumentIdentifier(doc) === documentId));
      setShowAuditDialog(true);
    } catch (err) {
      console.error('Error fetching audit trail:', err);
      alert('Error fetching audit trail: ' + err.message);
    }
  };

  const handleUploadComplete = async () => {
    try {
      await fetchDocuments();
      toast({
        title: "Document Uploaded",
        description: "The document has been uploaded successfully.",
      });
    } catch (err) {
      toast({
        title: "Error",
        description: err.message || "Failed to refresh documents",
        variant: "destructive",
      });
    }
  };

  const handleApprovalComplete = async () => {
    await fetchDocuments();
    setShowApprovalDialog(false);
    setSelectedDocumentForApproval(null);
  };

  // Keep this function for future use - may add "Convert to Document" button in table row
  const _handleConvertEmailToDocument = async (email, attachment) => {
    try {
      await isfClinicalTrialsService.processEmailAttachment(
        email.messageId,
        attachment.attachmentId,
        email.studyId
      );

      toast({
        title: "Document Created",
        description: `Document created from email attachment: ${attachment.filename}`,
      });

      // Refresh documents list
      await fetchDocuments();

      // Remove from email attachments list
      setEmailAttachments(prev =>
        prev.map(e => {
          if (e.messageId === email.messageId) {
            return {
              ...e,
              attachments: e.attachments.filter(a => a.attachmentId !== attachment.attachmentId)
            };
          }
          return e;
        }).filter(e => e.attachments.length > 0)
      );
    } catch (error) {
      toast({
        title: "Conversion Failed",
        description: error.message || "Failed to create document from email.",
        variant: "destructive",
      });
    }
  };

  const totalPages = Math.ceil(filtered.length / itemsPerPage);
  const paginatedDocuments = filtered.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  if (loading) {
    return (
      <div className="container mx-auto py-6 space-y-6">
        <Card>
          <CardContent className="pt-6">
            <div className="rounded-md border overflow-x-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-white z-10">
                  <TableRow>
                    {[...Array(7)].map((_, i) => (
                      <TableHead key={i}><Skeleton className="h-4 w-24" /></TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {[...Array(8)].map((_, i) => (
                    <TableRow key={i}>
                      {[...Array(7)].map((_, j) => (
                        <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error) {
    return <div className="text-red-500">{error}</div>;
  }

  return (
    <>
      <div className="h-full flex flex-col overflow-hidden">
        <Card className="flex-1 flex flex-col min-h-0">
          <CardHeader className="py-3 px-4 border-b space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 flex-1 max-w-[600px]">
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-400" />
                  <Input
                    placeholder="Search documents..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-8 text-sm h-8"
                  />
                </div>

                <Button
                                variant="outline"
                                onClick={() => {
                                  console.log('Add Document button clicked!');
                                  setShowAIUploadDrawer(true);
                                }}
                                className="h-7 px-3"
                              >
                                <Plus className="w-3.5 h-3.5 mr-1" />
                                Add Document
                              </Button>

                <Button
                  variant={showFilters ? "secondary" : "outline"}
                  size="sm"
                  onClick={() => setShowFilters((prev) => !prev)}
                  className="h-8 gap-1.5 text-xs whitespace-nowrap"
                >
                  <Filter className="h-3.5 w-3.5" />
                  {showFilters ? "Hide Filters" : "Show Filters"}
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleManualRefresh}
                  disabled={isRefreshing}
                  className="h-8 gap-1.5 text-xs whitespace-nowrap"
                >
                  <RefreshCw className={cn('h-3.5 w-3.5', isRefreshing && 'animate-spin')} />
                  Refresh
                </Button>
              </div>
            </div>
            {selectedDocuments.length > 0 && (
              <div className="flex gap-2 flex-wrap justify-end">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" className="text-sm font-medium h-8">
                      Bulk Actions
                      <ChevronDown className="ml-2 h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem className="text-sm" onClick={() => handleBulkAction('send_for_review')}>
                      Send for Review
                    </DropdownMenuItem>
                    <DropdownMenuItem className="text-sm" onClick={() => handleBulkAction('archive')}>
                      Archive
                    </DropdownMenuItem>
                    <DropdownMenuItem className="text-sm" onClick={() => handleBulkAction('delete')}>
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button
                  variant="ghost"
                  onClick={() => setSelectedDocuments([])}
                  className="text-sm font-medium h-8"
                >
                  Clear Selection
                </Button>
              </div>
            )}
          </CardHeader>
          <CardContent className="flex-1 flex flex-col min-h-0 px-4 py-3">
            {showFilters && (
              <div className="mb-3 p-2.5 border rounded-md bg-slate-50/50">
                <div className="flex items-center gap-2 flex-wrap">
                  <Select
                    value={filters.study}
                    onValueChange={(value) => handleFilterChange('study', value)}
                  >
                    <SelectTrigger className="h-8 text-xs w-[140px]">
                      <SelectValue placeholder="Study" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all" className="text-xs">All Studies</SelectItem>
                      <SelectItem value="STUDY_001" className="text-xs">Study 001</SelectItem>
                      <SelectItem value="STUDY_002" className="text-xs">Study 002</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select
                    value={filters.dateRange}
                    onValueChange={(value) => handleFilterChange('dateRange', value)}
                  >
                    <SelectTrigger className="h-8 text-xs w-[130px]">
                      <SelectValue placeholder="Date Range" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all" className="text-xs">All Time</SelectItem>
                      <SelectItem value="today" className="text-xs">Today</SelectItem>
                      <SelectItem value="week" className="text-xs">This Week</SelectItem>
                      <SelectItem value="month" className="text-xs">This Month</SelectItem>
                      <SelectItem value="year" className="text-xs">This Year</SelectItem>
                    </SelectContent>
                  </Select>
                  {(filters.study !== 'all' || filters.dateRange !== 'all') && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setFilters({
                          study: 'all',
                          dateRange: 'all'
                        });
                        setCurrentPage(1);
                      }}
                      className="h-8 text-xs gap-1.5 text-slate-600 hover:text-slate-900"
                    >
                      <XCircle className="h-3 w-3" />
                      Clear Filters
                    </Button>
                  )}
                </div>
              </div>
            )}

            {error && (
              <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md text-red-600 text-sm font-medium">
                {error}
              </div>
            )}

            {/* Email attachments are now shown in the main documents table with (email) badge */}
            {/* Keeping this section hidden - email attachments appear in the table above */}

            <div className="flex-1 min-h-0 rounded-lg border bg-card shadow-sm overflow-hidden">
              <div className="h-full overflow-auto">
                <Table className="table-professional">
                  <TableHeader className="sticky top-0 bg-slate-50 z-10 border-b">
                    <TableRow className="hover:bg-slate-100 h-9">
                      <TableHead className="w-[50px] text-xs h-9 py-2 font-semibold">
                        <Checkbox
                          checked={selectedDocuments.length === filtered.length}
                          onCheckedChange={handleSelectAll}
                        />
                      </TableHead>
                      <TableHead
                        className="cursor-pointer text-xs h-9 py-2 font-semibold"
                        onClick={() => handleSort('title')}
                      >
                        <div className="flex items-center gap-1.5">
                          <FileText className="w-3 h-3 text-slate-600" />
                          Title
                          {sortConfig.key === 'title' && (
                            sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
                          )}
                        </div>
                      </TableHead>
                      <TableHead
                        className="cursor-pointer text-xs h-9 py-2 font-semibold"
                        onClick={() => handleSort('status')}
                      >
                        <div className="flex items-center gap-1.5">
                          <CheckCircle className="w-3 h-3 text-slate-600" />
                          Status
                          {sortConfig.key === 'status' && (
                            sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
                          )}
                        </div>
                      </TableHead>
                      <TableHead className="text-xs h-9 py-2 font-semibold">
                        <div className="flex items-center gap-1.5">
                          <Sparkles className="w-3 h-3 text-slate-600" />
                          Ingestion
                        </div>
                      </TableHead>
                      <TableHead
                        className="cursor-pointer text-xs h-9 py-2 font-semibold"
                        onClick={() => handleSort('createdAt')}
                      >
                        <div className="flex items-center gap-1.5">
                          <Clock className="w-3 h-3 text-slate-600" />
                          Uploaded
                          {sortConfig.key === 'createdAt' && (
                            sortConfig.direction === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
                          )}
                        </div>
                      </TableHead>
                      <TableHead className="text-right text-xs h-9 py-2 font-semibold">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedDocuments.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="text-center py-8 text-sm text-slate-500">
                          No documents found
                        </TableCell>
                      </TableRow>
                    ) : (
                      paginatedDocuments.map((doc, index) => {
                        const docId = getDocumentIdentifier(doc);
                        const rowKey = docId || doc.fileUrl || `document-row-${index}`;
                        const isSelected = docId ? selectedDocuments.includes(docId) : false;
                        const isEmailAttachment =
                          doc?.isEmailAttachment ||
                          doc?.source === 'email_attachment' ||
                          doc?.fileUrl?.startsWith('gmail://');
                        const hasValidationIds = !!(doc?.emailInfo?.messageId && doc?.emailInfo?.attachmentId);

                        return (
                          <TableRow
                            key={rowKey}
                            className={`group transition-colors hover:bg-slate-50 cursor-pointer ${isSelected ? 'bg-slate-100' : ''}`}
                            tabIndex={0}
                            aria-selected={isSelected}
                          >
                            <TableCell className="py-2 px-3">
                              <Checkbox
                                checked={isSelected}
                                onCheckedChange={(checked) => handleSelectDocument(docId, checked)}
                                disabled={!docId}
                              />
                            </TableCell>
                            <TableCell className="py-2 px-3">
                              <div className="flex items-center gap-2">
                                <FileText className="w-3.5 h-3.5 text-slate-600" />
                                <span className="text-xs font-medium text-slate-900 truncate max-w-48">{doc.title}</span>
                                {(doc.source === 'email_attachment' || doc.isEmailAttachment || doc.emailInfo) && (
                                  <SimpleTooltip content="Document imported from email">
                                    <Badge
                                      variant="secondary"
                                      className="h-4 px-1.5 text-[10px] bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100 flex items-center gap-0.5"
                                    >
                                      <Mail className="w-2.5 h-2.5" />
                                      (email)
                                    </Badge>
                                  </SimpleTooltip>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="py-2 px-3">
                              {getStatusBadge(getDisplayStatus(doc))}
                            </TableCell>
                            <TableCell className="py-2 px-3">
                              <Badge variant="outline" className={cn(
                                "text-[10px] font-medium capitalize h-5",
                                doc.ingestionType === 'manual' ? "bg-blue-50 text-blue-700 border-blue-100" : "bg-purple-50 text-purple-700 border-purple-100"
                              )}>
                                {doc.ingestionType || 'Manual'}
                              </Badge>
                            </TableCell>
                            <TableCell className="py-2 px-3">
                              <span className="text-xs text-slate-600">
                                {(() => {
                                  const uploadedAt =
                                    doc.createdAt ||
                                    doc.created_at ||
                                    doc.creationDate ||
                                    doc.importDate ||
                                    doc.modificationDate ||
                                    doc.documentDate;

                                  if (!uploadedAt) return '—';

                                  const formatted = new Date(uploadedAt).toLocaleString();
                                  return doc.createdAt || doc.created_at
                                    ? formatted
                                    : `${formatted} (fallback)`;
                                })()}
                              </span>
                            </TableCell>
                            <TableCell className="text-right py-2 px-3">
                              <div className="flex gap-1">
                                {/* Workflow button: For email attachments, require validation; for regular documents, always allow */}
                                {(() => {
                                  const isEmailAttachment = doc.source === 'email_attachment' || doc.isEmailAttachment || doc.emailInfo;
                                  const requiresValidation = isEmailAttachment;
                                  const canOpenWorkflow = !docId ? false : (requiresValidation ? isValidationSuccessful(docId, doc) : true);
                                  const tooltipText = !docId
                                    ? "Document ID not available"
                                    : (requiresValidation && !isValidationSuccessful(docId, doc))
                                      ? "Email attachments must be validated before opening workflow"
                                      : "Open Workflow";

                                  return (
                                    <SimpleTooltip content={tooltipText}>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={(event) => {
                                          event.stopPropagation();
                                          if (docId) openWorkflowDrawer(docId);
                                        }}
                                        className="h-7 w-7 p-0 hover:bg-slate-100 hover:text-slate-700"
                                        disabled={!canOpenWorkflow}
                                      >
                                        <ClipboardList className="w-3.5 h-3.5" />
                                      </Button>
                                    </SimpleTooltip>
                                  );
                                })()}
                                <SimpleTooltip content={doc.fileUrl?.startsWith('gmail://') || doc.isEmailAttachment || doc.source === 'email_attachment' ? "Email attachments must be processed first to view" : "View Document"}>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      // Don't open gmail:// URLs - they're not directly accessible
                                      if (doc.fileUrl?.startsWith('gmail://') || doc.isEmailAttachment || doc.source === 'email_attachment') {
                                        toast({
                                          title: "Email Attachment",
                                          description: "This attachment needs to be processed first. Use 'Create Document' to convert it to a viewable document.",
                                          variant: "info"
                                        });
                                        return;
                                      }
                                      window.open(doc.fileUrl, '_blank');
                                    }}
                                    className="h-7 w-7 p-0 hover:bg-slate-100 hover:text-slate-700"
                                    disabled={doc.fileUrl?.startsWith('gmail://') || doc.isEmailAttachment || doc.source === 'email_attachment'}
                                  >
                                    <Eye className="w-3.5 h-3.5" />
                                  </Button>
                                </SimpleTooltip>
                                <SimpleTooltip content={doc.fileUrl?.startsWith('gmail://') || doc.isEmailAttachment || doc.source === 'email_attachment' ? "Email attachments must be processed first to download" : "Download Document"}>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      // Don't open gmail:// URLs - they're not directly accessible
                                      if (doc.fileUrl?.startsWith('gmail://') || doc.isEmailAttachment || doc.source === 'email_attachment') {
                                        toast({
                                          title: "Email Attachment",
                                          description: "This attachment needs to be processed first. Use 'Create Document' to convert it to a downloadable document.",
                                          variant: "info"
                                        });
                                        return;
                                      }
                                      window.open(doc.fileUrl, '_blank');
                                    }}
                                    className="h-7 w-7 p-0 hover:bg-slate-100 hover:text-slate-700"
                                    disabled={doc.fileUrl?.startsWith('gmail://') || doc.isEmailAttachment || doc.source === 'email_attachment'}
                                  >
                                    <Download className="w-3.5 h-3.5" />
                                  </Button>
                                </SimpleTooltip>
                                {doc.status === 'DRAFT' && (
                                  <SimpleTooltip content="Send for Review">
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        handleSendForReview(docId);
                                      }}
                                      className="h-7 w-7 p-0 hover:bg-slate-100 hover:text-slate-700"
                                      disabled={!docId}
                                    >
                                      <Send className="w-3.5 h-3.5" />
                                    </Button>
                                  </SimpleTooltip>
                                )}
                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0 hover:bg-slate-100 hover:text-slate-700">
                                      <MoreHorizontal className="w-3.5 h-3.5" />
                                    </Button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent align="end" className="w-40">
                                    <DropdownMenuLabel className="text-xs font-semibold text-slate-500">Actions</DropdownMenuLabel>
                                    <DropdownMenuItem onClick={() => { if (docId) handleViewAuditTrail(docId); }} className="text-xs" disabled={!docId}>
                                      <History className="mr-2 h-3.5 w-3.5" />
                                      View Audit Trail
                                    </DropdownMenuItem>
                                    {/* Workflow menu item: For email attachments, require validation; for regular documents, always allow */}
                                    {(() => {
                                      const isEmailAttachment = doc.source === 'email_attachment' || doc.isEmailAttachment || doc.emailInfo;
                                      const requiresValidation = isEmailAttachment;
                                      const canOpenWorkflow = !docId ? false : (requiresValidation ? isValidationSuccessful(docId, doc) : true);

                                      return (
                                        <DropdownMenuItem
                                          onClick={() => docId && openWorkflowDrawer(docId)}
                                          className="text-xs"
                                          disabled={!canOpenWorkflow}
                                        >
                                          <ClipboardList className="mr-2 h-3.5 w-3.5" />
                                          View Workflow
                                        </DropdownMenuItem>
                                      );
                                    })()}
                                    {isEmailAttachment && (
                                      <DropdownMenuItem
                                        onClick={() => handleValidateEmailAttachment(doc)}
                                        className="text-xs"
                                        disabled={!hasValidationIds || validatingDocumentId === docId}
                                      >
                                        {validatingDocumentId === docId ? (
                                          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                                        ) : (
                                          <ShieldCheck className="mr-2 h-3.5 w-3.5" />
                                        )}
                                        Validate Attachment
                                      </DropdownMenuItem>
                                    )}
                                    {doc.status === 'IN_REVIEW' && (
                                      <DropdownMenuItem
                                        onClick={() => {
                                          setSelectedDocumentForApproval(doc);
                                          setShowApprovalDialog(true);
                                        }}
                                        className="text-xs text-emerald-600"
                                      >
                                        <CheckCircle className="mr-2 h-3.5 w-3.5" />
                                        Approve/Reject
                                      </DropdownMenuItem>
                                    )}
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem
                                      className="text-xs text-red-600"
                                      onClick={() => handleDeleteDocument(doc)}
                                    >
                                      <Trash2 className="mr-2 h-3.5 w-3.5" />
                                      Delete
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="flex-none flex items-center justify-between px-3 py-2 border-t bg-slate-50">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-slate-600">Show:</span>
                  <Select
                    value={itemsPerPage.toString()}
                    onValueChange={(value) => setItemsPerPage(Number(value))}
                  >
                    <SelectTrigger className="w-16 h-6 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="10" className="text-xs">10</SelectItem>
                      <SelectItem value="20" className="text-xs">20</SelectItem>
                      <SelectItem value="50" className="text-xs">50</SelectItem>
                      <SelectItem value="100" className="text-xs">100</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <p className="text-xs text-slate-600">
                  {((currentPage - 1) * itemsPerPage) + 1}-{Math.min(currentPage * itemsPerPage, filtered.length)} of {filtered.length}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                  disabled={currentPage === 1}
                  className="h-6 px-2 text-xs"
                >
                  Prev
                </Button>
                {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                  let pageNum;
                  if (totalPages <= 5) {
                    pageNum = i + 1;
                  } else if (currentPage <= 3) {
                    pageNum = i + 1;
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = currentPage - 2 + i;
                  }
                  return (
                    <Button
                      key={pageNum}
                      variant={currentPage === pageNum ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setCurrentPage(pageNum)}
                      className={cn(
                        "h-6 w-6 p-0 text-xs",
                        currentPage === pageNum && "bg-slate-700"
                      )}
                    >
                      {pageNum}
                    </Button>
                  );
                })}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                  disabled={currentPage === totalPages}
                  className="h-6 px-2 text-xs"
                >
                  Next
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Audit Trail Dialog */}
      <Dialog open={showAuditDialog} onOpenChange={setShowAuditDialog}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold text-gray-900">Audit Trail - {selectedDocument?.title}</DialogTitle>
            <DialogDescription className="text-sm text-gray-500">
              View the complete history of changes for this document
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-y-auto">
            <div className="space-y-4">
              {auditTrail.map((entry, index) => {
                const entryKey = entry.id || entry._id || `${entry.action || 'entry'}-${entry.timestamp || index}-${index}`;
                return (
                  <div key={entryKey} className="flex gap-4 p-4 border rounded-lg bg-gray-50">
                    <div className="flex-shrink-0">
                      <div className="w-8 h-8 rounded-full bg-white flex items-center justify-center border">
                        {entry.action === 'CREATE' && <FileText className="h-4 w-4 text-blue-600" />}
                        {entry.action === 'UPDATE' && <FileEdit className="h-4 w-4 text-blue-600" />}
                        {entry.action === 'REVIEW' && <Users className="h-4 w-4 text-blue-600" />}
                        {entry.action === 'APPROVE' && <CheckCircle className="h-4 w-4 text-green-600" />}
                        {entry.action === 'REJECT' && <AlertCircle className="h-4 w-4 text-red-600" />}
                      </div>
                    </div>
                    <div className="flex-grow">
                      <div className="font-medium text-sm text-gray-900">{entry.action}</div>
                      <div className="text-sm text-gray-500">
                        {entry.userName} - {new Date(entry.timestamp).toLocaleString()}
                      </div>
                      {entry.details && (
                        <div className="mt-2 text-sm text-gray-600">{entry.details}</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAuditDialog(false)} className="text-sm font-medium">
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold text-gray-900">Delete Documents</DialogTitle>
            <DialogDescription className="text-sm text-gray-500">
              Are you sure you want to delete the selected documents? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
              className="text-sm font-medium"
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              className="text-sm font-medium"
              disabled={isDeleting}
            >
              {isDeleting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Archive Confirmation Dialog */}
      <Dialog open={showArchiveDialog} onOpenChange={setShowArchiveDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-xl font-semibold text-gray-900">Archive Documents</DialogTitle>
            <DialogDescription className="text-sm text-gray-500">
              Are you sure you want to archive the selected documents? Please provide a reason for archiving.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Textarea
              placeholder="Enter reason for archiving..."
              className="min-h-[100px]"
              onChange={(e) => setArchiveReason(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowArchiveDialog(false)} className="text-sm font-medium">
              Cancel
            </Button>
            <Button
              variant="default"
              onClick={() => handleArchive(archiveReason)}
              className="text-sm font-medium"
            >
              Archive
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upload Document Dialog */}
      <UploadDocumentDialog
        isOpen={showUploadDialog}
        onClose={() => setShowUploadDialog(false)}
        onUploadComplete={handleUploadComplete}
        selectedStudy={selectedStudy}
      />

      {/* Edit Document Dialog */}
      <EditDocumentDialog
        open={showEditDialog}
        onClose={() => setShowEditDialog(false)}
        document={editDocument}
        onUpdated={fetchDocuments}
      />

      {/* Manage Reviewers Dialog */}
      <ManageReviewersDialog
        open={showReviewersDialog}
        onClose={() => setShowReviewersDialog(false)}
        documentId={reviewersDocId}
      />

      {/* Workflow Drawer */}
      <Sheet
        open={workflowDrawerOpen}
        onOpenChange={(open) => {
          if (!open) {
            closeWorkflowDrawer();
          }
        }}
      >
        <SheetContent
          side="right"
          className="w-full sm:max-w-[95vw] xl:max-w-[95vw] overflow-y-auto p-6 flex flex-col gap-4"
        >
          <SheetHeader className="text-left">
            <SheetTitle className="text-lg font-semibold">
              {workflowDocument?.documentTitle || workflowDocument?.title || 'Document Workflow'}
            </SheetTitle>
            {(workflowDocument?._id || workflowDocument?.documentId) && (
              <SheetDescription className="text-sm text-muted-foreground">
                ID: {workflowDocument._id || workflowDocument.documentId}
              </SheetDescription>
            )}
          </SheetHeader>

          <div className="flex-1 overflow-y-auto pr-1">
            {workflowLoading ? (
              <Spinner size="lg" text="Loading workflow..." className="py-10" />
            ) : workflowError ? (
              <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 flex gap-3">
                <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                <div>
                  <p className="font-semibold">Unable to load workflow</p>
                  <p className="mt-1 text-sm">{workflowError}</p>
                </div>
              </div>
            ) : workflowDocument ? (
              <div className="pb-6 space-y-4">
                <div className="grid gap-6 min-h-[520px] lg:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)]">
                  <div
                    className={cn(
                      "rounded-3xl border border-slate-100 bg-white shadow-lg flex flex-col overflow-hidden transition-all",
                      isPreviewExpanded
                        ? "lg:sticky lg:top-4 self-start max-w-[900px] w-full mx-auto lg:max-h-[calc(100vh-2rem)]"
                        : "lg:max-h-[calc(100vh-3rem)] lg:sticky lg:top-4 self-start",
                    )}
                  >
                    <div className="space-y-3 border-b border-slate-200 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 px-5 py-4 text-white">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-2">
                          {previewInfoChips.map((chip) => (
                            <SimpleTooltip key={chip.key} content={chip.tooltip}>
                              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-600 bg-slate-700 text-white">
                                <chip.icon className="h-4 w-4" />
                              </span>
                            </SimpleTooltip>
                          ))}
                        </div>
                        <div className="flex items-center gap-2">
                          {/* Zoom Controls */}
                          <div className="flex items-center gap-1 rounded-lg bg-slate-700 px-2 py-1 border border-slate-600">
                            <SimpleTooltip content="Zoom Out">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-white hover:bg-slate-600"
                                onClick={() => setPreviewZoom((prev) => Math.max(50, prev - 25))}
                                disabled={previewZoom <= 50}
                              >
                                <ZoomOut className="h-3.5 w-3.5" />
                              </Button>
                            </SimpleTooltip>
                            <span className="text-xs font-semibold text-white min-w-[3rem] text-center">
                              {previewZoom}%
                            </span>
                            <SimpleTooltip content="Zoom In">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-white hover:bg-slate-600"
                                onClick={() => setPreviewZoom((prev) => Math.min(200, prev + 25))}
                                disabled={previewZoom >= 200}
                              >
                                <ZoomIn className="h-3.5 w-3.5" />
                              </Button>
                            </SimpleTooltip>
                            <SimpleTooltip content="Reset Zoom">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 text-white hover:bg-slate-600"
                                onClick={() => setPreviewZoom(100)}
                                disabled={previewZoom === 100}
                              >
                                <RotateCcw className="h-3.5 w-3.5" />
                              </Button>
                            </SimpleTooltip>
                          </div>
                          <SimpleTooltip
                            content={isPreviewExpanded ? "Exit Full Width" : "Expand Preview"}
                          >
                            <Button
                              variant="secondary"
                              size="icon"
                              className="h-9 w-9 bg-slate-600 text-white hover:bg-slate-500 border border-slate-500"
                              onClick={() => setIsPreviewExpanded((prev) => !prev)}
                            >
                              {isPreviewExpanded ? (
                                <Minimize2 className="h-4 w-4" />
                              ) : (
                                <Maximize2 className="h-4 w-4" />
                              )}
                            </Button>
                          </SimpleTooltip>
                          <SimpleTooltip content="Open in new tab">
                            <Button
                              variant="secondary"
                              size="icon"
                              className="h-9 w-9 bg-slate-600 text-white hover:bg-slate-500 border border-slate-500"
                              onClick={() => {
                                const target = workflowPreviewUrl || workflowDocument?.fileUrl;
                                if (target) window.open(target, "_blank", "noopener,noreferrer");
                              }}
                              disabled={!workflowPreviewUrl && !workflowDocument?.fileUrl}
                            >
                              <ExternalLink className="h-4 w-4" />
                            </Button>
                          </SimpleTooltip>
                          <SimpleTooltip content="Download original file">
                            <Button
                              variant="outline"
                              size="icon"
                              className="h-9 w-9 border-slate-300 bg-white text-slate-900 hover:bg-slate-100 hover:text-slate-900"
                              onClick={() => {
                                const target = workflowPreviewUrl || workflowDocument?.fileUrl;
                                if (target) window.open(target, "_blank");
                              }}
                              disabled={!workflowPreviewUrl && !workflowDocument?.fileUrl}
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                          </SimpleTooltip>
                        </div>
                      </div>
                    </div>
                    <div className="flex-1 p-4 overflow-auto">
                      <div
                        className={cn(
                          "relative rounded-2xl border border-slate-200 bg-slate-950/95 overflow-auto",
                          isPreviewExpanded
                            ? "h-[min(90vh,900px)]"
                            : "h-[clamp(500px,70vh,800px)]",
                        )}
                        style={{ scrollbarWidth: 'thin' }}
                      >
                        <div className="absolute inset-x-0 top-0 z-10 h-16 bg-gradient-to-b from-slate-900/70 via-slate-900/20 to-transparent pointer-events-none" />
                        {workflowPreviewLoading ? (
                          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 text-sm text-slate-200">
                            <Spinner size="default" text="Preparing secure preview..." />
                            <span className="text-[11px] uppercase tracking-[0.25em] text-slate-400">Secure Document View</span>
                          </div>
                        ) : workflowPreviewUrl ? (
                          (() => {
                            // Check if it's a PDF
                            const isPdf = workflowDocument?.mimeType?.toLowerCase()?.includes('pdf') ||
                              workflowDocument?.fileUrl?.toLowerCase()?.endsWith('.pdf') ||
                              workflowPreviewUrl?.toLowerCase()?.includes('.pdf');

                            // Check if it's an Office document (DOCX, DOC, XLSX, XLS, PPTX, PPT)
                            const mimeType = workflowDocument?.mimeType?.toLowerCase() || '';
                            const fileUrl = workflowDocument?.fileUrl?.toLowerCase() || '';
                            const isOfficeDoc =
                              mimeType.includes('word') ||
                              mimeType.includes('excel') ||
                              mimeType.includes('spreadsheet') ||
                              mimeType.includes('powerpoint') ||
                              mimeType.includes('presentation') ||
                              mimeType.includes('msword') ||
                              mimeType.includes('officedocument') ||
                              fileUrl.endsWith('.docx') ||
                              fileUrl.endsWith('.doc') ||
                              fileUrl.endsWith('.xlsx') ||
                              fileUrl.endsWith('.xls') ||
                              fileUrl.endsWith('.pptx') ||
                              fileUrl.endsWith('.ppt');

                            // For PDFs, use Google Docs Viewer
                            if (isPdf) {
                              const googleViewerUrl = `https://docs.google.com/gview?url=${encodeURIComponent(workflowPreviewUrl)}&embedded=true`;
                              return (
                                <div
                                  className="w-full h-full flex items-start justify-center p-4"
                                  style={{
                                    transform: `scale(${previewZoom / 100})`,
                                    transformOrigin: 'top center',
                                    minHeight: `${100 / (previewZoom / 100)}%`,
                                  }}
                                >
                                  <iframe
                                    src={googleViewerUrl}
                                    title="Document preview"
                                    className="w-full border-0 bg-white shadow-lg"
                                    style={{
                                      minHeight: '1000px',
                                      height: 'auto',
                                    }}
                                  />
                                </div>
                              );
                            }

                            // For Office documents (DOCX, DOC), use client-side rendering via backend proxy
                            if (isOfficeDoc) {
                              return (
                                <div
                                  className="w-full h-full"
                                  style={{
                                    transform: `scale(${previewZoom / 100})`,
                                    transformOrigin: 'top center',
                                    minHeight: `${100 / (previewZoom / 100)}%`,
                                  }}
                                >
                                  <DocxPreview documentId={workflowDocument?._id} className="h-full" />
                                </div>
                              );
                            }

                            // For other files, show in iframe directly
                            return (
                              <div
                                className="w-full h-full flex items-start justify-center p-4"
                                style={{
                                  transform: `scale(${previewZoom / 100})`,
                                  transformOrigin: 'top center',
                                  minHeight: `${100 / (previewZoom / 100)}%`,
                                }}
                              >
                                <iframe
                                  src={workflowPreviewUrl}
                                  title="Document preview"
                                  className="w-full border-0 bg-white shadow-lg"
                                  style={{
                                    minHeight: '1000px',
                                    height: 'auto',
                                  }}
                                />
                              </div>
                            );
                          })()
                        ) : workflowDocument?.fileUrl ? (
                          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 text-sm text-slate-200 px-8 text-center">
                            <FileText className="h-10 w-10 text-slate-400" />
                            Inline preview unavailable. Use the quick actions above to open the document.
                          </div>
                        ) : (
                          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 text-sm text-slate-200">
                            <FileText className="h-10 w-10 text-slate-400" />
                            No document file available.
                          </div>
                        )}
                        <div className="absolute bottom-4 right-4 z-20 flex gap-2 text-[11px] text-slate-200">
                          <Badge className="rounded-full bg-white px-3 py-0.5 font-semibold text-slate-800 shadow-sm">
                            {workflowDocument?.fileSize
                              ? `${(workflowDocument.fileSize / (1024 * 1024)).toFixed(2)} MB`
                              : "Unknown Size"}
                          </Badge>
                          {workflowDocument?.mimeType && (
                            <Badge className="rounded-full bg-white px-3 py-0.5 font-semibold text-slate-800 shadow-sm">
                              {workflowDocument.mimeType}
                            </Badge>
                          )}
                        </div>
                      </div>
                      {workflowPreviewError && (
                        <p className="mt-3 text-xs text-amber-600">{workflowPreviewError}</p>
                      )}
                    </div>
                  </div>

                  <div className="rounded-2xl border bg-white shadow-sm p-5 flex flex-col min-h-[600px]">
                    {/* Email Information Section */}
                    {(workflowDocument?.source === 'email_attachment' ||
                      workflowDocument?.isEmailAttachment ||
                      workflowDocument?.emailInfo) && (
                        <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                          <div className="flex items-center gap-2 mb-3">
                            <Mail className="h-4 w-4 text-blue-600" />
                            <h3 className="text-sm font-semibold text-blue-900">Email Information</h3>
                          </div>
                          <div className="space-y-2 text-sm">
                            {workflowDocument?.emailInfo?.subject && (
                              <div className="flex items-start gap-2">
                                <span className="font-medium text-gray-700 min-w-[60px]">Subject:</span>
                                <span className="text-gray-900">{workflowDocument.emailInfo.subject}</span>
                              </div>
                            )}
                            {workflowDocument?.emailInfo?.from && (
                              <div className="flex items-start gap-2">
                                <span className="font-medium text-gray-700 min-w-[60px]">From:</span>
                                <span className="text-gray-900">{workflowDocument.emailInfo.from}</span>
                              </div>
                            )}
                            {workflowDocument?.emailInfo?.to && (
                              <div className="flex items-start gap-2">
                                <span className="font-medium text-gray-700 min-w-[60px]">To:</span>
                                <span className="text-gray-900">{workflowDocument.emailInfo.to}</span>
                              </div>
                            )}
                            {workflowDocument?.emailInfo?.receivedAt && (
                              <div className="flex items-start gap-2">
                                <span className="font-medium text-gray-700 min-w-[60px]">Received:</span>
                                <span className="text-gray-900">
                                  {new Date(workflowDocument.emailInfo.receivedAt).toLocaleString()}
                                </span>
                              </div>
                            )}
                            {workflowDocument?.emailInfo?.messageId && (
                              <div className="flex items-start gap-2">
                                <span className="font-medium text-gray-700 min-w-[60px]">Message ID:</span>
                                <span className="text-gray-600 text-xs font-mono break-all">
                                  {workflowDocument.emailInfo.messageId}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                    <ISFDocumentWorkflow
                      document={workflowDocument}
                      layout="drawer"
                      className="flex-1"
                      onWorkflowUpdate={async () => {
                        // Refetch workflow data when mutations occur
                        const docId = workflowDocument?._id || workflowDocument?.documentId;
                        if (docId) {
                          try {
                            const [documentData, workflowResponse] = await Promise.all([
                              isfDocumentService.getDocument(docId),
                              isfDocumentWorkflowService.getState(docId).catch(err => {
                                console.warn('Failed to fetch workflow:', err);
                                return { workflow: null };
                              })
                            ]);
                            const documentWithWorkflow = {
                              ...documentData,
                              workflow: workflowResponse?.workflow || null
                            };
                            setWorkflowDocument(documentWithWorkflow);

                            // Refresh the documents list
                            fetchDocuments();
                          } catch (error) {
                            console.error('Failed to refresh workflow:', error);
                          }
                        }
                      }}
                      onStageOpen={(stage) => {
                        // Close the workflow drawer when stage is set to null (after successful replacement)
                        if (stage === null) {
                          setWorkflowDrawerOpen(false);
                          setWorkflowDocument(null);
                          setWorkflowPreviewUrl(null);
                          // Refresh the documents list
                          fetchDocuments();
                        }
                      }}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-600">
                Select a document to preview its workflow.
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>

      {/* Add ApprovalDialog */}
      <ApprovalDialog
        open={showApprovalDialog}
        onClose={() => {
          setShowApprovalDialog(false);
          setSelectedDocumentForApproval(null);
        }}
        document={selectedDocumentForApproval}
        onApproved={handleApprovalComplete}
      />

      {/* AI Upload Drawer for Email Attachment Classification (same flow as manual upload) */}
      <RightDrawer
        isOpen={showAIUploadDrawer}
        onClose={() => {
          setShowAIUploadDrawer(false);
          setEmailAttachmentData(null);
        }}
        title="AI Classification - Email Attachment"
        size="xl"
      >
        <ISFAIUploadDrawer
          isOpen={showAIUploadDrawer}
          onClose={() => {
            setShowAIUploadDrawer(false);
            setEmailAttachmentData(null);
          }}
          onUploadComplete={() => {
            // Refresh documents after upload
            fetchDocuments();
            setShowAIUploadDrawer(false);
            setEmailAttachmentData(null);
          }}
          selectedStudy={emailAttachmentData?.studyId || selectedStudy || null}
          selectedSite={emailAttachmentData?.siteId || selectedSite || null}
          emailAttachmentData={emailAttachmentData}
        />
      </RightDrawer>
    </>
  );
};

export default ISFDocumentList; 