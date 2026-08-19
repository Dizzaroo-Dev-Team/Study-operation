import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useToast } from '@/components/ui/use-toast';
import ISFAssignmentDialog from '@/components/dialogs/ISFAssignmentDialog';

import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from "@/components/ui/table";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    DropdownMenu,
    DropdownMenuCheckboxItem,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
    Search,
    Download,
    FileText,
    Calendar,
    Building,
    Globe,
    MapPin,
    Clock,
    CheckCircle,
    XCircle,
    AlertCircle,
    MoreHorizontal,
    Filter,
    RefreshCw,
    Eye,
    History,
    MessageSquare,
    Bookmark,
    Settings,
    Copy,
    X,
    FolderTree,
    Minimize2,
    Maximize2,
    Maximize,
    Minimize,
    Printer,
    ZoomIn,
    ZoomOut,
    MoreVertical,
    Link as LinkIcon,
    ArrowLeft,
    ChevronLeft,
    ChevronRight,
    GitBranch,
    Loader2,
    ArrowUpDown,
    ArrowUp,
    ArrowDown,
} from 'lucide-react';
import RightDrawer from '@/components/ui/right-drawer';
import ISFAIUploadDrawer from '@/components/ai/ISFAIUploadDrawer';
import { SimpleTooltip } from "@/components/ui/tooltip";
import isfDocumentService from '@/services/isfDocument.service';
import DocxPreview from '@/components/documents/DocxPreview';
import useTmfHierarchy from '../../hooks/useTmfHierarchy';
import { normalizeTMF } from '@/utils/tmfHierarchyUtils';

// Status badge component
const StatusBadge = ({ status, type = 'status' }) => {
    const getStatusConfig = () => {
        if (type === 'status') {
            // Always use the actual document status from the API
            switch (status) {
                case 'APPROVED':
                    return { variant: 'default', className: 'bg-green-100 text-green-800 border-green-200', icon: CheckCircle, label: 'APPROVED' };
                case 'ARCHIVED':
                    return { variant: 'secondary', className: 'bg-slate-100 text-slate-800 border-slate-200', icon: FileText, label: 'ARCHIVED' };
                case 'EXPIRED':
                    return { variant: 'destructive', className: 'bg-red-100 text-red-800 border-red-200', icon: XCircle, label: 'EXPIRED' };
                case 'PENDING_APPROVAL':
                    return { variant: 'secondary', className: 'bg-yellow-100 text-yellow-800 border-yellow-200', icon: Clock, label: 'PENDING APPROVAL' };
                case 'REJECTED':
                    return { variant: 'destructive', className: 'bg-red-100 text-red-800 border-red-200', icon: XCircle, label: 'REJECTED' };
                case 'IN_REVIEW':
                    return { variant: 'secondary', className: 'bg-blue-100 text-blue-800 border-blue-200', icon: AlertCircle, label: 'IN REVIEW' };
                case 'IN_QC':
                    return { variant: 'secondary', className: 'bg-purple-100 text-purple-800 border-purple-200', icon: AlertCircle, label: 'IN QC' };
                case 'DRAFT':
                    return { variant: 'outline', className: 'bg-gray-100 text-gray-800 border-gray-200', icon: FileText, label: 'DRAFT' };
                case 'RETIRED':
                    return { variant: 'secondary', className: 'bg-amber-100 text-amber-800 border-amber-200', icon: AlertCircle, label: 'RETIRED' };
                default:
                    return { variant: 'outline', className: 'bg-gray-100 text-gray-600 border-gray-200', icon: FileText, label: status?.replace(/_/g, ' ') || 'N/A' };
            }
        }

        return { variant: 'outline', className: 'bg-gray-100 text-gray-600 border-gray-200', icon: FileText, label: status?.replace(/_/g, ' ') || 'N/A' };
    };

    const config = getStatusConfig();
    const IconComponent = config.icon;

    return (
        <Badge
            variant={config.variant}
            className={cn("inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs font-medium border", config.className)}
        >
            <IconComponent className="w-2.5 h-2.5" />
            {config.label || status?.replace(/_/g, ' ') || 'N/A'}
        </Badge>
    );
};

// Enhanced document type icon
const DocumentTypeIcon = ({ type }) => {
    const getIcon = () => {
        switch (type) {
            case 'PROTOCOL':
                return <FileText className="w-3.5 h-3.5 text-blue-600" />;
            case 'INVESTIGATOR_BROCHURE':
                return <FileText className="w-3.5 h-3.5 text-purple-600" />;
            case 'INFORMED_CONSENT':
                return <FileText className="w-3.5 h-3.5 text-green-600" />;
            case 'REGULATORY_DOCUMENT':
                return <FileText className="w-3.5 h-3.5 text-orange-600" />;
            case 'CLINICAL_REPORT':
                return <FileText className="w-3.5 h-3.5 text-red-600" />;
            case 'SAFETY_REPORT':
                return <FileText className="w-3.5 h-3.5 text-yellow-600" />;
            default:
                return <FileText className="w-3.5 h-3.5 text-gray-600" />;
        }
    };

    return getIcon();
};

const ContentArea = ({ selectedItem, selectedStudy, refreshTrigger = 0 }) => {
    const { toast } = useToast();
    const { hierarchyData } = useTmfHierarchy();

    const [documents, setDocuments] = useState([]);
    const [globalFilter, setGlobalFilter] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
    const [advancedFilters, setAdvancedFilters] = useState({
        status: [],
        documentType: [],
        dateRange: { from: null, to: null },
        study: [],
        country: [],
        site: []
    });
    const [previewDocument, setPreviewDocument] = useState(null);
    const [showPreview, setShowPreview] = useState(false);
    const [presignedUrl, setPresignedUrl] = useState(null);
    const [isPreviewMinimized, setIsPreviewMinimized] = useState(false);
    const [isPreviewFullscreen, setIsPreviewFullscreen] = useState(false);
    const [zoomLevel, setZoomLevel] = useState(100);
    const [isDetailsCollapsed, setIsDetailsCollapsed] = useState(false);
    const [showAIUploadDrawer, setShowAIUploadDrawer] = useState(false);
    const [selectedDocuments, setSelectedDocuments] = useState([]);
    const [showSendToWorkflowDialog, setShowSendToWorkflowDialog] = useState(false);
    const [documentToSendToWorkflow, setDocumentToSendToWorkflow] = useState(null);
    const [isSendingToWorkflow, setIsSendingToWorkflow] = useState(false);
    const [showISFAssignmentDialog, setShowISFAssignmentDialog] = useState(false);
    const [documentForISFAssignment, setDocumentForISFAssignment] = useState(null);
    const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

    // Handle sort function
    const handleSort = (key) => {
        let direction = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        }
        setSortConfig({ key, direction });
    };

    const SortIcon = ({ columnKey }) => {
        if (sortConfig.key !== columnKey) {
            return <ArrowUpDown className="w-3 h-3 ml-auto text-gray-300" />;
        }
        return sortConfig.direction === 'asc' ?
            <ArrowUp className="w-3 h-3 ml-auto text-blue-600" /> :
            <ArrowDown className="w-3 h-3 ml-auto text-blue-600" />;
    };

    // Fetch documents function (Approved Documents view: only APPROVED, optional study filter)
    const fetchDocuments = useCallback(async () => {
        setIsLoading(true);
        try {
            const response = await isfDocumentService.getAllDocuments({
                isfViewer: true,
                status: 'APPROVED',
                study: selectedStudy || undefined,
                limit: 1000
            });

            let fetchedDocuments = Array.isArray(response) ? response : [];
            setDocuments(fetchedDocuments);
        } catch (error) {
            console.error('Error fetching documents:', error);
            setDocuments([]);
        } finally {
            setIsLoading(false);
        }
    }, [selectedStudy]);

    // Fetch documents on mount and when selectedStudy changes
    useEffect(() => {
        fetchDocuments();
    }, [fetchDocuments, selectedStudy]); // Only re-fetch when selectedStudy changes, not when selectedItem changes

    useEffect(() => {
        if (refreshTrigger > 0) {
            fetchDocuments();
        }
    }, [refreshTrigger, fetchDocuments]);

    // NOTE: We no longer auto-open preview when a document is selected from the sidebar.
    // This prevents implicit calls to the presign endpoint that can trigger automatic downloads
    // in some browsers. Preview is now opened only via explicit user actions (table row click, menu).

    // Resolve TMF display names from tmfReference + hierarchyData (used for table display and sub-artifact filter)
    const getTmfDisplayForDoc = useCallback((doc) => {
        const out = { zoneName: null, sectionName: null, artifactName: null, subArtifactName: null };
        if (!doc) return out;
        const tmfRef = doc.tmfReference ?? doc.tmf_reference;
        const parts = tmfRef ? tmfRef.split('.').map((p) => String(parseInt(p, 10) || p).padStart(2, '0')) : [];
        const isId = (v) => typeof v === 'string' && /^[0-9a-fA-F]{24}$/.test(v);
        const hasName = (obj) => obj && typeof obj === 'object' && (obj.zoneName || obj.sectionName || obj.artifactName || obj.subArtifactName);

        if (doc.zone && hasName(doc.zone)) {
            out.zoneName = (doc.zone.zoneName || '').trim() || null;
        } else if (tmfRef && (isId(doc.zone) || !doc.zone) && parts.length >= 1) {
            const z = parts[0];
            const zoneInfo = hierarchyData?.find((zd) => normalizeTMF(zd.Zone?.Number) === z);
            out.zoneName = zoneInfo?.Zone?.Name || null;
        }

        if (doc.section && hasName(doc.section)) {
            out.sectionName = (doc.section.sectionName || '').trim() || null;
        } else if (tmfRef && (isId(doc.section) || !doc.section) && parts.length >= 2) {
            const z = parts[0], s = parts[1];
            const zoneInfo = hierarchyData?.find((zd) => normalizeTMF(zd.Zone?.Number) === z);
            const sectionInfo = zoneInfo?.Sections?.find((sec) => normalizeTMF(sec.Section?.Number) === normalizeTMF(`${z}.${s}`));
            out.sectionName = sectionInfo?.Section?.Name || null;
        }

        if (doc.artifact && hasName(doc.artifact)) {
            out.artifactName = (doc.artifact.artifactName || doc.artifact.artifactNumber || '').trim() || null;
        } else if (doc.artifactName) {
            out.artifactName = doc.artifactName;
        } else if (tmfRef && (isId(doc.artifact) || !doc.artifact) && parts.length >= 3) {
            const z = parts[0], s = parts[1], a = parts[2];
            const zoneInfo = hierarchyData?.find((zd) => normalizeTMF(zd.Zone?.Number) === z);
            const sectionInfo = zoneInfo?.Sections?.find((sec) => normalizeTMF(sec.Section?.Number) === normalizeTMF(`${z}.${s}`));
            const artInfo = sectionInfo?.Artifacts?.find((art) => normalizeTMF(art.Artifact?.Number) === normalizeTMF(`${z}.${s}.${a}`));
            out.artifactName = artInfo?.Artifact?.Name || null;
        }

        const subObj = doc.subArtifact ?? doc.sub_artifact;
        if (subObj && typeof subObj === 'object' && subObj.subArtifactName) {
            out.subArtifactName = subObj.subArtifactName;
        } else if (doc.subArtifactName) {
            out.subArtifactName = doc.subArtifactName;
        } else if (tmfRef && parts.length >= 3) {
            const z = parts[0], s = parts[1], a = parts[2];
            const zoneInfo = hierarchyData?.find((zd) => normalizeTMF(zd.Zone?.Number) === z);
            const sectionInfo = zoneInfo?.Sections?.find((sec) => normalizeTMF(sec.Section?.Number) === normalizeTMF(`${z}.${s}`));
            const artInfo = sectionInfo?.Artifacts?.find((art) => normalizeTMF(art.Artifact?.Number) === normalizeTMF(`${z}.${s}.${a}`));
            const subArtifacts = artInfo?.SubArtifacts || [];
            out.subArtifactName = subArtifacts.length > 0 ? subArtifacts[0].Name : null;
        }
        return out;
    }, [hierarchyData]);

    // Helper function to check if document workflow is completed
    // This includes DRAFT documents if their workflow is completed
    const isWorkflowCompleted = (doc) => {
        const workflow = doc.workflow || {};

        // Check workflow lifecycle state - completed states (includes DRAFT with completed workflow)
        const lifecycleState = workflow.lifecycleState;
        const completedLifecycleStates = ['ACTIVATION', 'MONITORING', 'ARCHIVED'];
        if (completedLifecycleStates.includes(lifecycleState)) {
            return true;
        }

        // Check if both review and approval workflows are completed (includes DRAFT documents)
        const reviewCompleted = workflow.review?.overallStatus === 'COMPLETED';
        const approvalCompleted = workflow.approval?.overallStatus === 'COMPLETED';
        if (reviewCompleted && approvalCompleted) {
            return true;
        }

        // Check if all review stages are completed
        const reviewStages = workflow.review?.stages || [];
        const allReviewStagesCompleted = reviewStages.length > 0 &&
            reviewStages.every(stage => stage.status === 'COMPLETED');

        // Check if all approval stages are completed
        const approvalStages = workflow.approval?.stages || [];
        const allApprovalStagesCompleted = approvalStages.length > 0 &&
            approvalStages.every(stage => stage.status === 'COMPLETED');

        if (allReviewStagesCompleted && allApprovalStagesCompleted) {
            return true;
        }

        // Check document status - completed statuses (as a fallback, but workflow completion takes priority)
        const completedStatuses = ['APPROVED', 'FINAL', 'ARCHIVED', 'RETIRED'];
        if (completedStatuses.includes(doc.status)) {
            return true;
        }

        return false;
    };

    // Filter documents based on selected study, selected item, global search, and advanced filters
    const filteredDocuments = useMemo(() => {
        let result = documents;

        // Filter to show only documents with completed workflows
        result = result.filter(doc => isWorkflowCompleted(doc));

        // First, filter by selected study (if provided)
        if (selectedStudy) {
            result = result.filter(doc => {
                // doc.study can be a string (studyId/ObjectId) or an object with _id
                const docStudy = typeof doc.study === 'object' && doc.study !== null ? (doc.study._id || doc.study.id || doc.study.studyId) : doc.study;
                return docStudy && String(docStudy) === String(selectedStudy);
            });
        }

        // First, filter by selected item (document, zone, section, etc.)
        if (selectedItem) {
            const { type, item } = selectedItem;

            result = result.filter(doc => {
                // Determine document's hierarchy values with fallbacks to tmfReference
                let docZoneNum = doc.zone?.zoneNumber || doc.zoneNumber;
                let docSectionNum = doc.section?.sectionNumber || doc.sectionNumber;
                let docArtifactNum = doc.artifact?.artifactNumber || doc.artifactNumber;
                let docSubArtifactName = (doc.subArtifact?.subArtifactName || doc.subArtifactName || '').toLowerCase();

                // If values are missing, try to derive from tmfReference (e.g., "02.01.01")
                if (doc.tmfReference && (!docZoneNum || !docSectionNum || !docArtifactNum)) {
                    const parts = doc.tmfReference.split('.');
                    if (parts.length >= 1 && !docZoneNum) {
                        docZoneNum = String(parseInt(parts[0], 10));
                    }
                    if (parts.length >= 2 && !docSectionNum) {
                        const z = parts[0].padStart(2, '0');
                        const s = parts[1].padStart(2, '0');
                        docSectionNum = `${z}.${s}`;
                    }
                    if (parts.length >= 3 && !docArtifactNum) {
                        const z = parts[0].padStart(2, '0');
                        const s = parts[1].padStart(2, '0');
                        const a = parts[2].padStart(2, '0');
                        docArtifactNum = `${z}.${s}.${a}`;
                    }
                }

                // Normalize for comparison
                const normalizedDocZone = docZoneNum ? String(Number(docZoneNum)) : null;
                const normalizedDocSection = docSectionNum ? String(docSectionNum) : null;
                const normalizedDocArtifact = docArtifactNum ? String(docArtifactNum) : null;

                // Name match helpers
                const isMatch = (val1, val2) => {
                    if (!val1 || !val2) return false;
                    return String(val1).trim().toLowerCase() === String(val2).trim().toLowerCase();
                };

                if (type === 'document') {
                    return item?._id ? doc._id === item._id : true;
                } else if (type === 'zone') {
                    // Try name match first, then number match
                    const targetName = item.zoneName || item.name;
                    const targetNumber = String(Number(item.zoneNumber));

                    if (targetName && doc.zoneName) {
                        return isMatch(doc.zoneName, targetName);
                    }
                    return normalizedDocZone === targetNumber;
                } else if (type === 'section') {
                    const targetName = item.sectionName || item.name;
                    const targetNumber = String(item.sectionNumber);
                    const targetZoneNum = item.zone?.zoneNumber ? String(Number(item.zone.zoneNumber)) : null;
                    const targetZoneName = item.zone?.zoneName;

                    // Match Zone first
                    let zoneMatch = true;
                    if (targetZoneName && doc.zoneName) {
                        zoneMatch = isMatch(doc.zoneName, targetZoneName);
                    } else if (targetZoneNum) {
                        zoneMatch = normalizedDocZone === targetZoneNum;
                    }

                    if (!zoneMatch) return false;

                    // Match Section
                    if (targetName && doc.sectionName) {
                        return isMatch(doc.sectionName, targetName);
                    }
                    return normalizedDocSection === targetNumber;
                } else if (type === 'artifact') {
                    const targetName = item.artifactName || item.name;
                    const targetNumber = String(item.artifactNumber);
                    const targetSectionName = item.section?.sectionName;
                    const targetZoneName = item.zone?.zoneName;

                    // Match Zone & Section parent first
                    if (targetZoneName && doc.zoneName && !isMatch(doc.zoneName, targetZoneName)) return false;
                    if (targetSectionName && doc.sectionName && !isMatch(doc.sectionName, targetSectionName)) return false;

                    // Match Artifact
                    if (targetName && doc.artifactName) {
                        return isMatch(doc.artifactName, targetName);
                    }
                    return normalizedDocArtifact === targetNumber;
                } else if (type === 'subArtifact') {
                    const targetSubName = (item.subArtifactName || item.subArtifact?.subArtifactName || item.name || '').trim().toLowerCase();
                    if (!targetSubName) return false;

                    // Resolve document's sub-artifact name (API often returns sub_artifact as ID, so use hierarchy when missing)
                    const resolved = getTmfDisplayForDoc(doc);
                    const docSubName = (docSubArtifactName || (resolved.subArtifactName || '').toLowerCase()).trim();

                    // Match parent hierarchy: by name when available, else by number (zone/section/artifact)
                    const targetZoneNum = item.zone?.zoneNumber != null ? String(Number(item.zone.zoneNumber)) : null;
                    const targetSectionNum = item.section?.sectionNumber != null ? String(item.section.sectionNumber).split('.').map(p => String(parseInt(p, 10) || p).padStart(2, '0')).join('.') : null;
                    const targetArtifactNum = item.artifact?.artifactNumber != null ? String(item.artifact.artifactNumber) : null;
                    const targetZoneName = item.zone?.zoneName;
                    const targetSectionName = item.section?.sectionName;
                    const targetArtifactName = item.artifact?.artifactName;

                    if (targetZoneNum) {
                        if (normalizedDocZone !== targetZoneNum) return false;
                    } else if (targetZoneName && (doc.zoneName || resolved.zoneName) && !isMatch(doc.zoneName || resolved.zoneName, targetZoneName)) return false;

                    if (targetSectionNum) {
                        if (normalizedDocSection !== targetSectionNum) return false;
                    } else if (targetSectionName && (doc.sectionName || resolved.sectionName) && !isMatch(doc.sectionName || resolved.sectionName, targetSectionName)) return false;

                    if (targetArtifactNum) {
                        if (normalizedDocArtifact !== targetArtifactNum) return false;
                    } else if (targetArtifactName && (doc.artifactName || resolved.artifactName) && !isMatch(doc.artifactName || resolved.artifactName, targetArtifactName)) return false;

                    // Match Sub-Artifact by name (include docs with resolved name from tmfReference when API returns ID)
                    return docSubName && isMatch(docSubName, targetSubName);
                }
                return true;
            });
        }

        // Apply global search filter
        if (globalFilter) {
            const searchLower = globalFilter.toLowerCase();
            result = result.filter(doc =>
                doc.title?.toLowerCase().includes(searchLower) ||
                doc.description?.toLowerCase().includes(searchLower) ||
                doc.documentId?.toLowerCase().includes(searchLower) ||
                doc.tmfReference?.toLowerCase().includes(searchLower) ||
                doc.documentType?.toLowerCase().includes(searchLower)
            );
        }

        // Apply advanced filters
        // Filter by status
        if (advancedFilters.status && advancedFilters.status.length > 0) {
            result = result.filter(doc => advancedFilters.status.includes(doc.status));
        }

        // Filter by document type
        if (advancedFilters.documentType && advancedFilters.documentType.length > 0) {
            result = result.filter(doc => advancedFilters.documentType.includes(doc.documentType));
        }

        // Filter by country
        if (advancedFilters.country && advancedFilters.country.length > 0) {
            result = result.filter(doc => advancedFilters.country.includes(doc.country));
        }

        // Filter by site
        if (advancedFilters.site && advancedFilters.site.length > 0) {
            result = result.filter(doc => advancedFilters.site.includes(doc.site));
        }

        return result;
    }, [documents, selectedItem, globalFilter, advancedFilters, selectedStudy, getTmfDisplayForDoc]);

    // Apply sorting
    const displayByDocId = useMemo(() => {
        const m = {};
        filteredDocuments.forEach((doc) => {
            m[doc._id] = getTmfDisplayForDoc(doc);
        });
        return m;
    }, [filteredDocuments, getTmfDisplayForDoc]);

    const sortedDocuments = useMemo(() => {
        let sortableItems = [...filteredDocuments];
        if (sortConfig.key !== null) {
            sortableItems.sort((a, b) => {
                let aValue, bValue;
                const dispA = getTmfDisplayForDoc(a);
                const dispB = getTmfDisplayForDoc(b);

                // Handle nested objects or special fields (use resolved display names when API returns IDs)
                if (sortConfig.key === 'artifact') {
                    aValue = dispA.artifactName || a.artifact?.artifactName || '';
                    bValue = dispB.artifactName || b.artifact?.artifactName || '';
                } else if (sortConfig.key === 'subArtifact') {
                    aValue = dispA.subArtifactName || a.subArtifact?.subArtifactName || '';
                    bValue = dispB.subArtifactName || b.subArtifact?.subArtifactName || '';
                } else if (sortConfig.key === 'date') {
                    // Use creationDate for sorting by date
                    aValue = a.creationDate ? new Date(a.creationDate).getTime() : 0;
                    bValue = b.creationDate ? new Date(b.creationDate).getTime() : 0;
                } else {
                    aValue = a[sortConfig.key] || '';
                    bValue = b[sortConfig.key] || '';
                }

                // String comparison
                if (typeof aValue === 'string') aValue = aValue.toLowerCase();
                if (typeof bValue === 'string') bValue = bValue.toLowerCase();

                if (aValue < bValue) {
                    return sortConfig.direction === 'asc' ? -1 : 1;
                }
                if (aValue > bValue) {
                    return sortConfig.direction === 'asc' ? 1 : -1;
                }
                return 0;
            });
        }
        return sortableItems;
    }, [filteredDocuments, sortConfig, getTmfDisplayForDoc]);

    // Document selection handlers
    const handleSelectDocument = (documentId, checked) => {
        if (checked) {
            setSelectedDocuments(prev => [...prev, documentId]);
        } else {
            setSelectedDocuments(prev => prev.filter(id => id !== documentId));
        }
    };

    const handleSelectAll = useCallback(() => {
        if (selectedDocuments.length === filteredDocuments.length) {
            setSelectedDocuments([]);
        } else {
            setSelectedDocuments(filteredDocuments.map(doc => doc._id));
        }
    }, [selectedDocuments.length, filteredDocuments]);

    // Additional handler functions for enhanced actions
    const handleViewDetails = useCallback((document) => {
        setPreviewDocument(document);
        setShowPreview(true);
    }, []);

    // Limit display to prevent performance issues with large datasets
    // With virtualization enabled via conditional rendering, only 100 items shown at once
    const displayLimit = 1000;
    const displayedDocuments = sortedDocuments.length > displayLimit
        ? sortedDocuments.slice(0, displayLimit)
        : sortedDocuments;

    // Global search filter function
    const handleGlobalFilter = (value) => {
        setGlobalFilter(value);
    };

    const handleRowClick = (documentId) => {
        const doc = documents.find(d => d._id === documentId || d.documentId === documentId);
        if (doc) {
            setPreviewDocument(doc);
            setShowPreview(true);
        }
    };

    const refreshData = useCallback(() => {
        // Trigger a refresh of the data
        fetchDocuments();
    }, [fetchDocuments]);

    // Load presigned URL for dialog preview
    useEffect(() => {
        let mounted = true;
        const load = async () => {
            try {
                if (showPreview && previewDocument) {
                    const docId = previewDocument?._id || previewDocument?.id || previewDocument?.documentId;
                    if (!docId) return;
                    const url = await isfDocumentService.getPresignedUrl(docId);
                    if (mounted) setPresignedUrl(url || null);
                } else {
                    setPresignedUrl(null);
                }
            } catch (e) {
                console.error('Failed to presign preview URL', e);
                if (mounted) setPresignedUrl(null);
            }
        };
        load();
        return () => { mounted = false; };
    }, [showPreview, previewDocument]);


    // Handle keyboard shortcuts for preview
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (!showPreview) return;

            // Escape to close preview or exit fullscreen
            if (e.key === 'Escape') {
                if (isPreviewFullscreen) {
                    setIsPreviewFullscreen(false);
                } else {
                    setShowPreview(false);
                    setIsPreviewMinimized(false);
                    setIsPreviewFullscreen(false);
                    setZoomLevel(100);
                }
            }

            // F11 for fullscreen (prevent default browser behavior when in preview)
            if (e.key === 'F11' && showPreview) {
                e.preventDefault();
                setIsPreviewFullscreen(!isPreviewFullscreen);
                if (isPreviewMinimized) setIsPreviewMinimized(false);
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [showPreview, isPreviewFullscreen, isPreviewMinimized]);

    // Advanced features helper functions
    const handleAdvancedFilterChange = (filterType, value) => {
        setAdvancedFilters(prev => ({
            ...prev,
            [filterType]: value
        }));
    };

    const handleSendToWorkflow = useCallback((document) => {
        if (!document?._id) {
            toast({
                title: "Error",
                description: "Document ID is missing",
                variant: "destructive"
            });
            return;
        }

        // Set document and show confirmation dialog
        setDocumentToSendToWorkflow(document);
        setShowSendToWorkflowDialog(true);
    }, [toast]);

    const confirmSendToWorkflow = useCallback(async () => {
        if (!documentToSendToWorkflow?._id) {
            return;
        }

        setIsSendingToWorkflow(true);
        try {
            const workflowService = (await import("@/services/documentWorkflow.service")).default;
            await workflowService.resetToDraft(documentToSendToWorkflow._id, 'Sent back to workflow from ISF viewer');

            toast({
                title: "Success",
                description: "Document has been sent back to workflow. Status changed to DRAFT.",
            });

            // Close dialog and reset state
            setShowSendToWorkflowDialog(false);
            setDocumentToSendToWorkflow(null);

            // Refresh documents list
            fetchDocuments();
        } catch (error) {
            console.error('Error sending document to workflow:', error);
            toast({
                title: "Error",
                description: error.response?.data?.error || error.message || "Failed to send document to workflow",
                variant: "destructive"
            });
        } finally {
            setIsSendingToWorkflow(false);
        }
    }, [documentToSendToWorkflow, toast, fetchDocuments]);

    const handleCopy = (document) => {
        navigator.clipboard.writeText(`${window.location.origin}/isf-viewer/document/${document.documentId}`);
        // Show toast notification
    };


    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch (e.key) {
                    case 'f':
                        e.preventDefault();
                        document.querySelector('input[placeholder*="Search"]')?.focus();
                        break;
                    case 'a': {
                        e.preventDefault();
                        handleSelectAll();
                        break;
                    }
                    case 'e':
                        e.preventDefault();
                        // Export functionality would go here
                        break;
                }
            }
        };

        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [filteredDocuments, handleSelectAll]);

    return (
        <div className="h-full w-full flex flex-col overflow-hidden">
            <Card className="h-full w-full flex flex-col shadow-lg border-0 bg-white overflow-hidden">
                {!showPreview && (
                    <CardHeader className="flex-none bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-gray-200 py-2 px-4 flex-shrink-0">
                        <div className="flex items-center justify-between gap-4">
                            <div className="flex items-center gap-3 min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                    <FileText className="w-4 h-4 text-blue-600 flex-shrink-0" />
                                    <CardTitle className="text-base font-semibold text-gray-900">
                                        ISF Repository
                                    </CardTitle>
                                </div>
                                {selectedItem && (
                                    <CardDescription className="text-xs text-gray-600 truncate">
                                        {selectedItem?.type === 'document' && selectedItem?.data
                                            ? `Add new document to: ${selectedItem.data.zoneName || 'Unknown Zone'}`
                                            : selectedItem?.type === 'document' && selectedItem?.item?._id
                                                ? `Selected: ${selectedItem.item?.title || selectedItem.item?.documentTitle || 'Untitled Document'}`
                                                : selectedItem
                                                    ? `Documents associated with ${selectedItem.type}: ${selectedItem.item?.name || selectedItem.item?.zoneName || selectedItem.item?.sectionName || selectedItem.item?.artifactName || 'Unknown'}`
                                                    : 'All Documents'}
                                    </CardDescription>
                                )}
                            </div>
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                                <SimpleTooltip content="Refresh documents">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={refreshData}
                                        className="h-7 w-7"
                                    >
                                        <RefreshCw className={cn("w-3.5 h-3.5", isLoading && "animate-spin")} />
                                    </Button>
                                </SimpleTooltip>
                            </div>
                        </div>
                    </CardHeader>
                )}
                <CardContent className="flex-1 flex flex-col min-h-0 overflow-hidden p-3">
                    {/* Enhanced Search and Filters */}
                    {!showPreview && (
                        <div className="flex-none flex items-center gap-2 mb-3 flex-shrink-0">
                            <div className="relative flex-1 min-w-0">
                                <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                                <Input
                                    placeholder="Search documents..."
                                    value={globalFilter}
                                    onChange={(e) => handleGlobalFilter(e.target.value)}
                                    className="pl-8 pr-3 h-8 text-xs border-gray-300 focus:border-blue-500 focus:ring-blue-500"
                                />
                            </div>
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-8 px-2 text-xs"
                                onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                            >
                                <Filter className="w-3.5 h-3.5 mr-1" />
                                Filters
                            </Button>
                        </div>
                    )}

                    {/* Advanced Filters Panel */}
                    {!showPreview && showAdvancedFilters && (
                        <div className="flex-none bg-gray-50 p-2 rounded-lg mb-3 border">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
                                <div>
                                    <Label className="text-xs font-medium mb-1">Country</Label>
                                    <Select
                                        value={advancedFilters.country.join(',')}
                                        onValueChange={(value) => handleAdvancedFilterChange('country', value.split(','))}
                                    >
                                        <SelectTrigger className="h-8 text-xs">
                                            <SelectValue placeholder="Select country" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="US">United States</SelectItem>
                                            <SelectItem value="UK">United Kingdom</SelectItem>
                                            <SelectItem value="CA">Canada</SelectItem>
                                            <SelectItem value="AU">Australia</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div>
                                    <Label className="text-xs font-medium mb-1">Document Type</Label>
                                    <Select
                                        value={advancedFilters.documentType.join(',')}
                                        onValueChange={(value) => handleAdvancedFilterChange('documentType', value.split(','))}
                                    >
                                        <SelectTrigger className="h-8 text-xs">
                                            <SelectValue placeholder="Select type" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="PROTOCOL">Protocol</SelectItem>
                                            <SelectItem value="CLINICAL_REPORT">Clinical Report</SelectItem>
                                            <SelectItem value="INVESTIGATOR_BROCHURE">Investigator Brochure</SelectItem>
                                            <SelectItem value="INFORMED_CONSENT">Informed Consent</SelectItem>
                                            <SelectItem value="REGULATORY_DOCUMENT">Regulatory Document</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div>
                                    <Label className="text-xs font-medium mb-1">Status</Label>
                                    <Select
                                        value={advancedFilters.status.join(',')}
                                        onValueChange={(value) => handleAdvancedFilterChange('status', value.split(','))}
                                    >
                                        <SelectTrigger className="h-8 text-xs">
                                            <SelectValue placeholder="Select status" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="APPROVED">Approved</SelectItem>
                                            <SelectItem value="PENDING_APPROVAL">Pending</SelectItem>
                                            <SelectItem value="REJECTED">Rejected</SelectItem>
                                            <SelectItem value="IN_REVIEW">In Review</SelectItem>
                                            <SelectItem value="DRAFT">Draft</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div>
                                    <Label className="text-xs font-medium mb-1">Site</Label>
                                    <Select
                                        value={advancedFilters.site.join(',')}
                                        onValueChange={(value) => handleAdvancedFilterChange('site', value.split(','))}
                                    >
                                        <SelectTrigger className="h-8 text-xs">
                                            <SelectValue placeholder="Select site" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="SITE_101">Site 101</SelectItem>
                                            <SelectItem value="SITE_102">Site 102</SelectItem>
                                            <SelectItem value="SITE_103">Site 103</SelectItem>
                                            <SelectItem value="SITE_201">Site 201</SelectItem>
                                            <SelectItem value="SITE_202">Site 202</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                            <div className="flex justify-end">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => {
                                        setAdvancedFilters({
                                            status: [],
                                            documentType: [],
                                            dateRange: { from: null, to: null },
                                            study: [],
                                            country: [],
                                            site: []
                                        });
                                        setGlobalFilter('');
                                    }}
                                    className="h-7 px-2 text-xs text-gray-600 hover:text-gray-900 hover:bg-gray-100"
                                >
                                    <X className="w-3 h-3 mr-1" />
                                    Clear Filters
                                </Button>
                            </div>
                        </div>
                    )}

                    {/* Bulk Actions */}
                    {!showPreview && selectedDocuments.length > 0 && (
                        <div className="flex-none flex items-center justify-between p-2 bg-blue-50 border border-blue-200 rounded-lg mb-3">
                            <div className="flex items-center space-x-2">
                                <span className="text-sm font-medium text-blue-900">
                                    {selectedDocuments.length} document(s) selected
                                </span>
                            </div>
                            <div className="flex items-center space-x-2">
                                <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                        selectedDocuments.forEach(id => {
                                            const doc = documents.find(d => d._id === id);
                                            if (doc) window.open(doc.fileUrl, '_blank');
                                        });
                                    }}
                                    className="flex items-center space-x-1"
                                >
                                    <Download className="w-4 h-4" />
                                    <span>Download</span>
                                </Button>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => setSelectedDocuments([])}
                                >
                                    <X className="w-4 h-4" />
                                </Button>
                            </div>
                        </div>
                    )}

                    <div className="flex-1 min-h-0 overflow-hidden">
                        {showPreview ? (
                            <div className={cn(
                                "rounded-lg bg-white flex flex-col transition-all duration-300 overflow-hidden",
                                isPreviewMinimized ? "h-16" : isPreviewFullscreen ? "fixed inset-0 z-50 rounded-none" : "h-full"
                            )}>
                                {/* Preview Header */}
                                <div className="flex items-center justify-between h-10 px-2 border-b bg-slate-50 flex-shrink-0">
                                    <div className="flex items-center gap-2 min-w-0 flex-1">
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            onClick={() => {
                                                setShowPreview(false);
                                                setIsPreviewMinimized(false);
                                                setIsPreviewFullscreen(false);
                                                setZoomLevel(100);
                                            }}
                                            className="h-7 w-7 hover:bg-slate-100"
                                        >
                                            <ArrowLeft className="h-3.5 w-3.5" />
                                        </Button>
                                        <div className="text-sm font-medium truncate max-w-[40vw]">
                                            {previewDocument?.title || previewDocument?.documentTitle || 'Preview'}
                                        </div>
                                        {previewDocument?.status && (
                                            <StatusBadge status={previewDocument.status} type="status" />
                                        )}
                                    </div>
                                    {!isPreviewMinimized && (
                                        <div className="flex items-center gap-1">
                                            {/* Zoom Controls */}
                                            <div className="flex items-center gap-1 border-r pr-1 mr-1">
                                                <SimpleTooltip content={`Zoom Out (${zoomLevel - 25}%)`}>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        onClick={() => setZoomLevel(Math.max(25, zoomLevel - 25))}
                                                        className="h-7 w-7 hover:bg-slate-100"
                                                        disabled={zoomLevel <= 25}
                                                    >
                                                        <ZoomOut className="h-3.5 w-3.5" />
                                                    </Button>
                                                </SimpleTooltip>
                                                <span className="text-xs font-medium text-slate-600 min-w-[3rem] text-center">
                                                    {zoomLevel}%
                                                </span>
                                                <SimpleTooltip content={`Zoom In (${zoomLevel + 25}%)`}>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        onClick={() => setZoomLevel(Math.min(200, zoomLevel + 25))}
                                                        className="h-7 w-7 hover:bg-slate-100"
                                                        disabled={zoomLevel >= 200}
                                                    >
                                                        <ZoomIn className="h-3.5 w-3.5" />
                                                    </Button>
                                                </SimpleTooltip>
                                            </div>

                                            {/* Print */}
                                            <SimpleTooltip content="Print">
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    onClick={() => {
                                                        if (presignedUrl) {
                                                            window.open(presignedUrl, '_blank');
                                                            setTimeout(() => window.print(), 500);
                                                        }
                                                    }}
                                                    className="h-7 w-7 hover:bg-slate-100"
                                                >
                                                    <Printer className="h-3.5 w-3.5" />
                                                </Button>
                                            </SimpleTooltip>

                                            {/* Share/Copy Link */}
                                            <SimpleTooltip content="Copy link">
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    onClick={async () => {
                                                        try {
                                                            const docId = previewDocument?._id || previewDocument?.id || previewDocument?.documentId;
                                                            const url = `${window.location.origin}${window.location.pathname}?doc=${docId}`;
                                                            await navigator.clipboard.writeText(url);
                                                            toast({
                                                                title: "Link copied",
                                                                description: "Document link has been copied to clipboard",
                                                            });
                                                        } catch (e) {
                                                            console.error('Failed to copy link', e);
                                                            toast({
                                                                title: "Failed to copy link",
                                                                description: "Please try again",
                                                                variant: "destructive",
                                                            });
                                                        }
                                                    }}
                                                    className="h-7 w-7 hover:bg-slate-100"
                                                >
                                                    <LinkIcon className="h-3.5 w-3.5" />
                                                </Button>
                                            </SimpleTooltip>

                                            {/* Download */}
                                            <SimpleTooltip content="Download">
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    onClick={async () => {
                                                        try {
                                                            const docId = previewDocument?._id || previewDocument?.id || previewDocument?.documentId;
                                                            const url = await isfDocumentService.getPresignedUrl(docId);
                                                            if (url) {
                                                                const a = document.createElement('a');
                                                                a.href = url;
                                                                a.download = previewDocument?.title || 'document';
                                                                document.body.appendChild(a);
                                                                a.click();
                                                                document.body.removeChild(a);
                                                            }
                                                        } catch (e) {
                                                            console.error('Download failed', e);
                                                        }
                                                    }}
                                                    className="h-7 w-7 hover:bg-slate-100"
                                                >
                                                    <Download className="h-3.5 w-3.5" />
                                                </Button>
                                            </SimpleTooltip>

                                            {/* Minimize/Maximize */}
                                            <SimpleTooltip content={isPreviewMinimized ? "Restore" : "Minimize"}>
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    onClick={() => {
                                                        setIsPreviewMinimized(!isPreviewMinimized);
                                                        if (isPreviewFullscreen) setIsPreviewFullscreen(false);
                                                    }}
                                                    className="h-7 w-7 hover:bg-slate-100"
                                                >
                                                    {isPreviewMinimized ? <Maximize2 className="h-3.5 w-3.5" /> : <Minimize2 className="h-3.5 w-3.5" />}
                                                </Button>
                                            </SimpleTooltip>

                                            {/* Fullscreen */}
                                            <SimpleTooltip content={isPreviewFullscreen ? "Exit fullscreen" : "Fullscreen"}>
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    onClick={() => {
                                                        setIsPreviewFullscreen(!isPreviewFullscreen);
                                                        if (isPreviewMinimized) setIsPreviewMinimized(false);
                                                    }}
                                                    className="h-7 w-7 hover:bg-slate-100"
                                                >
                                                    {isPreviewFullscreen ? <Minimize className="h-3.5 w-3.5" /> : <Maximize className="h-3.5 w-3.5" />}
                                                </Button>
                                            </SimpleTooltip>

                                            {/* More Actions */}
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        className="h-7 w-7 hover:bg-slate-100"
                                                    >
                                                        <MoreVertical className="h-3.5 w-3.5" />
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end">
                                                    <DropdownMenuItem onClick={() => handleViewDetails(previewDocument)}>
                                                        <Eye className="h-4 w-4 mr-2" />
                                                        View Details
                                                    </DropdownMenuItem>
                                                    <DropdownMenuItem onClick={() => handleCopy(previewDocument)}>
                                                        <Copy className="h-4 w-4 mr-2" />
                                                        Copy Link
                                                    </DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </div>
                                    )}
                                </div>

                                {/* Preview Content */}
                                {!isPreviewMinimized && (
                                    <div className="flex-1 overflow-hidden flex min-h-0">
                                        <div className="flex-[3] min-w-0 bg-white relative">
                                            {presignedUrl ? (
                                                (() => {
                                                    // Check if it's a PDF
                                                    const isPdf = previewDocument?.mimeType?.toLowerCase()?.includes('pdf') ||
                                                        previewDocument?.fileUrl?.toLowerCase()?.endsWith('.pdf') ||
                                                        presignedUrl?.toLowerCase()?.includes('.pdf');

                                                    // Check if it's an Office document (DOCX, DOC, XLSX, XLS, PPTX, PPT)
                                                    const mimeType = previewDocument?.mimeType?.toLowerCase() || '';
                                                    const fileUrl = previewDocument?.fileUrl?.toLowerCase() || '';
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
                                                        const googleViewerUrl = `https://docs.google.com/gview?url=${encodeURIComponent(presignedUrl)}&embedded=true`;
                                                        return (
                                                            <div className="h-full w-full overflow-auto" style={{ zoom: `${zoomLevel}%` }}>
                                                                <iframe
                                                                    src={googleViewerUrl}
                                                                    className="w-full h-full border-0"
                                                                    title="Document Preview"
                                                                    style={{ minHeight: '100%' }}
                                                                />
                                                            </div>
                                                        );
                                                    }

                                                    // For Office documents (DOCX, DOC), use client-side rendering via backend proxy
                                                    if (isOfficeDoc) {
                                                        return (
                                                            <div className="h-full w-full overflow-auto" style={{ zoom: `${zoomLevel}%` }}>
                                                                <DocxPreview documentId={previewDocument?._id} className="h-full" />
                                                            </div>
                                                        );
                                                    }

                                                    // For other files, show in iframe directly
                                                    return (
                                                        <div className="h-full w-full overflow-auto" style={{ zoom: `${zoomLevel}%` }}>
                                                            <iframe
                                                                src={presignedUrl}
                                                                className="w-full h-full border-0"
                                                                title="Document Preview"
                                                                style={{ minHeight: '100%' }}
                                                            />
                                                        </div>
                                                    );
                                                })()
                                            ) : (
                                                <div className="h-full w-full flex items-center justify-center text-sm text-slate-500">
                                                    <div className="flex flex-col items-center gap-2">
                                                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-slate-600"></div>
                                                        <span>Preparing preview…</span>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                        <div className={cn(
                                            "border-l bg-white flex flex-col min-w-0 transition-all duration-200",
                                            isDetailsCollapsed ? "w-7" : "w-[320px]"
                                        )}>
                                            <div className="px-2 py-2 border-b text-sm font-semibold bg-slate-50 flex items-center justify-between">
                                                <span className={isDetailsCollapsed ? "sr-only" : ""}>Details</span>
                                                <SimpleTooltip content={isDetailsCollapsed ? "Show details" : "Hide details"}>
                                                    <Button
                                                        size="icon"
                                                        variant="ghost"
                                                        onClick={() => setIsDetailsCollapsed(!isDetailsCollapsed)}
                                                        className="h-6 w-6 hover:bg-slate-100"
                                                    >
                                                        {isDetailsCollapsed ? (
                                                            <ChevronLeft className="h-3.5 w-3.5" />
                                                        ) : (
                                                            <ChevronRight className="h-3.5 w-3.5" />
                                                        )}
                                                    </Button>
                                                </SimpleTooltip>
                                            </div>
                                            {!isDetailsCollapsed && (
                                                <div className="p-3 overflow-auto space-y-3 flex-1">
                                                    <div className="grid grid-cols-2 gap-x-2 gap-y-2 text-xs">
                                                        <div className="text-slate-500">Zone</div>
                                                        <div className="text-sm font-medium truncate">{previewDocument?.zone?.zoneName || '—'}</div>
                                                        <div className="text-slate-500">Section</div>
                                                        <div className="text-sm font-medium truncate">{previewDocument?.section?.sectionName || '—'}</div>
                                                        <div className="text-slate-500">Artifact</div>
                                                        <div className="text-sm font-medium truncate">{displayByDocId[previewDocument?._id]?.artifactName ?? previewDocument?.artifact?.artifactName ?? '—'}</div>
                                                        <div className="text-slate-500">Sub-Artifact</div>
                                                        <div className="text-sm font-medium truncate">{displayByDocId[previewDocument?._id]?.subArtifactName ?? previewDocument?.subArtifact?.subArtifactName ?? '—'}</div>
                                                        <div className="text-slate-500">Status</div>
                                                        <div className="text-sm font-medium truncate">{previewDocument?.status || 'DRAFT'}</div>
                                                        <div className="text-slate-500">Version</div>
                                                        <div className="text-sm font-medium truncate">{previewDocument?.version || 1}</div>
                                                        <div className="text-slate-500">Doc Date</div>
                                                        <div className="text-sm font-medium truncate">{previewDocument?.documentDate ? new Date(previewDocument.documentDate).toLocaleDateString() : '—'}</div>
                                                        <div className="text-slate-500">Study</div>
                                                        <div className="text-sm font-medium truncate">{previewDocument?.study || '—'}</div>
                                                        <div className="text-slate-500">Country</div>
                                                        <div className="text-sm font-medium truncate">{previewDocument?.country ?? '—'}</div>
                                                        <div className="text-slate-500">Site</div>
                                                        <div className="text-sm font-medium truncate">{previewDocument?.site ?? '—'}</div>
                                                    </div>

                                                    {/* Comments Section */}
                                                    <div className="mt-4 pt-4 border-t">
                                                        <div className="flex items-center justify-between mb-2">
                                                            <h3 className="text-xs font-semibold text-slate-600 uppercase tracking-wider">Comments</h3>
                                                            <Button size="sm" variant="ghost" className="h-6 text-xs">
                                                                <MessageSquare className="h-3 w-3 mr-1" />
                                                                Add
                                                            </Button>
                                                        </div>
                                                        <div className="text-xs text-slate-500">No comments yet</div>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="h-full rounded-lg border border-gray-200 bg-white shadow-sm flex flex-col overflow-hidden">
                                <div className="overflow-auto flex-1 min-h-0">
                                    <Table>
                                        <TableHeader className="sticky top-0 bg-gray-50 z-10 border-b border-gray-200 shadow-sm">
                                            <TableRow className="hover:bg-transparent h-8 border-b border-gray-200">
                                                <TableHead className="w-[40px] px-3 py-2">
                                                    <Checkbox
                                                        checked={selectedDocuments.length === filteredDocuments.length && filteredDocuments.length > 0}
                                                        onCheckedChange={handleSelectAll}
                                                        className="border-gray-300 data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600 h-4 w-4"
                                                    />
                                                </TableHead>
                                                <TableHead
                                                    className="px-3 py-2 w-[240px] max-w-[240px] cursor-pointer hover:bg-gray-100 transition-colors"
                                                    onClick={() => handleSort('title')}
                                                >
                                                    <div className="flex items-center gap-1.5">
                                                        <FileText className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Title</span>
                                                        <SortIcon columnKey="title" />
                                                    </div>
                                                </TableHead>
                                                <TableHead className="px-2 py-2">
                                                    <div className="flex items-center gap-1.5">
                                                        <Settings className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Type</span>
                                                    </div>
                                                </TableHead>
                                                <TableHead
                                                    className="px-2 py-2 cursor-pointer hover:bg-gray-100 transition-colors"
                                                    onClick={() => handleSort('artifact')}
                                                >
                                                    <div className="flex items-center gap-1.5">
                                                        <Bookmark className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Artifact</span>
                                                        <SortIcon columnKey="artifact" />
                                                    </div>
                                                </TableHead>
                                                <TableHead
                                                    className="px-2 py-2 cursor-pointer hover:bg-gray-100 transition-colors"
                                                    onClick={() => handleSort('subArtifact')}
                                                >
                                                    <div className="flex items-center gap-1.5">
                                                        <Bookmark className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Sub-Artifact</span>
                                                        <SortIcon columnKey="subArtifact" />
                                                    </div>
                                                </TableHead>
                                                <TableHead className="px-2 py-2">
                                                    <div className="flex items-center gap-1.5">
                                                        <History className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Version</span>
                                                    </div>
                                                </TableHead>
                                                <TableHead
                                                    className="px-2 py-2 cursor-pointer hover:bg-gray-100 transition-colors"
                                                    onClick={() => handleSort('country')}
                                                >
                                                    <div className="flex items-center gap-1.5">
                                                        <Globe className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Country</span>
                                                        <SortIcon columnKey="country" />
                                                    </div>
                                                </TableHead>
                                                <TableHead
                                                    className="px-2 py-2 cursor-pointer hover:bg-gray-100 transition-colors"
                                                    onClick={() => handleSort('site')}
                                                >
                                                    <div className="flex items-center gap-1.5">
                                                        <MapPin className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Site</span>
                                                        <SortIcon columnKey="site" />
                                                    </div>
                                                </TableHead>
                                                <TableHead className="px-2 py-2">
                                                    <div className="flex items-center gap-1.5">
                                                        <CheckCircle className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Status</span>
                                                    </div>
                                                </TableHead>
                                                <TableHead
                                                    className="px-2 py-2 cursor-pointer hover:bg-gray-100 transition-colors"
                                                    onClick={() => handleSort('date')}
                                                >
                                                    <div className="flex items-center gap-1.5">
                                                        <Calendar className="w-3 h-3 text-gray-500" />
                                                        <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Date</span>
                                                        <SortIcon columnKey="date" />
                                                    </div>
                                                </TableHead>
                                                <TableHead className="text-right px-4 py-2 w-[100px]">
                                                    <span className="text-[10px] font-semibold text-gray-700 tracking-wide uppercase">Actions</span>
                                                </TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {isLoading ? (
                                                <TableRow>
                                                    <TableCell colSpan={11} className="text-center py-12">
                                                        <div className="flex flex-col items-center justify-center space-y-3">
                                                            <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-200 border-t-blue-600"></div>
                                                            <span className="text-sm text-gray-600 font-medium">Loading documents...</span>
                                                        </div>
                                                    </TableCell>
                                                </TableRow>
                                            ) : displayedDocuments?.length ? (
                                                <>
                                                    {displayedDocuments.map((document, index) => (
                                                        <TableRow
                                                            key={document._id}
                                                            className={cn(
                                                                "group transition-all duration-200 cursor-pointer border-b border-gray-200/50",
                                                                "hover:bg-blue-50/70 hover:shadow-sm hover:border-blue-200",
                                                                selectedDocuments.includes(document._id) && "bg-blue-50 border-blue-300",
                                                                index % 2 === 0 ? "bg-white" : "bg-gray-50/40"
                                                            )}
                                                            tabIndex={0}
                                                            aria-selected={selectedDocuments.includes(document._id)}
                                                            onClick={(e) => {
                                                                e.preventDefault();
                                                                e.stopPropagation();
                                                                handleRowClick(document.documentId);
                                                            }}
                                                        >
                                                            <TableCell className="py-2 px-3">
                                                                <Checkbox
                                                                    checked={selectedDocuments.includes(document._id)}
                                                                    onCheckedChange={(checked) => handleSelectDocument(document._id, checked)}
                                                                    onClick={(e) => e.stopPropagation()}
                                                                    className="border-gray-300 data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600 h-4 w-4"
                                                                />
                                                            </TableCell>
                                                            <TableCell className="py-2 px-3 w-[240px] max-w-[240px]">
                                                                <div className="flex items-start gap-1.5">
                                                                    <DocumentTypeIcon type={document.documentType} />
                                                                    <div className="flex flex-col min-w-0 flex-1 max-w-[210px]">
                                                                        <SimpleTooltip content={document.title}>
                                                                            <span className="text-xs font-semibold text-gray-900 truncate leading-tight block">
                                                                                {document.title || <span className="text-gray-400 italic">Untitled</span>}
                                                                            </span>
                                                                        </SimpleTooltip>
                                                                        {document.description && (
                                                                            <SimpleTooltip content={document.description}>
                                                                                <div className="text-[10px] text-gray-500 truncate leading-tight mt-0.5 block">
                                                                                    {document.description}
                                                                                </div>
                                                                            </SimpleTooltip>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2">
                                                                <Badge variant="outline" className="text-[10px] font-medium border-gray-200 text-gray-600 bg-gray-50 max-w-[100px] truncate block">
                                                                    {document.documentType?.replace(/_/g, ' ') || 'N/A'}
                                                                </Badge>
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2">
                                                                <span className="text-xs font-medium text-gray-800 truncate max-w-[120px] block leading-tight" title={displayByDocId[document._id]?.artifactName ?? document.artifact?.artifactName ?? 'N/A'}>
                                                                    {displayByDocId[document._id]?.artifactName ?? document.artifact?.artifactName ?? <span className="text-gray-400 italic text-[10px]">—</span>}
                                                                </span>
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2">
                                                                <span className="text-xs font-medium text-gray-800 truncate max-w-[120px] block leading-tight" title={displayByDocId[document._id]?.subArtifactName ?? document.subArtifact?.subArtifactName ?? 'N/A'}>
                                                                    {displayByDocId[document._id]?.subArtifactName ?? document.subArtifact?.subArtifactName ?? <span className="text-gray-400 italic text-[10px]">—</span>}
                                                                </span>
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2">
                                                                <Badge variant="secondary" className="text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200 h-5">
                                                                    v{document.version || '1'}
                                                                </Badge>
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2">
                                                                <span className="text-xs font-medium text-gray-800 truncate max-w-[70px] block" title={document.country ?? 'N/A'}>
                                                                    {document.country ?? <span className="text-gray-400 italic text-[10px]">—</span>}
                                                                </span>
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2">
                                                                <span className="text-xs font-medium text-gray-800 truncate max-w-[90px] block" title={document.site ?? 'N/A'}>
                                                                    {document.site ?? <span className="text-gray-400 italic text-[10px]">—</span>}
                                                                </span>
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2">
                                                                <StatusBadge
                                                                    status={document.status}
                                                                    type="status"
                                                                />
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2">
                                                                <span className="text-[10px] text-gray-600 font-medium whitespace-nowrap">
                                                                    {document.creationDate ? new Date(document.creationDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : <span className="text-gray-400 italic">—</span>}
                                                                </span>
                                                            </TableCell>
                                                            <TableCell className="text-right py-2 px-4">
                                                                <DropdownMenu>
                                                                    <DropdownMenuTrigger asChild>
                                                                        <Button
                                                                            variant="ghost"
                                                                            size="sm"
                                                                            onClick={(e) => e.stopPropagation()}
                                                                            className="h-8 w-8 p-0 hover:bg-gray-100 hover:text-gray-700 rounded-md transition-colors"
                                                                        >
                                                                            <MoreHorizontal className="w-4 h-4" />
                                                                        </Button>
                                                                    </DropdownMenuTrigger>
                                                                    <DropdownMenuContent align="end" className="w-48 shadow-lg border border-gray-200 rounded-lg">
                                                                        <DropdownMenuLabel className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 py-2">Actions</DropdownMenuLabel>
                                                                        <DropdownMenuItem
                                                                            onClick={async (e) => {
                                                                                e.stopPropagation();
                                                                                try {
                                                                                    const docId = document?._id || document?.id || document?.documentId;
                                                                                    const url = await isfDocumentService.getPresignedUrl(docId);
                                                                                    if (url) window.open(url, '_blank');
                                                                                } catch (err) {
                                                                                    console.error('Failed to open document', err);
                                                                                }
                                                                            }}
                                                                            className="text-sm px-3 py-2 cursor-pointer"
                                                                        >
                                                                            <Eye className="h-4 w-4 mr-2 text-gray-500" />
                                                                            Preview
                                                                        </DropdownMenuItem>
                                                                        <DropdownMenuItem
                                                                            onClick={async (e) => {
                                                                                e.stopPropagation();
                                                                                try {
                                                                                    const docId = document?._id || document?.id || document?.documentId;
                                                                                    const url = await isfDocumentService.getPresignedUrl(docId);
                                                                                    if (url) window.open(url, '_blank');
                                                                                } catch (err) {
                                                                                    console.error('Failed to download document', err);
                                                                                }
                                                                            }}
                                                                            className="text-sm px-3 py-2 cursor-pointer"
                                                                        >
                                                                            <Download className="h-4 w-4 mr-2 text-gray-500" />
                                                                            Download
                                                                        </DropdownMenuItem>
                                                                        <DropdownMenuSeparator className="bg-gray-200" />
                                                                        <DropdownMenuItem onClick={() => handleViewDetails(document)} className="text-sm px-3 py-2 cursor-pointer">
                                                                            <FileText className="h-4 w-4 mr-2 text-gray-500" />
                                                                            View Details
                                                                        </DropdownMenuItem>
                                                                        <DropdownMenuItem
                                                                            onSelect={(e) => {
                                                                                e.stopPropagation();
                                                                                handleSendToWorkflow(document);
                                                                            }}
                                                                            className="text-sm px-3 py-2 cursor-pointer text-blue-700 hover:text-blue-800 hover:bg-blue-50"
                                                                        >
                                                                            <GitBranch className="h-4 w-4 mr-2" />
                                                                            Send to Workflow
                                                                        </DropdownMenuItem>
                                                                        {(!document.zone || !document.section || !document.artifact) && (
                                                                            <DropdownMenuItem
                                                                                onSelect={(e) => {
                                                                                    e.stopPropagation();
                                                                                    setDocumentForISFAssignment(document);
                                                                                    setShowISFAssignmentDialog(true);
                                                                                }}
                                                                                className="text-sm px-3 py-2 cursor-pointer text-purple-700 hover:text-purple-800 hover:bg-purple-50"
                                                                            >
                                                                                <FolderTree className="h-4 w-4 mr-2" />
                                                                                Assign ISF Metadata
                                                                            </DropdownMenuItem>
                                                                        )}
                                                                        <DropdownMenuSeparator className="bg-gray-200" />
                                                                        <DropdownMenuItem onClick={() => handleCopy(document)} className="text-sm px-3 py-2 cursor-pointer">
                                                                            <Copy className="h-4 w-4 mr-2 text-gray-500" />
                                                                            Copy Link
                                                                        </DropdownMenuItem>
                                                                    </DropdownMenuContent>
                                                                </DropdownMenu>
                                                            </TableCell>
                                                        </TableRow>
                                                    ))}
                                                </>
                                            ) : (
                                                <TableRow>
                                                    <TableCell colSpan={11} className="text-center py-16">
                                                        <div className="flex flex-col items-center space-y-3">
                                                            <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center">
                                                                <FileText className="w-8 h-8 text-gray-400" />
                                                            </div>
                                                            <div className="space-y-1">
                                                                <p className="text-base font-semibold text-gray-900">No documents found</p>
                                                                <p className="text-sm text-gray-500">Try adjusting your search criteria or filters</p>
                                                            </div>
                                                        </div>
                                                    </TableCell>
                                                </TableRow>
                                            )}
                                        </TableBody>
                                    </Table>
                                </div>

                                {/* Document Count */}
                                <div className="flex-none flex items-center justify-between px-3 py-1.5 border-t bg-white">
                                    <p className="text-[10px] text-muted-foreground">
                                        {filteredDocuments.length > displayLimit
                                            ? `Showing first ${displayLimit} of ${filteredDocuments.length} documents - use filters to narrow results`
                                            : `Showing all ${filteredDocuments.length} documents`}
                                    </p>
                                </div>
                            </div>
                        )}

                        {/* ISF Assignment Dialog */}
                        <ISFAssignmentDialog
                            open={showISFAssignmentDialog}
                            onOpenChange={setShowISFAssignmentDialog}
                            document={documentForISFAssignment}
                            onSuccess={async () => {
                                // Refresh documents after successful assignment
                                await fetchDocuments();
                                // Force page refresh to ensure SidebarNav also refreshes
                                // This ensures the hierarchy updates immediately
                                setTimeout(() => {
                                    window.location.reload();
                                }, 500);
                            }}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Send to Workflow Confirmation Dialog */}
            <Dialog open={showSendToWorkflowDialog} onOpenChange={setShowSendToWorkflowDialog}>
                <DialogContent className="sm:max-w-[500px]">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <AlertCircle className="h-5 w-5 text-amber-500" />
                            Send Document to Workflow
                        </DialogTitle>
                        <DialogDescription className="pt-2">
                            Are you sure you want to send this document back to workflow?
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                            <p className="text-sm font-medium text-blue-900 mb-2">
                                Document: <span className="font-semibold">{documentToSendToWorkflow?.title || documentToSendToWorkflow?.documentId || 'Unknown'}</span>
                            </p>
                            <div className="text-sm text-blue-800 space-y-1">
                                <p className="flex items-start gap-2">
                                    <span className="font-medium">•</span>
                                    <span>Workflow will be reset to <strong>INTAKE</strong> state</span>
                                </p>
                                <p className="flex items-start gap-2">
                                    <span className="font-medium">•</span>
                                    <span>Document status will change to <strong>DRAFT</strong></span>
                                </p>
                                <p className="flex items-start gap-2">
                                    <span className="font-medium">•</span>
                                    <span>Document will be available in the workflow view again</span>
                                </p>
                                <p className="flex items-start gap-2">
                                    <span className="font-medium">•</span>
                                    <span>This action will be logged in the audit trail</span>
                                </p>
                            </div>
                        </div>
                        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                            <p className="text-xs text-amber-800">
                                <strong>Note:</strong> This action cannot be undone. The document will need to go through the workflow stages again.
                            </p>
                        </div>
                    </div>
                    <div className="flex justify-end gap-3 pt-4 border-t">
                        <Button
                            variant="outline"
                            onClick={() => {
                                setShowSendToWorkflowDialog(false);
                                setDocumentToSendToWorkflow(null);
                            }}
                            disabled={isSendingToWorkflow}
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={confirmSendToWorkflow}
                            disabled={isSendingToWorkflow}
                            className="bg-blue-600 hover:bg-blue-700 text-white"
                        >
                            {isSendingToWorkflow ? (
                                <>
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                    Sending...
                                </>
                            ) : (
                                <>
                                    <GitBranch className="h-4 w-4 mr-2" />
                                    Send to Workflow
                                </>
                            )}
                        </Button>
                    </div>
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
                    onUploadComplete={refreshData}
                    selectedStudy={selectedStudy}
                />
            </RightDrawer>
        </div>
    );
};

export default ContentArea;