import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import {
  Upload,
  FileText,
  Brain,
  CheckCircle,
  AlertCircle,
  Loader2,
  X,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
  Edit,
  RotateCcw,
  ArrowRight,
  Clock,
  Fingerprint,
  Minimize2,
  Maximize2,
  Calendar,
  Globe,
  MapPin,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import useTmfHierarchy from '../../hooks/useTmfHierarchy';
import { resolveArtifactDetails as resolveArtifactFromMap } from '@/utils/tmfHierarchyUtils';
import { cn } from '@/lib/utils';
import { useToast } from '@/components/ui/use-toast';
import api from '@/services/api';
import isfDocumentService from '@/services/isfDocument.service';
import DocumentDialog from '../dialogs/DocumentDialog';
import DuplicateDocumentDialog from '../dialogs/DuplicateDocumentDialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

// import { Document, Page, pdfjs } from 'react-pdf';
// pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;
import * as pdfjs from 'pdfjs-dist';

// Map the worker to the local distribution file
pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.js`;

import { Viewer, Worker } from '@react-pdf-viewer/core';
import { highlightPlugin } from '@react-pdf-viewer/highlight';
import '@react-pdf-viewer/core/lib/styles/index.css';

// Section mapping from DocumentDialog.jsx - handles both two-part and three-part section numbers
const sectionMapping = {
  // Two-part section numbers (main sections)
  "01.01": "Trial Oversight",
  "01.02": "Trial Team",
  "01.03": "Trial Committee",
  "01.04": "Meetings",
  "01.05": "General",
  "02.01": "Product and Trial Documentation",
  "02.02": "Subject Documentation",
  "02.03": "Reports",
  "02.04": "General",
  "03.01": "Trial Approval",
  "03.02": "Investigational Medicinal Product",
  "03.03": "Trial Status Reporting",
  "03.04": "General",
  "04.01": "IRB or IEC Trial Approval",
  "04.02": "Other Committees",
  "04.03": "Trial Status Reporting",
  "04.04": "General",
  "05.01": "Site Selection",
  "05.02": "Site Set-up",
  "05.03": "Site Initiation",
  "05.04": "Site Management",
  "05.05": "General",
  "06.01": "IP Documentation",
  "06.02": "IP Release Process Documentation",
  "06.03": "IP Allocation Documentation",
  "06.04": "Storage",
  "06.05": "Non-IP Documentation",
  "06.06": "Interactive Response Technology",
  "06.07": "General",
  "07.01": "Safety Documentation",
  "07.02": "Trial Status Reporting",
  "07.03": "General",
  "08.01": "Facility Documentation",
  "08.02": "Sample Documentation",
  "08.03": "General",
  "09.01": "Third Party Oversight",
  "09.02": "Third Party Set-up",
  "09.03": "General",
  "10.01": "Data Management Oversight",
  "10.02": "Data Capture",
  "10.03": "Database",
  "10.04": "EDC Management",
  "10.05": "General",
  "11.01": "Statistics Oversight",
  "11.02": "Randomization",
  "11.03": "Analysis",
  "11.04": "Report",
  "11.05": "General",

  // Three-part section numbers (artifact-level sections)
  "01.01.01": "Trial Master File Plan",
  "01.01.02": "Trial Management Plan",
  "01.01.03": "Quality Plan",
  "01.01.04": "List of SOPs Current During Trial",
  "01.01.05": "Operational Procedure Manual",
  "01.01.06": "Recruitment Plan",
  "01.01.07": "Communication Plan",
  "01.01.08": "Monitoring Plan",
  "01.01.09": "Medical Monitoring Plan",
  "01.01.10": "Publication Policy",
  "01.01.11": "Debarment Statement",
  "01.01.12": "Trial Status Report",
  "01.01.13": "Investigator Newsletter",
  "01.01.14": "Audit Certificate",
  "01.01.15": "Filenote Master List",
  "01.01.16": "Risk Management Plan",
  "01.01.17": "Vendor Management Plan",
  "01.01.18": "Roles and Responsibility Matrix",
  "01.01.19": "Transfer of Regulatory Obligations",
  "01.01.20": "Operational Oversight",
  "01.02.01": "Trial Team Details",
  "01.02.02": "Trial Team Curriculum Vitae",
  "01.03.01": "Committee Process",
  "01.03.02": "Committee Member List",
  "01.03.03": "Committee Output",
  "01.03.04": "Committee Member Curriculum Vitae",
  "01.03.05": "Committee Member Financial Disclosure Form",
  "01.03.06": "Committee Member Contract",
  "01.03.07": "Committee Member Confidentiality Disclosure Agreement",
  "01.04.01": "Kick-off Meeting Material",
  "01.04.02": "Trial Team Training Material",
  "01.04.03": "Investigators Meeting Material",
  "02.01.01": "Investigator's Brochure",
  "02.01.02": "Protocol",
  "02.01.03": "Protocol Synopsis",
  "02.01.04": "Protocol Amendment",
  "02.01.05": "Financial Disclosure Summary",
  "02.01.06": "Insurance",
  "02.01.07": "Sample Case Report Form",
  "02.01.10": "Report of Prior Investigations",
  "02.01.11": "Marketed Product Material",
  "02.02.01": "Subject Diary",
  "02.02.02": "Subject Questionnaire",
  "02.02.03": "Informed Consent Form",
  "02.02.04": "Subject Information Sheet",
  "02.02.05": "Subject Participation Card",
  "02.02.06": "Advertisements for Subject Recruitment",
  "02.02.07": "Other Information Given to Subjects",
  "02.03.01": "Clinical Study Report",
  "02.03.02": "Bioanalytical Report",
  "02.04.01": "Relevant Communications",
  "02.04.02": "Tracking Information",
  "02.04.03": "Meeting Material",
  "02.04.04": "Filenote",
  "03.01.01": "Regulatory Submission",
  "03.01.02": "Regulatory Authority Decision",
  "03.01.03": "Notification of Regulatory Identification Number",
  "03.01.04": "Public Registration",
  "03.02.01": "Import or Export License Application",
  "03.02.02": "Import or Export Documentation",
  "03.02.03": "Notification of Safety or Trial Information",
  "03.02.04": "Regulatory Progress Report",
  "03.02.05": "Regulatory Notification of Trial Termination",
  "04.01.01": "IRB or IEC Submission",
  "04.01.02": "IRB or IEC Decision",
  "04.01.03": "IRB or IEC Composition",
  "04.01.04": "IRB or IEC Documentation of Non-Voting Status",
  "04.01.05": "IRB or IEC Compliance Documentation",
  "04.02.01": "Other Submissions",
  "04.02.02": "Other Approvals",
  "04.03.01": "Notification to IRB or IEC of Safety Information",
  "04.03.02": "IRB or IEC Progress Report",
  "04.03.03": "IRB or IEC Notification of Trial Termination",
  "05.01.01": "Site Contact Details",
  "05.01.02": "Confidentiality Agreement",
  "05.01.03": "Feasibility Documentation",
  "05.01.04": "Pre Trial Monitoring Report",
  "05.01.05": "Sites Evaluated but not Selected",
  "05.02.01": "Acceptance of Investigator Brochure",
  "05.02.02": "Protocol Signature Page",
  "05.02.03": "Protocol Amendment Signature Page",
  "05.02.04": "Principal Investigator Curriculum Vitae",
  "05.02.05": "Sub-Investigator Curriculum Vitae",
  "05.02.06": "Other Curriculum Vitae",
  "05.02.07": "Site Staff Qualification Supporting Information",
  "05.02.08": "Form FDA 1572",
  "05.02.09": "Investigator Regulatory Agreement",
  "05.02.10": "Financial Disclosure Form",
  "05.02.11": "Data Privacy Agreement",
  "05.02.12": "Clinical Trial Agreement",
  "05.02.13": "Indemnity",
  "05.02.14": "Other Financial Agreement",
  "05.03.01": "IP Site Release Documentation",
  "05.03.02": "Site Signature Sheet",
  "05.03.03": "Investigators Agreement (Device)",
  "05.03.04": "Coordinating Investigator Documentation",
  "05.03.05": "Trial Initiation Monitoring Report",
  "05.03.06": "Site Training Material",
  "05.03.07": "Site Evidence of Training",
  "05.04.01": "Subject Log",
  "05.04.02": "Source Data Verification",
  "05.04.03": "Monitoring Visit Report",
  "05.04.04": "Visit Log",
  "05.04.05": "Additional Monitoring Activity",
  "05.04.06": "Protocol Deviations",
  "05.04.07": "Financial Documentation",
  "05.04.08": "Final Trial Close Out Monitoring Report",
  "05.04.09": "Notification to Investigators of Safety Information",
  "05.04.10": "Subject Identification Log",
  "05.04.11": "Source Data",
  "05.04.12": "Monitoring Visit Follow-up Documentation",
  "05.04.13": "Subject Eligibility Verification Forms and Worksheets",
  "06.01.01": "IP Supply Plan",
  "06.01.02": "IP Instructions for Handling",
  "06.01.03": "IP Sample Label",
  "06.01.04": "IP Shipment Documentation",
  "06.01.05": "IP Accountability Documentation",
  "06.01.06": "IP Transfer Documentation",
  "06.01.07": "IP Re-labeling Documentation",
  "06.01.08": "IP Recall Documentation",
  "06.01.09": "IP Quality Complaint Form",
  "06.01.10": "IP Return Documentation",
  "06.01.11": "IP Certificate of Destruction",
  "06.01.12": "IP Retest and Expiry Documentation",
  "06.01.13": "QP (Qualified Person) Certification",
  "06.01.14": "IP Regulatory Release Documentation",
  "06.01.15": "IP Verification Statements",
  "06.01.16": "Certificate of Analysis",
  "06.01.17": "IP Treatment Allocation Documentation",
  "06.01.18": "IP Unblinding Plan",
  "06.01.19": "IP Treatment Decoding Documentation",
  "06.01.20": "IP Storage Condition Documentation",
  "06.01.21": "IP Storage Condition Excursion Documentation",
  "06.01.22": "Maintenance Logs",
  "06.05.01": "Non-IP Supply Plan",
  "06.05.02": "Non-IP Shipment Documentation",
  "06.05.03": "Non-IP Return Documentation",
  "06.05.04": "Non-IP Storage Documentation",
  "06.06.01": "IRT User Requirement Specification",
  "06.06.02": "IRT Validation Certification",
  "06.06.03": "IRT User Acceptance Testing (UAT) Certification",
  "06.06.04": "IRT User Manual",
  "06.06.05": "IRT User Account Management",
  "07.01.01": "Safety Management Plan",
  "07.01.02": "Pharmacovigilance Database Line Listing",
  "07.01.03": "Expedited Safety Report",
  "07.01.04": "SAE Report",
  "07.01.05": "Pregnancy Report",
  "07.01.06": "Special Events of Interest",
  "08.01.01": "Certification or Accreditation",
  "08.01.02": "Laboratory Validation Documentation",
  "08.01.03": "Laboratory Results Documentation",
  "08.01.04": "Normal Ranges",
  "08.01.05": "Manual",
  "08.01.06": "Supply Import Documentation",
  "08.02.01": "Head of Facility Curriculum Vitae",
  "08.02.02": "Standardization Methods",
  "08.02.03": "Specimen Label",
  "08.02.04": "Shipment Records",
  "08.02.05": "Sample Storage Condition Log",
  "08.02.06": "Sample Import or Export Documentation",
  "08.02.07": "Record of Retained Samples",
  "08.02.08": "Qualification and Compliance",
  "09.01.01": "Third Party Curriculum Vitae",
  "09.01.02": "Ongoing Third Party Oversight",
  "09.02.01": "Confidentiality Agreement",
  "09.02.02": "Vendor Selection",
  "09.02.03": "Contractual Agreement",
  "10.01.01": "Data Management Plan",
  "10.01.02": "CRF Completion Requirements",
  "10.01.03": "Annotated CRF",
  "10.01.04": "Documentation of Corrections to Entered Data",
  "10.01.05": "Final Subject Data",
  "10.02.01": "Database Requirements",
  "10.02.02": "Edit Check Plan",
  "10.02.03": "Edit Check Programming",
  "10.02.04": "Edit Check Testing",
  "10.02.05": "Approval for Database Activation",
  "10.02.06": "External Data Transfer Specifications",
  "10.02.07": "Data Entry Guidelines (Paper)",
  "10.02.08": "SAE Reconciliation",
  "10.02.09": "Dictionary Coding",
  "10.02.10": "Data Review Documentation",
  "10.02.11": "Database Lock and Unlock Approval",
  "10.02.12": "Database Change Control",
  "10.02.13": "System Account Management",
  "10.02.14": "Technical Design Document",
  "10.02.15": "Validation Documentation",
  "11.01.01": "Statistical Analysis Plan",
  "11.01.02": "Sample Size Calculation",
  "11.02.01": "Randomization Plan",
  "11.02.02": "Randomization Procedure",
  "11.02.03": "Master Randomization List",
  "11.02.04": "Randomization Programming",
  "11.02.05": "Randomization Sign Off",
  "11.02.06": "End of Trial or Interim Unblinding",
  "11.03.01": "Data Definitions for Analysis Datasets",
  "11.03.02": "Analysis QC Documentation",
  "11.03.03": "Interim Analysis Raw Datasets",
  "11.03.04": "Interim Analysis Programs",
  "11.03.05": "Interim Analysis Datasets",
  "11.03.06": "Interim Analysis Output",
  "11.03.07": "Final Analysis Raw Datasets",
  "11.03.08": "Final Analysis Programs",
  "11.03.09": "Final Analysis Datasets",
  "11.03.10": "Final Analysis Output",
  "11.03.11": "Subject Evaluability Criteria and Subject Classification",
  "11.04.01": "Interim Statistical Report(s)",
  "11.04.02": "Statistical Report"
};

const getDefaultZones = () => [
  { id: '1', number: '1', name: 'Trial Management' },
  { id: '2', number: '2', name: 'Central Trial Documents' },
  { id: '3', number: '3', name: 'Regulatory' },
  { id: '4', number: '4', name: 'IRB or IEC and other Approvals' },
  { id: '5', number: '5', name: 'Site Management' },
  { id: '6', number: '6', name: 'IP and Trial Supplies' },
  { id: '7', number: '7', name: 'Safety Reporting' },
  { id: '8', number: '8', name: 'Central and Local Testing' },
  { id: '9', number: '9', name: 'Third parties' },
  { id: '10', number: '10', name: 'Data Management' },
  { id: '11', number: '11', name: 'Statistics' }
];

const AIUploadDrawer = ({ isOpen, onClose, onUploadComplete, selectedStudy, selectedSite, emailAttachmentData }) => {
  const { toast } = useToast();
  const { artifactSubartifacts } = useTmfHierarchy();
  const resolveArtifactDetails = (artifactHint) => resolveArtifactFromMap(artifactHint, artifactSubartifacts);
  const [uploadMode, setUploadMode] = useState('single'); // 'single' or 'bulk'
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(1); // 1: Upload, 2: Classification, 3: Review
  const [aiAnalysis, setAiAnalysis] = useState({});
  const [manualClassification, setManualClassification] = useState({});
  const [selectedHierarchy, setSelectedHierarchy] = useState({});
  const fileInputRef = useRef(null);

  // Enhanced state for content-based classification
  const [classificationResults, setClassificationResults] = useState([]);
  const [processingStatus, setProcessingStatus] = useState({});
  const [confidenceScores, setConfidenceScores] = useState({});

  // Validation state
  const [validationResults, setValidationResults] = useState({}); // { fileName: validationResult }
  const [validating, setValidating] = useState(false);
  const [validationStatus, setValidationStatus] = useState({}); // { fileName: 'validating' | 'valid' | 'invalid' }
  const [securityInsights, setSecurityInsights] = useState([]);

  // Enhanced progress tracking
  const [progressStage, setProgressStage] = useState('idle'); // 'idle', 'uploading', 'processing', 'complete'
  const [progressMessage, setProgressMessage] = useState('');

  // Helper function to reset progress state
  const resetProgressState = () => {
    setProgressStage('idle');
    setProgressMessage('');
    setUploadProgress(0);
  };

  const [documentDialogOpen, setDocumentDialogOpen] = useState(false);
  const [selectedFileForDialog, setSelectedFileForDialog] = useState(null);
  const [aiClassificationForDialog, setAiClassificationForDialog] = useState(null);
  const [editingFileIndex, setEditingFileIndex] = useState(null);
  const [activeBulkFileIndex, setActiveBulkFileIndex] = useState(0);
  const [duplicateError, setDuplicateError] = useState(null);

  // Preview state
  const [previewZoom, setPreviewZoom] = useState(100);
  const [isPreviewExpanded, setIsPreviewExpanded] = useState(false);
  const [fileUrls, setFileUrls] = useState({});

  const [phiDetections, setPhiDetections] = useState([]);
  const [validationData, setValidationData] = useState([]);
  const pageCharIndexRef = useRef({});

  // Manage object URLs for file previews
  useEffect(() => {
    const urls = {};
    files.forEach(file => {
      urls[file.name] = URL.createObjectURL(file);
    });
    setFileUrls(urls);

    // Cleanup URLs on unmount or file change
    return () => {
      Object.values(urls).forEach(url => URL.revokeObjectURL(url));
    };
  }, [files]);

  // Form management with react-hook-form for embedded DocumentDialog
  const {
    register,
    handleSubmit,
    reset,
    control,
    setValue,
    formState: { errors, isSubmitting },
    watch
  } = useForm({
    defaultValues: {
      documentTitle: '',
      description: '',
      documentType: '',
      tmfReference: '',
      effectiveDate: null,
      expirationDate: null,
      accessLevel: 'Restricted',
      version: '1.0',
      study: '',
      site: '',
      country: '',
      indication: '',
      mimeType: '',
      pageCount: '',
      language: 'en',
      documentDate: null,
      approvalDate: null,
      author: '',
      contributors: [],
      qualityControlStatus: 'PENDING',
      completenessStatus: 'PENDING_REVIEW',
      archivalStatus: 'ACTIVE',
      regulatoryAuthority: '',
      gcpComplianceStatus: 'PENDING_REVIEW',
      retentionDuration: '',
      retentionStartDate: null,
      retentionEndDate: null,
      // Zone fields
      zoneNumber: '',
      zoneName: '',
      zoneDescription: '',
      // Section fields
      sectionNumber: '',
      sectionName: '',
      sectionDescription: '',
      // Artifact fields
      artifactNumber: '',
      artifactName: '',
      artifactDescription: '',
      subArtifactName: '',
      mandatory: false,
      // Document fields
      status: 'Draft',
      uploadDate: new Date(),
      // TMF Metadata fields
      processBasedMetadata: '',
      tmfLevel: '',
      coreOrRecommended: '',
      ichCode: '',
      iso14155Reference: '',
      uniqueIdNumber: '',
      sponsorDocument: false,
      investigatorDocument: false,
      processNumber: '',
      processName: '',
      trialLevelDocument: false,
      trialLevelMilestoneEvent: '',
      countryRegionLevelDocument: false,
      countryLevelMilestoneEvent: '',
      siteLevelDocument: false,
      siteLevelMilestoneEvent: ''
    }
  });

  // Watchers for dynamic form updates
  const artifactNumber = watch('artifactNumber');

  // Effect to handle artifact number changes - auto-populate artifact name and metadata
  useEffect(() => {
    if (artifactNumber && artifactSubartifacts[artifactNumber]) {
      const artifactData = artifactSubartifacts[artifactNumber];

      // Populate artifact name if not already set
      if (!watch('artifactName')) {
        setValue('artifactName', artifactData.name || '');
      }

      // Reset sub-artifact when artifact changes, but not during AI review step
      if (currentStep !== 2) {
        setValue('subArtifactName', '');
      }

      // Auto-populate all metadata fields from TMF Reference Model
      if (artifactData.definition) setValue('processBasedMetadata', artifactData.definition);
      if (artifactData.coreOrRecommended) setValue('coreOrRecommended', artifactData.coreOrRecommended);
      // Formatter for multiple values (e.g. ICH codes)
      const formatMultipleValues = (val) => {
        if (!val || val === 'N/A') return 'N/A';
        if (typeof val !== 'string') return val;
        // Replace newlines or multiple spaces with a comma and space
        return val.split(/[\n,]/).map(s => s.trim()).filter(Boolean).join(', ');
      };

      if (artifactData.ichCode !== null && artifactData.ichCode !== undefined)
        setValue('ichCode', formatMultipleValues(artifactData.ichCode));
      if (artifactData.iso14155Reference)
        setValue('iso14155Reference', formatMultipleValues(artifactData.iso14155Reference));
      if (artifactData.uniqueIdNumber !== null && artifactData.uniqueIdNumber !== undefined) setValue('uniqueIdNumber', artifactData.uniqueIdNumber);
      if (artifactData.sponsorDocument !== undefined) setValue('sponsorDocument', artifactData.sponsorDocument);
      if (artifactData.investigatorDocument !== undefined) setValue('investigatorDocument', artifactData.investigatorDocument);
      if (artifactData.processNumber !== null && artifactData.processNumber !== undefined) setValue('processNumber', artifactData.processNumber);
      if (artifactData.processName) setValue('processName', artifactData.processName);
      if (artifactData.trialLevelDocument !== undefined) setValue('trialLevelDocument', artifactData.trialLevelDocument);
      if (artifactData.trialLevelMilestone) setValue('trialLevelMilestoneEvent', artifactData.trialLevelMilestone);
      if (artifactData.countryLevelDocument !== undefined) setValue('countryRegionLevelDocument', artifactData.countryLevelDocument);
      if (artifactData.countryLevelMilestone) setValue('countryLevelMilestoneEvent', artifactData.countryLevelMilestone);
      if (artifactData.siteLevelDocument !== undefined) setValue('siteLevelDocument', artifactData.siteLevelDocument);
      if (artifactData.siteLevelMilestone) setValue('siteLevelMilestoneEvent', artifactData.siteLevelMilestone);

      // Set TMF Level based on document level flags
      if (artifactData.trialLevelDocument) {
        setValue('tmfLevel', 'Trial');
      } else if (artifactData.countryLevelDocument) {
        setValue('tmfLevel', 'Country');
      } else if (artifactData.siteLevelDocument) {
        setValue('tmfLevel', 'Site');
      }
    }
  }, [artifactNumber, setValue, watch]);

  const artifactOptions = useMemo(() => {
    const seen = new Set();
    return Object.entries(artifactSubartifacts).reduce((acc, [number, data]) => {
      const name = data?.name?.trim();
      if (!name) {
        return acc;
      }
      const key = name.toLowerCase();
      if (seen.has(key)) {
        return acc;
      }
      seen.add(key);
      acc.push({ number, name });
      return acc;
    }, []);
  }, [artifactSubartifacts]);

  useEffect(() => {
    if (!isOpen) {
      setSecurityInsights([]);
    }
  }, [isOpen]);

  // Handle email attachment data - skip to classification step with pre-classified data
  useEffect(() => {
    console.log('[AIUploadDrawer] Email attachment data effect', { isOpen, hasEmailAttachmentData: !!emailAttachmentData });

    if (isOpen && emailAttachmentData) {
      const { attachment, classification, fullResponse } = emailAttachmentData;

      console.log('[AIUploadDrawer] Processing email attachment data', {
        hasAttachment: !!attachment,
        hasClassification: !!classification,
        attachmentFilename: attachment?.filename,
        classificationKeys: classification ? Object.keys(classification) : []
      });

      // Create a File-like object from attachment data
      const fileName = attachment?.filename || attachment?.name || 'email-attachment.pdf';
      const fileSize = attachment?.size || 0;
      const mimeType = attachment?.mimeType || 'application/pdf';

      // Create a File object (we'll use a placeholder since we don't have the actual file)
      const file = new File([''], fileName, { type: mimeType });
      Object.defineProperty(file, 'size', { value: fileSize, writable: false });

      // Set the file first
      setFiles([file]);
      setUploadMode('single');

      // Populate classification results
      if (classification) {
        const classificationResult = {
          fileName: fileName,
          result: {
            success: true,
            classification: classification,
            extractedContent: fullResponse?.extractedContent || {},
            validation: fullResponse?.validation || { isValid: true, overallStatus: 'PASSED' }
          }
        };

        console.log('[AIUploadDrawer] Setting classification results', {
          fileName,
          hasClassificationResult: !!classificationResult,
          classificationKeys: Object.keys(classification)
        });

        // Set all classification-related state
        setClassificationResults([classificationResult]);
        setAiAnalysis({ [fileName]: classification });
        setContentAnalysis({ [fileName]: fullResponse?.extractedContent || {} });
        setConfidenceScores({ [fileName]: classification.confidence || 0 });
        setProcessingStatus({ [fileName]: 'Completed' });

        // Mark validation as passed
        setValidationStatus({ [fileName]: 'valid' });
        setValidationResults({
          [fileName]: {
            isValid: true,
            overallStatus: 'PASSED'
          }
        });

        // Skip directly to classification step (step 2)
        // Use setTimeout to ensure state updates are applied
        setTimeout(() => {
          console.log('[AIUploadDrawer] Moving to step 2');
          setCurrentStep(2);
        }, 0);
      } else {
        console.warn('[AIUploadDrawer] No classification data found in emailAttachmentData');
      }
    } else if (isOpen && !emailAttachmentData) {
      // Reset to step 1 if no email attachment data
      setCurrentStep(1);
      setFiles([]);
      setClassificationResults([]);
      setAiAnalysis({});
      setConfidenceScores({});
      setProcessingStatus({});
      setValidationStatus({});
      setValidationResults({});
    }
  }, [isOpen, emailAttachmentData]);

  // Effect to populate form with AI classification data
  useEffect(() => {
    if (classificationResults.length > 0 && currentStep === 2) {
      const result = classificationResults[0]; // For single file
      const classification = result.result.classification;
      const fileName = result.fileName;
      const subArtifactName = classification.suggestedSubartifact;

      // Populate form with AI data
      setValue('documentTitle', classification.extractedMetadata?.title || fileName.replace(/\.[^/.]+$/, ""));
      setValue('description', classification.extractedMetadata?.description || 'N/A');
      setValue('documentType', classification.documentType || 'OTHER');
      setValue('tmfReference', (classification.suggestedArtifact || 'N/A'));
      setValue('version', classification.extractedMetadata?.version || '1.0');
      setValue('documentDate', classification.extractedMetadata?.documentDate || new Date().toISOString().split('T')[0]);
      setValue('author', classification.extractedMetadata?.author || 'N/A');
      setValue('pageCount', classification.extractedMetadata?.pageCount || 'N/A');
      setValue('mimeType', files[0]?.type || '');

      // Zone information
      setValue('zoneNumber', classification.suggestedZone?.number || 'N/A');
      setValue('zoneName', classification.suggestedZone?.name || 'N/A');
      setValue('zoneDescription', `AI-suggested zone: ${classification.suggestedZone?.name || 'N/A'}`);

      // Section information
      // Process section mapping

      // Handle section mapping with fallback logic
      let sectionNumber = (classification.suggestedSection || '').split(':')[0].trim();
      let sectionName = '';

      // Try to map section number to name
      if (sectionNumber && sectionMapping[sectionNumber]) {
        sectionName = sectionMapping[sectionNumber];
      } else if (sectionNumber) {
        // Handle three-part section numbers (e.g., "02.01.01" -> "02.01")
        if (sectionNumber.split('.').length === 3) {
          const twoPartNumber = sectionNumber.split('.').slice(0, 2).join('.');
          if (sectionMapping[twoPartNumber]) {
            sectionName = sectionMapping[twoPartNumber];
            sectionNumber = twoPartNumber; // Use the two-part number for consistency
          } else {
            // If still no match, use the section number as the name
            sectionName = sectionNumber;
          }
        } else {
          // If no direct mapping, try to find a partial match
          const matchingSection = Object.entries(sectionMapping).find(([number, name]) =>
            number.includes(sectionNumber) || sectionNumber.includes(number)
          );
          if (matchingSection) {
            sectionNumber = matchingSection[0];
            sectionName = matchingSection[1];
          } else {
            // If still no match, use the section number as the name
            sectionName = sectionNumber;
          }
        }
      }

      setValue('sectionNumber', sectionNumber || 'N/A');
      setValue('sectionName', sectionName || 'N/A');
      setValue('sectionDescription', `AI-suggested section: ${sectionName || 'N/A'}`);

      // Section mapping completed

      // Artifact information
      // Find the artifact number for the suggested artifact name
      const { number: artifactNumber, name: artifactName } = resolveArtifactDetails(classification.suggestedArtifact);

      setValue('artifactName', artifactName || 'N/A');
      setValue('artifactNumber', artifactNumber || 'N/A');
      setValue('subArtifactName', subArtifactName || 'N/A');
      setValue('artifactDescription', `AI-suggested artifact: ${artifactName || 'N/A'}`);

      // Auto-populate metadata from TMF Reference Model
      if (artifactNumber && artifactSubartifacts[artifactNumber]) {
        const artifactData = artifactSubartifacts[artifactNumber];
        setValue('processBasedMetadata', artifactData.definition || 'N/A');
        setValue('coreOrRecommended', artifactData.coreOrRecommended || 'N/A');
        // Formatter for multiple values (e.g. ICH codes)
        const formatMultipleValues = (val) => {
          if (!val || val === 'N/A') return 'N/A';
          if (typeof val !== 'string') return val;
          return val.split(/[\n,]/).map(s => s.trim()).filter(Boolean).join(', ');
        };

        setValue('ichCode', formatMultipleValues(artifactData.ichCode));
        setValue('iso14155Reference', formatMultipleValues(artifactData.iso14155Reference));
        setValue('uniqueIdNumber', (artifactData.uniqueIdNumber !== null && artifactData.uniqueIdNumber !== undefined) ? artifactData.uniqueIdNumber : 'N/A');
        setValue('sponsorDocument', artifactData.sponsorDocument !== undefined ? artifactData.sponsorDocument : false);
        setValue('investigatorDocument', artifactData.investigatorDocument !== undefined ? artifactData.investigatorDocument : false);
        setValue('processNumber', (artifactData.processNumber !== null && artifactData.processNumber !== undefined) ? artifactData.processNumber : 'N/A');
        setValue('processName', artifactData.processName || 'N/A');
        // Set TMF Level based on document level flags - consistently use booleans for internal state
        const isTrial = !!artifactData.trialLevelDocument;
        const isCountry = !!artifactData.countryLevelDocument;
        const isSite = !!artifactData.siteLevelDocument;

        setValue('trialLevelDocument', isTrial);
        setValue('trialLevelMilestoneEvent', artifactData.trialLevelMilestone || 'N/A');
        setValue('countryRegionLevelDocument', isCountry);
        setValue('countryLevelMilestoneEvent', artifactData.countryLevelMilestone || 'N/A');
        setValue('siteLevelDocument', isSite);
        setValue('siteLevelMilestoneEvent', artifactData.siteLevelMilestone || 'N/A');

        if (isTrial) {
          setValue('tmfLevel', 'Trial');
        } else if (isCountry) {
          setValue('tmfLevel', 'Country');
        } else if (isSite) {
          setValue('tmfLevel', 'Site');
        }
      }

      // Artifact mapping completed

      // Status
      setValue('status', 'DRAFT');
      setValue('qualityControlStatus', 'PENDING');
      setValue('completenessStatus', 'PENDING_REVIEW');
      setValue('archivalStatus', 'ACTIVE');
      setValue('gcpComplianceStatus', 'PENDING_REVIEW');
    }
  }, [classificationResults, currentStep, setValue, files]);

  // Effect to reset progress state when drawer opens
  useEffect(() => {
    if (isOpen) {
      resetProgressState();
    }
  }, [isOpen]);

  // Hardcoded zones for classification
  const zones = getDefaultZones();

  const handleFileSelect = async (event) => {
    const selectedFiles = Array.from(event.target.files);

    // Limit to 5 files for bulk upload
    if (uploadMode === 'bulk' && selectedFiles.length > 5) {
      toast({
        title: "File Limit Exceeded",
        description: "Maximum 5 files allowed for bulk upload",
        variant: "destructive"
      });
      return;
    }

    setFiles(selectedFiles);

    // Validate files immediately after selection
    await validateFiles(selectedFiles);
  };

  const handleDrop = async (event) => {
    event.preventDefault();
    const droppedFiles = Array.from(event.dataTransfer.files);

    // Limit to 5 files for bulk upload
    if (uploadMode === 'bulk' && droppedFiles.length > 5) {
      toast({
        title: "File Limit Exceeded",
        description: "Maximum 5 files allowed for bulk upload",
        variant: "destructive"
      });
      return;
    }

    setFiles(droppedFiles);

    // Validate files immediately after drop
    await validateFiles(droppedFiles);
  };

  const handleDragOver = (event) => {
    event.preventDefault();
  };

  const removeFile = (index) => {
    const fileToRemove = files[index];
    setFiles(files.filter((_, i) => i !== index));
    // Remove validation results for removed file
    setValidationResults(prev => {
      const updated = { ...prev };
      delete updated[fileToRemove.name];
      return updated;
    });
    setValidationStatus(prev => {
      const updated = { ...prev };
      delete updated[fileToRemove.name];
      return updated;
    });
  };

  const formatUploadError = (result, fileName) => {
    const baseDescription = result?.message || result?.error || `Failed to upload ${fileName}`;
    switch (result?.error) {
      case 'DuplicateDocument':
        return {
          title: 'Duplicate Document Detected',
          description: result?.message || `${fileName} matches an existing document (${result?.existingDocumentId || 'unknown ID'}).`
        };
      case 'PermissionDenied':
        return {
          title: 'Permission Denied',
          description: result?.message || 'You do not have permission to upload documents for this study.'
        };
      case 'MissingStudyContext':
        return {
          title: 'Study Required',
          description: result?.message || 'Please select a study before uploading.'
        };
      case 'UserLookupFailed':
        return {
          title: 'User Verification Failed',
          description: result?.message || 'Unable to verify your account. Please sign in again.'
        };
      default:
        return {
          title: 'Upload Failed',
          description: baseDescription
        };
    }
  };

  const buildSecurityToastDescription = (fileName, uploadResult) => {
    const details = uploadResult?.validation?.details || {};
    const pieces = [`${fileName} passed all security checks.`];
    if (details.mimeValidation?.detectedMimeType) {
      pieces.push(`Signature: ${details.mimeValidation.detectedMimeType}`);
    }
    if (details.metadataSanitization?.actions?.length) {
      pieces.push(`Sanitized (${details.metadataSanitization.actions.join(', ')})`);
    }
    if (details.fileHash?.hash) {
      pieces.push(`Hash: ${details.fileHash.hash.slice(0, 16)}…`);
    }
    return pieces.join(' ');
  };

  const recordSecurityInsight = (fileName, uploadResult) => {
    const details = uploadResult?.validation?.details || {};
    const metadataSanitization =
      details.metadataSanitization ||
      uploadResult?.document?.metadataSanitization ||
      uploadResult?.data?.metadataSanitization;
    const fileHash =
      details.fileHash ||
      (uploadResult?.document?.fileHash
        ? { hash: uploadResult.document.fileHash, algorithm: uploadResult.document.fileHashAlgorithm }
        : null);
    const hasInsight = details.mimeValidation || metadataSanitization || fileHash;
    if (!hasInsight) {
      return;
    }

    const entry = {
      id: `${fileName}-${Date.now()}`,
      fileName,
      timestamp: new Date().toISOString(),
      mimeValidation: details.mimeValidation,
      metadataSanitization,
      fileHash
    };

    setSecurityInsights((prev) => [entry, ...prev].slice(0, 5));
  };

  const PDFPreviewer = ({ fileUrl, phiDetections, previewZoom }) => {
    const containerRef = useRef(null);
    const renderHighlightTargetPlugin = highlightPlugin({
      renderHighlightTarget: (props) => (
        <div />
      ),
      renderHighlightContent: (props) => (
        <div />
      ),
    });

    const [isDocumentLoaded, setIsDocumentLoaded] = useState(false);
    const viewerRef = useRef(null);

    const highlightTerms = useMemo(() => {
      if (!phiDetections || !Array.isArray(phiDetections)) return [];

      const terms = new Set();
      phiDetections.forEach(group => {
        group.values?.forEach(item => {
          if (item.value && typeof item.value === 'string' && item.value.trim().length > 0) {
            const cleaned = item.value.trim().replace(/\s+/g, ' ');
            terms.add(cleaned);
          }
        });
      });

      return Array.from(terms);
    }, [phiDetections]);

    useEffect(() => {
      if (!isDocumentLoaded || highlightTerms.length === 0) return;

      const timer = setTimeout(() => {
        highlightAllTermsInPDF(highlightTerms);
      }, 1500);

      return () => clearTimeout(timer);
    }, [highlightTerms, isDocumentLoaded]);

    const highlightAllTermsInPDF = (terms) => {
      try {
        if (!containerRef.current) return;
        console.log("🔍 Custom highlighting all terms:", terms);

        const textLayers = containerRef.current.querySelectorAll('.rpv-core__text-layer');

        textLayers.forEach(layer => {
          // Get all text content from the layer to reconstruct full text
          const spans = Array.from(layer.querySelectorAll('span'));
          const fullText = spans.map(s => s.textContent).join('');

          console.log("Full page text:", fullText);

          terms.forEach(term => {
            const lowerFullText = fullText.toLowerCase();
            const lowerTerm = term.toLowerCase();

            // Find all occurrences of the term in the full text
            let startIndex = 0;
            while ((startIndex = lowerFullText.indexOf(lowerTerm, startIndex)) !== -1) {
              const endIndex = startIndex + term.length;

              console.log(`Found "${term}" at position ${startIndex}-${endIndex}`);

              // Now find which spans contain this range
              let currentPos = 0;
              spans.forEach(span => {
                const spanStart = currentPos;
                const spanEnd = currentPos + span.textContent.length;

                // Check if this span overlaps with our term
                if (spanEnd > startIndex && spanStart < endIndex) {
                  console.log(`Highlighting span: "${span.textContent}"`);
                  // Darker highlight styles
                  span.style.backgroundColor = '#fbbf24'; // Solid yellow
                  span.style.color = '#000000'; // Black text for contrast
                  span.style.outline = '2px solid #f59e0b';
                  span.style.padding = '1px 0'; // Add slight padding
                  span.style.borderRadius = '2px';
                }

                currentPos = spanEnd;
              });

              startIndex = endIndex; // Move to next occurrence
            }
          });
        });

        console.log("✅ Highlighting complete");

      } catch (err) {
        console.error("❌ Custom highlighting error:", err);
      }
    };

    const handleDocumentLoad = (e) => {
      console.log("✅ PDF Document Loaded");
      setIsDocumentLoaded(true);
    };

    return (
      <div ref={containerRef} className="h-full w-full">
        <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.min.js">
          <Viewer
            ref={viewerRef}
            fileUrl={fileUrl}
            plugins={[renderHighlightTargetPlugin]}
            defaultScale={previewZoom / 100}
            onDocumentLoad={handleDocumentLoad}
          />
        </Worker>
      </div>
    );
  };

  const renderFilePreview = (fileName) => {
    const file = files.find(f => f.name === fileName);
    if (!file) return null;

    const fileUrl = fileUrls[fileName];
    if (!fileUrl) return null;

    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');

    // Get PHI detections specifically for this file from validationResults
    const filePhiDetections = validationResults[fileName]?.phiDetection?.detections || [];

    return (
      <div className="h-full flex flex-col bg-white">
        {/* Header UI */}
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-medium truncate">{file.name}</h3>

          <div className="flex items-center gap-2">
            <button onClick={() => setPreviewZoom(z => Math.max(50, z - 25))}>
              -
            </button>
            <span>{previewZoom}%</span>
            <button onClick={() => setPreviewZoom(z => Math.min(200, z + 25))}>
              +
            </button>

            <button onClick={() => setIsPreviewExpanded(!isPreviewExpanded)}>
              {isPreviewExpanded ? <Minimize2 /> : <Maximize2 />}
            </button>
          </div>
        </div>

        {/* Body / Viewer Container */}
        <div className="flex-1 overflow-auto">
          {isPdf ? (
            <PDFPreviewer
              fileUrl={fileUrl}
              phiDetections={filePhiDetections.length > 0 ? filePhiDetections : phiDetections}
              previewZoom={previewZoom}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400">
              Preview not available for this format
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderValidationIssuePanel = (fileName, errorDetails) => {
    if (!errorDetails?.length) return null;

    return (
      <div className="mt-3 space-y-2">
        <div className="flex items-center justify-between rounded-md border border-red-100 bg-red-50 px-3 py-2">
          <div className="flex items-start space-x-2">
            <ShieldAlert className="h-4 w-4 flex-shrink-0 text-red-600" />
            <div>
              <p className="text-sm font-semibold text-red-900">
                Action required for {fileName}
              </p>
              <p className="text-xs text-red-700">
                Resolve the issues below, then re-upload the document.
              </p>
            </div>
          </div>
          <Badge variant="outline" className="border-red-200 text-xs text-red-700">
            {errorDetails.length} issue{errorDetails.length > 1 ? 's' : ''}
          </Badge>
        </div>

        <Accordion type="multiple" defaultValue={['validation-errors']} className="rounded-md border border-red-100 bg-white">
          <AccordionItem value="validation-errors">
            <AccordionTrigger className="px-4 py-2 text-sm font-medium text-red-900 hover:text-red-900 hover:no-underline">
              <div className="flex items-center space-x-2">
                <AlertCircle className="h-4 w-4 text-red-600" />
                <span>Validation Errors</span>
              </div>
            </AccordionTrigger>
            <AccordionContent className="p-0">
              <div className="divide-y divide-red-100">
                {errorDetails.map((detail, index) => (
                  <div key={index} className="p-4 bg-red-50/30">
                    <div className="flex items-center space-x-2 mb-1">
                      <ShieldAlert className="h-4 w-4 text-red-600" />
                      <span className="font-semibold text-red-900 text-sm">{detail.type}</span>
                    </div>
                    <p className="text-sm text-gray-800 ml-6">{detail.message}</p>
                    {detail.details?.length > 0 && (
                      <ul className="mt-2 list-disc space-y-1 pl-11 text-xs text-gray-600">
                        {detail.details.map((item, idx) => (
                          <li key={idx}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>

        {/* Enhanced Document Preview for Invalid Documents - Height constrained to save space */}
        <div className="mt-4 rounded-lg border border-gray-200 overflow-hidden shadow-sm h-[600px]">
          {renderFilePreview(fileName)}
        </div>
      </div>
    );
  };

  const renderValidationChecks = (status, validation) => {
    if (!status && !validation) return null;

    const stateVisuals = {
      pending: {
        container: 'bg-white border-gray-200',
        badge: 'border-gray-200 text-gray-600',
        label: 'Queued',
        icon: <Clock className="w-4 h-4 text-gray-400" />
      },
      running: {
        container: 'bg-blue-50 border-blue-200',
        badge: 'border-blue-200 text-blue-700 bg-blue-50',
        label: 'Running',
        icon: <Loader2 className="w-4 h-4 text-blue-600 animate-spin" />
      },
      passed: {
        container: 'bg-green-50 border-green-200',
        badge: 'border-green-200 text-green-700 bg-green-50',
        label: 'Passed',
        icon: <CheckCircle className="w-4 h-4 text-green-600" />
      },
      failed: {
        container: 'bg-red-50 border-red-200',
        badge: 'border-red-200 text-red-700 bg-red-50',
        label: 'Failed',
        icon: <X className="w-4 h-4 text-red-600" />
      }
    };

    const resolveState = (passes, hasData = false) => {
      if (status === 'error') return 'failed';
      // If we are currently in any validating state, return running
      if (['validating', 'scanning-virus', 'validating-format', 'detecting-phi'].includes(status)) return 'running';
      if (!hasData && !validation) return 'pending';
      if (passes === undefined || passes === null) {
        return hasData ? 'pending' : 'pending';
      }
      return passes ? 'passed' : 'failed';
    };

    const virusClean = validation?.virusScan ? validation.virusScan.status === 'CLEAN' : undefined;
    const phiClean = validation?.phiDetection ? !validation.phiDetection.containsPHI : undefined;
    const formattingClean = validation?.generalValidation
      ? validation.generalValidation.status === 'VALID'
      : undefined;
    const mimeStatus = validation?.mimeValidation?.status
      ? validation.mimeValidation.status.toUpperCase()
      : null;
    const mimeClean = mimeStatus ? mimeStatus === 'PASSED' : undefined;

    // Determine current step based on validation state strings
    const getCurrentStep = () => {
      if (status === 'scanning-virus') return 1;
      if (status === 'validating-format') return 2;
      if (status === 'detecting-phi') return 3;

      if (status === 'validating') {
        if (!validation?.virusScan) return 1;
        if (virusClean === false) return 1;
        if (!validation?.generalValidation) return 2;
        if (formattingClean === false) return 2;
        return 3;
      }
      return null;
    };

    const currentStep = getCurrentStep();
    const isStepActive = (stepNum) => currentStep === stepNum;
    const isStepCompleted = (stepNum) => {
      if (status === 'error') return false;

      // Step is completed if we are currently on a LATER step
      if (['validating', 'scanning-virus', 'validating-format', 'detecting-phi'].includes(status)) {
        return currentStep !== null && currentStep > stepNum;
      }

      // If overall status is 'valid' or 'invalid', check the specific result
      if (stepNum === 1) return virusClean === true;
      if (stepNum === 2) return formattingClean === true && virusClean === true;
      if (stepNum === 3) return phiClean === true && formattingClean === true && virusClean === true;
      return false;
    };
    const isStepFailed = (stepNum) => {
      if (stepNum === 1) return virusClean === false;
      if (stepNum === 2) return formattingClean === false && virusClean === true;
      if (stepNum === 3) return phiClean === false && formattingClean === true && virusClean === true;
      return false;
    };

    const checks = [
      {
        key: 'virus',
        label: 'Step 1: Virus Scan',
        stepNumber: 1,
        state: isStepActive(1) ? 'running' : isStepFailed(1) ? 'failed' : isStepCompleted(1) ? 'passed' : resolveState(virusClean, !!validation?.virusScan),
        description: validation?.virusScan
          ? (virusClean
            ? '✓ Virus scan completed – no threats found.'
            : validation.virusScan.notes || '✗ Potential threat detected. File blocked.')
          : isStepActive(1)
            ? 'Scanning for malware, ransomware, and suspicious macros...'
            : 'Pending virus scan...'
      },
      {
        key: 'format',
        label: 'Step 2: Document Formatting Check',
        stepNumber: 2,
        state: isStepActive(2) ? 'running' : isStepFailed(2) ? 'failed' : isStepCompleted(2) ? 'passed' : (virusClean === true ? resolveState(formattingClean, !!validation?.generalValidation) : 'pending'),
        description: virusClean === false
          ? 'Skipped - virus scan failed'
          : validation?.generalValidation
            ? (formattingClean
              ? '✓ File size, type, and name meet policy.'
              : validation.generalValidation.notes ||
              '✗ Document violates size, type, or naming policy.')
            : isStepActive(2)
              ? 'Checking file size limits, allowed types, and naming rules...'
              : virusClean === true
                ? 'Pending formatting validation...'
                : 'Waiting for virus scan to complete...'
      },
      {
        key: 'phi',
        label: 'Step 3: PHI Detection',
        stepNumber: 3,
        state: isStepActive(3) ? 'running' : isStepFailed(3) ? 'failed' : isStepCompleted(3) ? 'passed' : (formattingClean === true && virusClean === true ? resolveState(phiClean, !!validation?.phiDetection) : 'pending'),
        description: virusClean === false || formattingClean === false
          ? 'Skipped - previous validation step failed'
          : validation?.phiDetection
            ? (phiClean
              ? '✓ No PHI indicators detected in document text.'
              : validation.phiDetection.notes || '✗ Sensitive PHI/PII patterns detected.')
            : isStepActive(3)
              ? 'Analyzing extracted text for PHI/PII patterns...'
              : (formattingClean === true && virusClean === true)
                ? 'Pending PHI detection...'
                : 'Waiting for previous steps to complete...'
      }
    ];

    return (
      <div className="mt-4">
        <div className="flex items-center space-x-2 mb-4">
          <div className="p-1.5 rounded-lg bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100">
            <ShieldCheck className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900">Sequential Security Validation</p>
            <p className="text-xs text-gray-500">Documents are validated in a strict sequence</p>
          </div>
        </div>

        <div className="relative space-y-4">
          {checks.map((check, index) => {
            const visuals = stateVisuals[check.state] || stateVisuals.pending;
            const isBlocked = check.stepNumber > 1 && checks[check.stepNumber - 2]?.state === 'failed';
            const isActive = isStepActive(check.stepNumber);
            const isCompleted = isStepCompleted(check.stepNumber);
            const isFailed = isStepFailed(check.stepNumber);

            return (
              <div key={check.key} className="relative">
                {/* Enhanced connection line between steps */}
                {index < checks.length - 1 && (
                  <div className="absolute left-5 top-14 w-0.5 h-5 z-0">
                    <div className={`w-full h-full transition-all duration-500 ${isCompleted
                      ? 'bg-gradient-to-b from-green-400 to-green-300 shadow-sm'
                      : isFailed
                        ? 'bg-gradient-to-b from-red-300 to-red-200'
                        : isActive
                          ? 'bg-gradient-to-b from-blue-300 to-blue-200 animate-pulse'
                          : 'bg-gray-200'
                      }`} />
                  </div>
                )}

                {/* Main step card */}
                <div className={`relative p-5 rounded-xl border-2 text-sm transition-all duration-300 transform ${isActive
                  ? 'border-blue-400 bg-gradient-to-br from-blue-50 via-indigo-50 to-blue-50 shadow-lg shadow-blue-100/50 scale-[1.02] ring-2 ring-blue-200/50'
                  : isFailed
                    ? 'border-red-300 bg-gradient-to-br from-red-50 via-rose-50 to-red-50 shadow-md shadow-red-100/30'
                    : isCompleted
                      ? 'border-green-300 bg-gradient-to-br from-green-50 via-emerald-50 to-green-50 shadow-md shadow-green-100/30'
                      : isBlocked
                        ? 'border-gray-200 bg-gray-50/50 opacity-50'
                        : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
                  }`}>
                  {/* Animated background glow for active step */}
                  {isActive && (
                    <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-400/10 via-indigo-400/10 to-blue-400/10 animate-pulse" />
                  )}

                  <div className="relative flex items-start justify-between">
                    <div className="flex items-start space-x-4 flex-1">
                      {/* Enhanced step number indicator */}
                      <div className="relative flex-shrink-0">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold transition-all duration-300 shadow-sm ${isActive
                          ? 'bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-blue-300/50 ring-2 ring-blue-200 ring-offset-2'
                          : isFailed
                            ? 'bg-gradient-to-br from-red-500 to-rose-600 text-white shadow-red-300/50'
                            : isCompleted
                              ? 'bg-gradient-to-br from-green-500 to-emerald-600 text-white shadow-green-300/50'
                              : 'bg-gray-200 text-gray-500'
                          }`}>
                          {isActive ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                          ) : isCompleted ? (
                            <CheckCircle className="w-5 h-5" />
                          ) : isFailed ? (
                            <X className="w-5 h-5" />
                          ) : (
                            check.stepNumber
                          )}
                        </div>
                        {/* Pulse ring for active step */}
                        {isActive && (
                          <div className="absolute inset-0 rounded-full bg-blue-400 animate-ping opacity-75" />
                        )}
                      </div>

                      <div className="flex-1 min-w-0 pt-0.5">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center space-x-2">
                            {!isActive && visuals.icon && (
                              <div className={`${isCompleted ? 'text-green-600' : isFailed ? 'text-red-600' : 'text-gray-400'}`}>
                                {visuals.icon}
                              </div>
                            )}
                            <span className={`font-semibold text-base ${isActive ? 'text-blue-900' :
                              isFailed ? 'text-red-900' :
                                isCompleted ? 'text-green-900' :
                                  'text-gray-800'
                              }`}>
                              {check.label}
                            </span>
                          </div>
                          <Badge
                            variant="outline"
                            className={`text-[10px] font-medium px-2.5 py-0.5 ${isActive
                              ? 'border-blue-300 text-blue-700 bg-blue-100/50'
                              : isFailed
                                ? 'border-red-300 text-red-700 bg-red-100/50'
                                : isCompleted
                                  ? 'border-green-300 text-green-700 bg-green-100/50'
                                  : 'border-gray-300 text-gray-600 bg-gray-50'
                              }`}
                          >
                            {visuals.label}
                          </Badge>
                        </div>

                        <p className={`text-sm leading-relaxed mt-1 ${isActive ? 'text-blue-800' :
                          isFailed ? 'text-red-800' :
                            isCompleted ? 'text-green-800' :
                              'text-gray-600'
                          }`}>
                          {check.description}
                        </p>

                        {/* Additional details for failed steps */}
                        {isFailed && validation && (
                          <div className="mt-3 p-2.5 rounded-lg bg-red-50/50 border border-red-200/50">
                            <p className="text-xs font-medium text-red-900 mb-1">Issue Details:</p>
                            <p className="text-xs text-red-700">
                              {check.key === 'virus' && validation.virusScan?.notes}
                              {check.key === 'phi' && validation.phiDetection?.notes}
                              {check.key === 'format' && validation.generalValidation?.notes}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Summary footer */}
        {status === 'valid' && (
          <div className="mt-4 p-3 rounded-lg bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200">
            <div className="flex items-center space-x-2">
              <CheckCircle className="w-5 h-5 text-green-600" />
              <p className="text-sm font-medium text-green-900">
                All validation checks passed successfully
              </p>
            </div>
          </div>
        )}

        {status === 'invalid' && (
          <div className="mt-4 p-3 rounded-lg bg-gradient-to-r from-red-50 to-rose-50 border border-red-200">
            <div className="flex items-center space-x-2">
              <ShieldAlert className="w-5 h-5 text-red-600" />
              <p className="text-sm font-medium text-red-900">
                Validation failed. Please review the issues above.
              </p>
            </div>
          </div>
        )}
      </div>
    );
  };

  // Validate files function (server-side validation)
  const validateFiles = async (filesToValidate) => {
    if (!filesToValidate || filesToValidate.length === 0) return;

    setValidating(true);

    // Initialize status for all files being validated
    const initialStatus = {};
    filesToValidate.forEach(file => {
      initialStatus[file.name] = 'validating';
    });
    setValidationStatus(prev => ({ ...prev, ...initialStatus }));

    // Helper function to validate a single file through all three stages
    const validateOneFile = async (file) => {
      try {
        // --- Stage 1: Virus Scan ---
        setValidationStatus(prev => ({ ...prev, [file.name]: 'scanning-virus' }));
        const virusFormData = new FormData();
        virusFormData.append('file', file);

        const virusScanResponse = await api.post('/validation/validate-upload/virus-scan', virusFormData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });

        if (!virusScanResponse.data?.success) {
          throw new Error(virusScanResponse.data?.error || 'Virus scan failed');
        }

        const virusScan = virusScanResponse.data.virusScan;
        setValidationResults(prev => ({
          ...prev,
          [file.name]: { ...prev[file.name], virusScan }
        }));

        if (!virusScan.isClean) {
          setValidationStatus(prev => ({ ...prev, [file.name]: 'invalid' }));
          toast({
            title: "Virus Scan Failed",
            description: `${file.name}: ${virusScan.notes || virusScan.status}`,
            variant: "destructive",
            duration: 8000,
          });
          return;
        }

        // --- Stage 2: Format and General Validation ---
        setValidationStatus(prev => ({ ...prev, [file.name]: 'validating-format' }));
        const formatFormData = new FormData();
        formatFormData.append('file', file);

        const formatResponse = await api.post('/validation/validate-upload/format-validation', formatFormData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });

        if (!formatResponse.data?.success) {
          throw new Error(formatResponse.data?.error || 'Format validation failed');
        }

        const generalValidation = formatResponse.data.generalValidation;
        const mimeValidation = formatResponse.data.mimeValidation;
        const formatWarnings = formatResponse.data.warnings || [];

        setValidationResults(prev => ({
          ...prev,
          [file.name]: { ...prev[file.name], generalValidation, mimeValidation, warnings: formatWarnings }
        }));

        if (generalValidation.status !== 'VALID') {
          setValidationStatus(prev => ({ ...prev, [file.name]: 'invalid' }));
          toast({
            title: "Format Validation Failed",
            description: `${file.name}: ${generalValidation.notes || generalValidation.status}`,
            variant: "destructive",
            duration: 8000,
          });
          return;
        }

        // --- Stage 3: PHI Detection ---
        setValidationStatus(prev => ({ ...prev, [file.name]: 'detecting-phi' }));
        const phiFormData = new FormData();
        phiFormData.append('file', file);

        const phiResponse = await api.post('/validation/validate-upload/phi-detection', phiFormData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });

        if (!phiResponse.data?.success) {
          throw new Error(phiResponse.data?.error || 'PHI detection failed');
        }

        const phiDetection = phiResponse.data.phiDetection;
        setValidationResults(prev => ({
          ...prev,
          [file.name]: { ...prev[file.name], phiDetection }
        }));

        // Combine all results
        const combinedValidation = {
          isValid: virusScan.isClean && generalValidation.status === 'VALID' && !phiDetection.containsPHI,
          overallStatus: virusScan.isClean && generalValidation.status === 'VALID' && !phiDetection.containsPHI ? 'PASSED' : 'FAILED',
          virusScan,
          generalValidation,
          mimeValidation,
          phiDetection,
          warnings: formatWarnings
        };

        // For compatibility with single-file expectations
        if (filesToValidate.length === 1) {
          setValidationData(combinedValidation);
          setPhiDetections(phiDetection?.detections || []);
        }

        if (!combinedValidation.isValid) {
          setValidationStatus(prev => ({ ...prev, [file.name]: 'invalid' }));

          const errorMessages = [];
          if (!virusScan.isClean) errorMessages.push("Infected file detected");
          if (generalValidation.status !== 'VALID') errorMessages.push("Invalid formatting");
          if (phiDetection.containsPHI) errorMessages.push("PHI patterns detected");

          toast({
            title: "Document Validation Failed",
            description: `${file.name}: ${errorMessages.join("; ") || 'Security violation'}`,
            variant: "destructive",
            duration: 8000,
          });
        } else {
          setValidationStatus(prev => ({ ...prev, [file.name]: 'valid' }));
          toast({
            title: "Document Validated",
            description: `${file.name} passed all security checks`,
            variant: "default",
            duration: 3000,
          });
        }

      } catch (error) {
        console.error(`Validation error for ${file.name}:`, error);
        setValidationStatus(prev => ({ ...prev, [file.name]: 'error' }));
        toast({
          title: "Validation Error",
          description: `Failed to validate ${file.name}: ${error.response?.data?.error || error.message}`,
          variant: "destructive",
        });
      }
    };

    try {
      // Validate all files in parallel (max 5)
      await Promise.all(filesToValidate.map(file => validateOneFile(file)));

      // Final summary toast for bulk
      if (filesToValidate.length > 1) {
        toast({
          title: "Bulk Validation Complete",
          description: `Finished processing ${filesToValidate.length} documents.`,
          variant: "default",
        });
      }
    } catch (err) {
      console.error('Parallel validation failed:', err);
    } finally {
      setValidating(false);
    }
  };

  // Enhanced AI analysis with content-based classification
  // 1. Updated Main Analysis Trigger
  const performAIAnalysis = async () => {
    if (uploading) return;

    // 1. Reset states
    setAiAnalysis({});
    setClassificationResults([]);
    setProcessingStatus({}); // Ensure this is cleared

    setUploading(true);
    setUploadProgress(0);
    setProgressStage('uploading');
    setProgressMessage('Starting AI analysis...');

    try {
      if (uploadMode === 'bulk') {
        await performBulkClassification();
      } else {
        // Ensure processing status is set for single mode too
        setProcessingStatus({ [files[0].name]: 'Processing...' });
        await performSingleClassification();
      }
      // Advance to Step 2
      setCurrentStep(2);
    } catch (error) {
      console.error('AI Analysis failed:', error);
      toast({
        title: "Analysis Failed",
        description: "AI could not process the file.",
        variant: "destructive"
      });
    } finally {
      setUploading(false);
    }
  };

  const performSingleClassification = async () => {
    const file = files[0];
    try {
      const formData = new FormData();
      // Make sure validationData is defined
      formData.append('payload', JSON.stringify(validationData || {}));
      formData.append('file', file);

      const response = await api.post('/gemini/classify-content', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      if (response.data.success) {
        const result = response.data;
        const fileName = file.name;

        // Update all related states consistently
        setAiAnalysis({ [fileName]: result.classification });
        setClassificationResults([{ fileName, result }]); // THIS IS KEY
        setConfidenceScores({ [fileName]: result.classification.confidence || 0 });
        setProcessingStatus({ [fileName]: 'Completed' });
        return true;
      }
    } catch (error) {
      setProcessingStatus({ [file.name]: 'Failed' });
      throw error;
    }
  };

  const performBulkClassification = async () => {
    try {
      setClassificationResults([]);
      setAiAnalysis({});
      setContentAnalysis({});
      setConfidenceScores({});

      setProgressStage('uploading');
      setProgressMessage(`Initializing analysis for ${files.length} documents...`);

      const batchSize = 2; // Process 2 files at a time to avoid overwhelming the server
      const results = [];

      for (let i = 0; i < files.length; i += batchSize) {
        const batch = files.slice(i, i + batchSize);
        const batchPromises = batch.map(async (file, batchIdx) => {
          const globalIdx = i + batchIdx;
          setProcessingStatus(prev => ({ ...prev, [file.name]: 'Processing...' }));
          setProgressMessage(`Analyzing document ${globalIdx + 1} of ${files.length}: ${file.name}...`);

          try {
            const formData = new FormData();
            // Pass the specific validation results for this file
            const fileValidation = validationResults[file.name] || {};
            formData.append('payload', JSON.stringify(fileValidation));
            formData.append('file', file);

            const response = await api.post('/gemini/classify-content', formData, {
              headers: { 'Content-Type': 'multipart/form-data' }
            });

            if (response.data.success) {
              const result = response.data;
              const fileName = file.name;

              setAiAnalysis(prev => ({ ...prev, [fileName]: result.classification }));
              setClassificationResults(prev => [...prev, { fileName, result }]);
              setContentAnalysis(prev => ({ ...prev, [fileName]: result.extractedContent }));
              setConfidenceScores(prev => ({ ...prev, [fileName]: result.classification.confidence }));
              setProcessingStatus(prev => ({ ...prev, [fileName]: 'Completed' }));

              return { success: true, fileName, result };
            } else {
              setProcessingStatus(prev => ({ ...prev, [file.name]: 'Failed' }));
              return { success: false, fileName: file.name, error: response.data.error };
            }
          } catch (error) {
            console.error(`Error classifying ${file.name}:`, error);
            setProcessingStatus(prev => ({ ...prev, [file.name]: 'Failed' }));
            return { success: false, fileName: file.name, error: error.message };
          }
        });

        const batchResults = await Promise.all(batchPromises);
        results.push(...batchResults);

        // Update overall progress
        const progress = Math.round(((i + batch.length) / files.length) * 100);
        setUploadProgress(progress);
      }

      const successfulCount = results.filter(r => r.success).length;

      toast({
        title: "Bulk Analysis Complete",
        description: `${successfulCount}/${files.length} documents classified successfully`,
        variant: successfulCount === files.length ? "default" : "warning"
      });

      // Automatically advance to classification step after successful analysis
      if (successfulCount > 0) {
        setTimeout(() => {
          setCurrentStep(2);
        }, 1500);
      }
    } catch (error) {
      console.error('Bulk classification error:', error);
      toast({
        title: "Bulk Analysis Failed",
        description: error.message || "Failed to process documents",
        variant: "destructive"
      });
    }
  };

  const handleManualClassification = (fileIndex, field, value) => {
    setManualClassification(prev => ({
      ...prev,
      [fileIndex]: {
        ...prev[fileIndex],
        [field]: value
      }
    }));
  };

  const proceedToReview = () => {
    setCurrentStep(3);
  };

  // Function to handle form submission
  const handleFormSubmit = async (data) => {
    try {
      if (files.length === 0) {
        toast({
          title: "Error",
          description: "No file available for upload",
          variant: "destructive"
        });
        return;
      }

      const file = files[0]; // For single file upload

      // Extract hierarchy data from form
      const metadata = {
        title: data.documentTitle || data.title || file.name.replace(/\.[^/.]+$/, ""),
        description: data.description || "N/A",
        documentType: data.documentType || "OTHER",
        tmfReference: data.tmfReference || "01.01.01",
        version: data.version || 1,
        documentDate: data.documentDate || new Date().toISOString().split('T')[0],
        author: data.author || "N/A",
        status: data.status || "DRAFT",
        qualityControlStatus: data.qualityControlStatus || "PENDING",
        completenessStatus: data.completenessStatus || "PENDING_REVIEW",
        zoneNumber: data.zoneNumber || "1",
        zoneName: data.zoneName || "",
        sectionNumber: data.sectionNumber || "",
        sectionName: data.sectionName || "",
        artifactNumber: data.artifactNumber || "",
        artifactName: data.artifactName || "",
        subArtifactName: data.subArtifactName || "",
        // Study/site references — scope to the currently selected study + site
        // (context) so the document is created in the same study+site the list filters by.
        study: selectedStudy || data.study || '',
        site: selectedSite || data.site || '',
        country: data.country || '',
        // TMF Metadata fields
        processBasedMetadata: data.processBasedMetadata || 'N/A',
        tmfLevel: data.tmfLevel || 'N/A',
        coreOrRecommended: data.coreOrRecommended || 'N/A',
        ichCode: data.ichCode || 'N/A',
        iso14155Reference: data.iso14155Reference || 'N/A',
        uniqueIdNumber: data.uniqueIdNumber || 'N/A',
        sponsorDocument: data.sponsorDocument || false,
        investigatorDocument: data.investigatorDocument || false,
        processNumber: data.processNumber || 'N/A',
        processName: data.processName || 'N/A',
        // Document Level Flags: Map 'X' or true to 'Yes', otherwise 'No'
        trialLevelDocument: (data.trialLevelDocument === 'X' || data.trialLevelDocument === true) ? 'Yes' : 'No',
        trialLevelMilestoneEvent: data.trialLevelMilestoneEvent || 'N/A',
        countryRegionLevelDocument: (data.countryRegionLevelDocument === 'X' || data.countryRegionLevelDocument === true) ? 'Yes' : 'No',
        countryLevelMilestoneEvent: data.countryLevelMilestoneEvent || 'N/A',
        siteLevelDocument: (data.siteLevelDocument === 'X' || data.siteLevelDocument === true) ? 'Yes' : 'No',
        siteLevelMilestoneEvent: data.siteLevelMilestoneEvent || 'N/A',
        pageCount: (data.pageCount && data.pageCount !== 'N/A') ? Number(data.pageCount) : 0,
        bypassChecks: true, // Allow PHI/validation warnings to be bypassed
        validationResult: validationData
      };

      // Use documentService.uploadDocument to upload to TMF documents API
      const result = await isfDocumentService.uploadDocument(file, metadata);

      if (!result.success) {
        // Handle duplicate document error with better UI
        if (result.error === 'DuplicateDocument') {
          setDuplicateError({
            existingDocumentId: result.existingDocumentId,
            fileName: file.name,
            message: result.message
          });
          return;
        }

        const { title, description } = formatUploadError(result, file.name);
        toast({
          title,
          description,
          variant: "destructive"
        });
        return;
      }

      recordSecurityInsight(file.name, result);

      toast({
        title: "Document Created",
        description: buildSecurityToastDescription(file.name, result),
        variant: "default"
      });

      // Call the upload complete callback
      if (onUploadComplete) {
        onUploadComplete();
      }

      // Close the drawer
      resetProgressState();
      onClose();
    } catch (error) {
      console.error('Form submission error:', error);
      toast({
        title: "Upload Failed",
        description: error.message || "Failed to upload document",
        variant: "destructive"
      });
    }
  };


  // Auto-trigger AI Analysis when validation is complete
  useEffect(() => {
    // Keep consistent with drawer state
    if (!isOpen) return;

    // Only proceed if we have files and haven't started analysis yet
    if (files.length === 0 || uploading || Object.keys(aiAnalysis).length > 0) return;

    // Check if we've already attempted processing (to avoid infinite loops on failure)
    const hasAttemptedProcessing = Object.keys(processingStatus).length > 0;
    if (hasAttemptedProcessing) return;

    // Check if validation is complete and successful for all files
    const allFilesValidated = files.every(file => validationStatus[file.name] === 'valid');

    if (allFilesValidated) {
      console.log('Auto-triggering AI Analysis after validation');
      performAIAnalysis();
    }
  }, [isOpen, files, validationStatus, uploading, aiAnalysis, processingStatus]);


  // Function to open DocumentDialog with AI classification data
  // Function to map AI classification results to DocumentDialog form data
  const mapAIToDocumentDialog = (classification, file, manualData = {}) => {
    console.log('=== Mapping AI/Manual to DocumentDialog ===', { classification, manualData });

    const { suggestedZone, suggestedSection, suggestedArtifact, extractedMetadata, documentType } = classification;

    // Map zone information (prioritize manualData)
    const zoneData = {
      zoneNumber: manualData.zone?.number || suggestedZone?.number || '',
      zoneName: manualData.zone?.name || suggestedZone?.name || '',
      zoneDescription: `AI - suggested zone: ${suggestedZone?.name || 'Unknown'} `
    };

    // Map section information
    const sectionData = {
      sectionNumber: manualData.section || suggestedSection || '',
      sectionName: sectionMapping[manualData.section || suggestedSection] || manualData.section || suggestedSection || '',
      sectionDescription: `AI - suggested section: ${suggestedSection || 'Unknown'} `
    };

    // Map artifact information
    const artifactHint = manualData.artifactNumber || manualData.artifact || suggestedArtifact;
    const { number: resolvedArtifactNumber, name: resolvedArtifactName } = resolveArtifactDetails(artifactHint);
    const artifactDataSub = artifactSubartifacts[resolvedArtifactNumber] || {};
    const artifactData = {
      artifactNumber: manualData.artifactNumber || resolvedArtifactNumber,
      artifactName: manualData.artifact || resolvedArtifactName,
      artifactDescription: `AI - suggested artifact: ${resolvedArtifactName || suggestedArtifact || 'N/A'} `,
      subArtifactName: manualData.subArtifactName || classification.suggestedSubartifact || 'N/A',
    };

    // Map document metadata
    const documentData = {
      documentTitle: manualData.title || extractedMetadata?.title || file.name.replace(/\.[^/.]+$/, ""),
      description: manualData.description || extractedMetadata?.description || 'N/A',
      documentType: manualData.documentType || documentType || 'OTHER',
      tmfReference: manualData.section || suggestedSection || 'N/A',
      version: manualData.version || extractedMetadata?.version || '1.0',
      documentDate: manualData.documentDate || extractedMetadata?.documentDate || new Date().toISOString().split('T')[0],
      approvalDate: null,
      author: manualData.author || extractedMetadata?.author || 'N/A',
      language: manualData.language || 'en',
      pageCount: extractedMetadata?.pageCount || 'N/A',
      status: manualData.status || 'DRAFT',
      qualityControlStatus: 'PENDING',
      completenessStatus: 'PENDING_REVIEW',
      archivalStatus: 'ACTIVE',
      gcpComplianceStatus: 'PENDING_REVIEW',
      mandatory: false,
      study: selectedStudy || '',
      site: selectedSite || '',
      country: '',
      indication: '',
      mimeType: file.type,
      uploadDate: new Date().toISOString().split('T')[0],
      // TMF Metadata flags
      trialLevelDocument: manualData.trialLevelDocument !== undefined ? manualData.trialLevelDocument : !!artifactDataSub.trialLevelDocument,
      trialLevelMilestoneEvent: manualData.trialLevelMilestoneEvent || artifactDataSub.trialLevelMilestone || 'N/A',
      countryRegionLevelDocument: manualData.countryRegionLevelDocument !== undefined ? manualData.countryRegionLevelDocument : !!artifactDataSub.countryLevelDocument,
      countryLevelMilestoneEvent: manualData.countryLevelMilestoneEvent || artifactDataSub.countryLevelMilestone || 'N/A',
      siteLevelDocument: manualData.siteLevelDocument !== undefined ? manualData.siteLevelDocument : !!artifactDataSub.siteLevelDocument,
      siteLevelMilestoneEvent: manualData.siteLevelMilestoneEvent || artifactDataSub.siteLevelMilestone || 'N/A'
    };

    return {
      type: 'document',
      data: {
        ...zoneData,
        ...sectionData,
        ...artifactData,
        ...documentData,
        hierarchy: {
          zone: manualData.zone || suggestedZone,
          section: { number: manualData.section || suggestedSection, name: sectionMapping[manualData.section || suggestedSection] },
          artifact: {
            number: manualData.artifactNumber || resolvedArtifactNumber || suggestedArtifact || '',
            name: manualData.artifact || resolvedArtifactName || suggestedArtifact || ''
          },
          subArtifact: manualData.subArtifactName || null
        },
        trialLevelDocument: documentData.trialLevelDocument,
        trialLevelMilestoneEvent: documentData.trialLevelMilestoneEvent,
        countryRegionLevelDocument: documentData.countryRegionLevelDocument,
        countryLevelMilestoneEvent: documentData.countryLevelMilestoneEvent,
        siteLevelDocument: documentData.siteLevelDocument,
        siteLevelMilestoneEvent: documentData.siteLevelMilestoneEvent
      }
    };
  };

  const openDocumentDialogWithAI = (fileIndex) => {
    console.log('=== Opening DocumentDialog (ISF) with AI/Manual Overrides ===');
    const file = files[fileIndex];
    const classification = aiAnalysis[file.name];
    const manualData = manualClassification[fileIndex] || {};

    if (!classification) {
      toast({
        title: "No Classification Data",
        description: "Please run AI analysis first",
        variant: "destructive"
      });
      return;
    }

    const dialogData = mapAIToDocumentDialog(classification, file, manualData);

    setSelectedFileForDialog(file);
    setAiClassificationForDialog(classification);
    setEditingFileIndex(fileIndex);
    setDocumentDialogOpen(true);
  };

  // Function to handle DocumentDialog submission
  const handleDocumentDialogSubmit = async (documentData) => {
    // If we are in classification review step, just update the manualClassification state
    if (currentStep === 2 && editingFileIndex !== null) {
      const resolvedArtifact = resolveArtifactDetails(documentData.artifactNumber || documentData.tmfReference);

      setManualClassification(prev => ({
        ...prev,
        [editingFileIndex]: {
          zone: { number: documentData.zoneNumber, name: documentData.zoneName },
          section: documentData.sectionNumber,
          artifact: documentData.artifactName || resolvedArtifact.name || documentData.subArtifactName || '',
          artifactNumber: documentData.artifactNumber || resolvedArtifact.number || '',
          documentType: documentData.documentType,
          title: documentData.documentTitle || documentData.title,
          description: documentData.description || 'N/A',
          version: documentData.version || '1.0',
          author: documentData.author || 'N/A',
          status: documentData.status || 'DRAFT',
          language: documentData.language || 'en',
          // Preserve TMF flags
          trialLevelDocument: documentData.trialLevelDocument,
          trialLevelMilestoneEvent: documentData.trialLevelMilestoneEvent,
          countryRegionLevelDocument: documentData.countryRegionLevelDocument,
          countryLevelMilestoneEvent: documentData.countryLevelMilestoneEvent,
          siteLevelDocument: documentData.siteLevelDocument,
          siteLevelMilestoneEvent: documentData.siteLevelMilestoneEvent
        }
      }));

      toast({
        title: "Document Details Updated",
        description: `Changes saved for ${selectedFileForDialog.name}`,
        variant: "default"
      });

      setDocumentDialogOpen(false);
      setEditingFileIndex(null);
      return;
    }

    try {
      // Extract metadata from documentData
      const metadata = {
        title: documentData.documentTitle || documentData.title || selectedFileForDialog.name.replace(/\.[^/.]+$/, ""),
        description: documentData.description || "N/A",
        documentType: documentData.documentType || "OTHER",
        tmfReference: documentData.tmfReference || "01.01.01",
        version: documentData.version || 1,
        documentDate: documentData.documentDate || new Date().toISOString().split('T')[0],
        author: documentData.author || "N/A",
        status: documentData.status || "DRAFT",
        qualityControlStatus: documentData.qualityControlStatus || "PENDING",
        completenessStatus: documentData.completenessStatus || "PENDING_REVIEW",
        zoneNumber: documentData.zoneNumber || "1",
        zoneName: documentData.zoneName || "",
        sectionNumber: documentData.sectionNumber || "",
        sectionName: documentData.sectionName || "",
        artifactNumber: documentData.artifactNumber || "",
        artifactName: documentData.artifactName || "",
        subArtifactName: documentData.subArtifactName || "",
        // Study/site references from the dialog data — fall back to the
        // currently selected site UUID so the doc matches the list's site filter.
        study: selectedStudy || documentData.study || '',
        site: selectedSite || documentData.site || '',
        country: documentData.country || '',
        // TMF Metadata flags - Map 'X' or true to 'Yes', otherwise 'No'
        trialLevelDocument: (documentData.trialLevelDocument === 'X' || documentData.trialLevelDocument === true) ? 'Yes' : 'No',
        trialLevelMilestoneEvent: documentData.trialLevelMilestoneEvent || 'N/A',
        countryRegionLevelDocument: (documentData.countryRegionLevelDocument === 'X' || documentData.countryRegionLevelDocument === true) ? 'Yes' : 'No',
        countryLevelMilestoneEvent: documentData.countryLevelMilestoneEvent || 'N/A',
        siteLevelDocument: (documentData.siteLevelDocument === 'X' || documentData.siteLevelDocument === true) ? 'Yes' : 'No',
        siteLevelMilestoneEvent: documentData.siteLevelMilestoneEvent || 'N/A',
        pageCount: (documentData.pageCount && documentData.pageCount !== 'N/A') ? Number(documentData.pageCount) : 0,
        bypassChecks: true
      };

      // Use documentService.uploadDocument to upload to TMF documents API
      const result = await documentService.uploadDocument(selectedFileForDialog, metadata);

      if (!result.success) {
        const { title, description } = formatUploadError(result, selectedFileForDialog.name);
        toast({
          title,
          description,
          variant: "destructive"
        });
        return;
      }

      recordSecurityInsight(selectedFileForDialog.name, result);

      toast({
        title: "Document Created",
        description: buildSecurityToastDescription(selectedFileForDialog.name, result),
        variant: "default"
      });

      // Close dialog and reset state
      setDocumentDialogOpen(false);
      setSelectedFileForDialog(null);
      setAiClassificationForDialog(null);

      // Call the upload complete callback
      if (onUploadComplete) {
        onUploadComplete();
      }
    } catch (error) {
      console.error('Document upload error:', error);
      toast({
        title: "Upload Failed",
        description: error.message || "Failed to upload document",
        variant: "destructive"
      });
    }
  };

  const handleUpload = async () => {
    try {
      setUploading(true);
      let successCount = 0;
      let failCount = 0;

      // Process each file for upload
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const fileIndex = i;

        // Get AI analysis and manual overrides
        const aiData = aiAnalysis[file.name] || {};
        const manualData = manualClassification[fileIndex] || {};

        // Resolve Artifact Details based on manual entry or AI suggestion
        const artifactHint = manualData.artifactNumber || manualData.artifact || aiData.suggestedArtifact;
        const resolvedArtifact = resolveArtifactDetails(artifactHint);
        const artifactDataSub = artifactSubartifacts[resolvedArtifact.number] || {};

        // Merge Logic: Prioritize Manual > AI > Default
        const zoneNumber = manualData.zone?.number || aiData.suggestedZone?.number || "1";
        const zoneName = manualData.zone?.name || aiData.suggestedZone?.name || "";
        const sectionNumber = manualData.section || aiData.suggestedSection || "";
        const sectionName = sectionMapping[sectionNumber] || "";
        const artifactNumber = manualData.artifactNumber || resolvedArtifact.number || "";
        const artifactName = manualData.artifact || resolvedArtifact.name || aiData.suggestedArtifact || "";

        // Construct Metadata matching the ISF Requirements
        const metadata = {
          title: manualData.title || aiData.extractedMetadata?.title || file.name.replace(/\.[^/.]+$/, ""),
          description: manualData.description || aiData.extractedMetadata?.description || "N/A",
          documentType: manualData.documentType || aiData.documentType || "OTHER",
          tmfReference: artifactNumber || sectionNumber || aiData.suggestedSection || "01.01.01",
          version: manualData.version || aiData.extractedMetadata?.version || "1.0",
          documentDate: manualData.documentDate || aiData.extractedMetadata?.documentDate || new Date().toISOString().split('T')[0],
          author: manualData.author || aiData.extractedMetadata?.author || "N/A",
          status: manualData.status || "DRAFT",
          qualityControlStatus: "PENDING",
          completenessStatus: "PENDING_REVIEW",
          zoneNumber: zoneNumber,
          zoneName: zoneName,
          sectionNumber: sectionNumber,
          sectionName: sectionName,
          artifactNumber: artifactNumber,
          artifactName: artifactName,
          subArtifactName: manualData.subArtifactName || aiData.suggestedSubartifact || "N/A",
          language: manualData.language || aiData.extractedMetadata?.language || "en",

          // Study context — fall back to the selected site UUID so the doc
          // matches the list's site filter (otherwise it's hidden).
          study: selectedStudy || "",
          site: selectedSite || manualData.site || "",
          country: manualData.country || "",

          // TMF Level Flags - Map boolean/X to Yes/No for the API
          trialLevelDocument: (manualData.trialLevelDocument || artifactDataSub.trialLevelDocument) ? 'Yes' : 'No',
          trialLevelMilestoneEvent: manualData.trialLevelMilestoneEvent || artifactDataSub.trialLevelMilestone || 'N/A',
          countryRegionLevelDocument: (manualData.countryRegionLevelDocument || artifactDataSub.countryLevelDocument) ? 'Yes' : 'No',
          countryLevelMilestoneEvent: manualData.countryLevelMilestoneEvent || artifactDataSub.countryLevelMilestone || 'N/A',
          siteLevelDocument: (manualData.siteLevelDocument || artifactDataSub.siteLevelDocument) ? 'Yes' : 'No',
          siteLevelMilestoneEvent: manualData.siteLevelMilestoneEvent || artifactDataSub.siteLevelMilestone || 'N/A',

          pageCount: aiData.extractedMetadata?.pageCount ? Number(aiData.extractedMetadata.pageCount) : 0,

          // CRITICAL: This allows files that failed PHI/Virus checks in Step 1 to be uploaded
          bypassChecks: true
        };

        try {
          // Use the correct ISF service
          const result = await isfDocumentService.uploadDocument(file, metadata);
          if (result.success) {
            successCount++;
            recordSecurityInsight(file.name, result);
          } else {
            failCount++;
            console.error(`ISF Upload failed for ${file.name}:`, result.error);
            toast({
              title: `Upload failed: ${file.name}`,
              description: result.message || "Unknown error",
              variant: "destructive"
            });
          }
        } catch (err) {
          failCount++;
          console.error(`Error in ISF upload loop for ${file.name}:`, err);
        }
      }

      if (successCount > 0) {
        toast({
          title: "ISF Bulk Upload Complete",
          description: `Successfully uploaded ${successCount} document(s). ${failCount > 0 ? `${failCount} failed.` : ''}`,
          variant: successCount > 0 && failCount === 0 ? "default" : "warning"
        });

        if (onUploadComplete) onUploadComplete();
        resetProgressState();
        onClose();
      }
    } catch (error) {
      console.error('Bulk Upload process crashed:', error);
      toast({
        title: "Process Failed",
        description: "An unexpected error occurred during bulk processing",
        variant: "destructive"
      });
    } finally {
      setUploading(false);
    }
  };

  const renderSecurityInsights = () => {
    if (!securityInsights.length) return null;
    return (
      <div className="space-y-3 mt-6">
        <div className="flex items-center space-x-2 text-gray-700">
          <ShieldCheck className="w-4 h-4 text-green-600" />
          <h4 className="font-medium">Recent Security Signals</h4>
        </div>
        <div className="space-y-2">
          {securityInsights.map((entry) => (
            <div
              key={entry.id}
              className="p-3 rounded-lg border border-gray-200 bg-gray-50"
            >
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold text-gray-900">{entry.fileName}</span>
                <span className="text-xs text-gray-500">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
              </div>
              {entry.mimeValidation && (
                <div className="mt-2 flex items-center space-x-2 text-xs text-gray-600">
                  <ShieldCheck className="w-3.5 h-3.5 text-green-600" />
                  <span>
                    Signature: {entry.mimeValidation.status || 'Pending'}
                    {entry.mimeValidation.detectedMimeType
                      ? ` (${entry.mimeValidation.detectedMimeType})`
                      : ''}
                  </span>
                </div>
              )}
              {entry.metadataSanitization?.actions?.length > 0 && (
                <div className="mt-1 flex items-center space-x-2 text-xs text-gray-600">
                  <Sparkles className="w-3.5 h-3.5 text-blue-500" />
                  <span>Scrubbed: {entry.metadataSanitization.actions.join(', ')}</span>
                </div>
              )}
              {entry.fileHash?.hash && (
                <div className="mt-1 flex items-center space-x-2 text-xs text-gray-600">
                  <Fingerprint className="w-3.5 h-3.5 text-gray-500" />
                  <span>
                    Hash ({entry.fileHash.algorithm || 'SHA-256'}):{' '}
                    {entry.fileHash.hash.slice(0, 16)}…
                  </span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderUploadStep = () => (
    <div className="space-y-6">
      <div className="text-center">
        <h3 className="text-lg font-semibold mb-2">Upload Documents ISF</h3>
        <p className="text-gray-600">Choose between single file or bulk upload (max 5 files)</p>
      </div>

      {/* Upload Mode Selection */}
      <div className="flex space-x-4 mb-6">
        <Button
          variant={uploadMode === 'single' ? 'default' : 'outline'}
          onClick={() => setUploadMode('single')}
          className="flex-1"
        >
          <FileText className="w-4 h-4 mr-2" />
          Single File
        </Button>
        <Button
          variant={uploadMode === 'bulk' ? 'default' : 'outline'}
          onClick={() => setUploadMode('bulk')}
          className="flex-1"
        >
          <Upload className="w-4 h-4 mr-2" />
          Bulk Upload (Max 5)
        </Button>
      </div>

      {/* File Upload Area */}
      <div
        className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
      >
        <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
        <p className="text-lg font-medium mb-2">
          {uploadMode === 'single' ? 'Drop a file here' : 'Drop files here (max 5)'}
        </p>
        <p className="text-gray-500 mb-4">
          Supported formats: PDF, Word, Excel, Text files
        </p>
        <Button
          onClick={() => fileInputRef.current?.click()}
          className="bg-blue-600 hover:bg-blue-700"
        >
          Choose Files
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          multiple={uploadMode === 'bulk'}
          onChange={handleFileSelect}
          className="hidden"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.csv"
        />
      </div>

      {/* Selected Files */}
      {files.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-medium">Selected Files ({files.length})</h4>
          {files.map((file, index) => {
            const status = validationStatus[file.name];
            const validation = validationResults[file.name];

            // Build detailed error messages
            const errorDetails = [];
            if (validation) {
              if (validation.virusScan && validation.virusScan.status !== 'CLEAN') {
                errorDetails.push({
                  type: 'Virus Scan',
                  message: validation.virusScan.notes || `Status: ${validation.virusScan.status}`,
                  details: [
                    !validation.virusScan.structureIntegrity && 'Structure integrity check failed',
                    !validation.virusScan.formatValidation && 'Format validation failed',
                    !validation.virusScan.contentSafety && 'Content safety check failed'
                  ].filter(Boolean)
                });
              }
              if (validation.generalValidation && validation.generalValidation.status !== 'VALID') {
                errorDetails.push({
                  type: 'General Validation',
                  message: validation.generalValidation.notes || `Status: ${validation.generalValidation.status}`,
                  details: [
                    !validation.generalValidation.fileSizeValid && 'File size exceeds 50MB limit',
                    !validation.generalValidation.fileTypeValid && 'File type not allowed',
                    !validation.generalValidation.fileNameValid && 'File name contains invalid characters'
                  ].filter(Boolean)
                });
              }
              if (validation.mimeValidation && validation.mimeValidation.status !== 'PASSED') {
                errorDetails.push({
                  type: 'File Signature',
                  message:
                    validation.mimeValidation.notes ||
                    `Detected ${validation.mimeValidation.detectedMime || 'unknown'} but declared ${validation.mimeValidation.declaredMime || 'unknown'}`,
                  details: validation.mimeValidation.errors || []
                });
              }
              if (validation.phiDetection && validation.phiDetection.containsPHI) {
                errorDetails.push({
                  type: 'PHI/PII Detection',
                  message: validation.phiDetection.notes || `Patient-level information detected (${validation.phiDetection.confidence}% confidence)`,
                  details: validation.phiDetection.indicators || []
                });
              }
              if (validation.errors && validation.errors.length > 0) {
                validation.errors.forEach(error => {
                  errorDetails.push({
                    type: 'Validation Error',
                    message: error,
                    details: []
                  });
                });
              }
            }

            return (
              <div key={index} className={`p-3 rounded-lg border ${status === 'valid'
                ? 'bg-green-50 border-green-200'
                : status === 'invalid'
                  ? 'bg-red-50 border-red-200'
                  : status === 'error'
                    ? 'bg-orange-50 border-orange-200'
                    : 'bg-gray-50 border-gray-200'
                }`}>
                <div className="flex items-start justify-between">
                  <div className="flex items-start space-x-3 flex-1 min-w-0">
                    <FileText className={`w-5 h-5 flex-shrink-0 mt-0.5 ${status === 'valid' ? 'text-green-600' : status === 'invalid' ? 'text-red-600' : 'text-blue-600'
                      }`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2">
                        <p className="font-medium truncate">{file.name}</p>
                        {status === 'validating' && (
                          <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-600 flex-shrink-0"></div>
                        )}
                        {status === 'valid' && (
                          <CheckCircle className="w-4 h-4 text-green-600 flex-shrink-0" />
                        )}
                        {status === 'invalid' && (
                          <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
                        )}
                        {status === 'error' && (
                          <AlertCircle className="w-4 h-4 text-orange-600 flex-shrink-0" />
                        )}
                      </div>
                      <div className="flex items-center space-x-2 mt-1">
                        <p className="text-sm text-gray-500">
                          {(file.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                        {status === 'validating' && (
                          <Badge variant="secondary" className="text-xs">Validating...</Badge>
                        )}
                        {status === 'valid' && (
                          <Badge variant="default" className="text-xs bg-green-100 text-green-700">Validated</Badge>
                        )}
                        {status === 'invalid' && (
                          <Badge variant="destructive" className="text-xs">Validation Failed</Badge>
                        )}
                        {status === 'error' && (
                          <Badge variant="destructive" className="text-xs">Validation Error</Badge>
                        )}
                      </div>

                      {renderValidationChecks(status, validation)}

                      {status === 'invalid' && renderValidationIssuePanel(file.name, errorDetails)}
                      {status === 'error' && (
                        <div className="mt-3 space-y-2 rounded-md border border-orange-100 bg-orange-50 px-3 py-2 text-xs text-orange-800">
                          <div className="flex items-center space-x-2">
                            <AlertCircle className="h-4 w-4 text-orange-600" />
                            <span className="font-semibold">Validation service unavailable</span>
                          </div>
                          <p>Please retry the upload. If the issue persists, contact support with the document name and timestamp.</p>
                        </div>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeFile(index)}
                    className="text-red-600 hover:text-red-700 flex-shrink-0"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {renderSecurityInsights()}

      {/* Enhanced Progress Bar */}
      {uploading && (
        <div className="space-y-3">
          <div className="flex justify-between text-sm">
            <span className="font-medium">{progressMessage}</span>
            <span>{Math.round(uploadProgress)}%</span>
          </div>
          <div className="space-y-2">
            <Progress
              value={progressStage === 'processing' ? 100 : uploadProgress}
              className="w-full"
            />
            {progressStage === 'processing' && (
              <div className="flex items-center space-x-2 text-sm text-blue-600">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                <span>AI is analyzing document content...</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Processing Status */}
      {Object.keys(processingStatus).length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-medium">Processing Status</h4>
            {uploadMode === 'bulk' && (
              <div className="text-sm text-gray-600">
                {Object.values(processingStatus).filter(status => status === 'Completed').length} / {files.length} Complete
              </div>
            )}
          </div>
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {Object.entries(processingStatus).map(([fileName, status]) => (
              <div key={fileName} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div className="flex items-center space-x-3">
                  <div className={`w-2 h-2 rounded-full ${status === 'Completed' ? 'bg-green-500' :
                    status === 'Failed' ? 'bg-red-500' :
                      'bg-yellow-500'
                    }`}></div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">{fileName}</div>
                    <div className="text-xs text-gray-500">
                      {/* Explicitly check if status exists before showing 'Failed' */}
                      {status === 'Queued' && 'Waiting to be processed...'}
                      {status === 'Processing' && 'AI is analyzing content...'}
                      {status === 'Completed' && 'Successfully classified'}
                      {status === 'Failed' && 'AI Analysis failed'}
                      {!status && 'Ready for analysis'}
                    </div>
                  </div>
                </div>
                <Badge variant={
                  status === 'Completed' ? 'default' :
                    status === 'Failed' ? 'destructive' :
                      'secondary'
                }>
                  {status}
                </Badge>
              </div>
            ))}
          </div>
          {uploadMode === 'bulk' && Object.values(processingStatus).some(status => status === 'Completed') && (
            <div className="bg-blue-50 p-3 rounded-lg border border-blue-200">
              <div className="flex items-center space-x-2">
                <Brain className="w-4 h-4 text-blue-600" />
                <div className="text-sm text-blue-800">
                  <span className="font-medium">
                    {Object.values(processingStatus).filter(status => status === 'Completed').length} documents
                  </span>
                  {' '}ready for review
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Auto-redirect Notification */}
      {progressStage === 'complete' && !uploading && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <div className="flex items-center space-x-2">
            <CheckCircle className="w-5 h-5 text-green-600" />
            <div>
              <p className="text-sm font-medium text-green-800">Analysis Complete!</p>
              <p className="text-xs text-green-600">Redirecting to classification step in a moment...</p>
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex justify-between">
        <Button variant="outline" onClick={() => {
          resetProgressState();
          onClose();
        }}>
          Cancel
        </Button>

        <div className="space-x-2">
          {/* Show the button ONLY if we haven't successfully classified yet */}
          {Object.keys(aiAnalysis).length === 0 && files.length > 0 && !uploading && (
            <Button
              onClick={performAIAnalysis}
              className={cn(
                "transition-all duration-300",
                files.some(f => validationStatus[f.name] === 'invalid')
                  ? "bg-orange-500 hover:bg-orange-600 text-white"
                  : "bg-blue-600 hover:bg-blue-700"
              )}
              // Disable if uploading or validating, but allow proceeding even if validation fails
              disabled={uploading || validating || files.some(f => validationStatus[f.name] === 'validating')}
            >
              <Brain className="w-4 h-4 mr-2" />
              {files.some(f => validationStatus[f.name] === 'invalid')
                ? 'Continue to Proceed'
                : 'Start AI Classification'}
            </Button>
          )}
        </div>
      </div>
    </div>
  );

  const renderClassificationStep = () => (
    <div className="space-y-6">
      <div className="text-center">
        <h3 className="text-lg font-semibold mb-2">AI-Powered Document Classification</h3>
        <p className="text-gray-600">
          {uploadMode === 'bulk'
            ? `Review and modify AI-generated information for ${files.length} documents`
            : 'Review and modify AI-generated document information'
          }
        </p>
      </div>

      {/* Bulk Upload Progress Summary */}
      {uploadMode === 'bulk' && classificationResults.length > 0 && (
        <div className="bg-gradient-to-r from-blue-50 to-green-50 p-4 rounded-lg border border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-blue-900 flex items-center">
                <Brain className="w-4 h-4 mr-2" />
                Bulk Analysis Complete
              </h4>
              <p className="text-sm text-blue-700 mt-1">
                {classificationResults.length} documents analyzed successfully
              </p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-blue-600">
                {Math.round(
                  Object.values(confidenceScores).reduce((sum, score) => sum + score, 0) /
                  Object.values(confidenceScores).length * 100
                )}%
              </div>
              <div className="text-xs text-blue-600">Avg Confidence</div>
            </div>
          </div>
        </div>
      )}

      {/* Single File Summary */}
      {uploadMode === 'single' && classificationResults.length > 0 && (
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-blue-900 flex items-center">
                <Brain className="w-4 h-4 mr-2" />
                AI Analysis Complete
              </h4>
              <p className="text-sm text-blue-700 mt-1">
                {classificationResults[0].result.classification.classificationReasoning}
              </p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-blue-600">
                {Math.round(classificationResults[0].result.classification.confidence * 100)}%
              </div>
              <div className="text-xs text-blue-600">Confidence</div>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Upload: Individual Document Forms */}
      {uploadMode === 'bulk' && classificationResults.length > 0 && (
        <div className="space-y-6">
          <div className="flex items-center justify-between bg-slate-100 p-4 rounded-xl border border-slate-200 shadow-sm">
            <h4 className="text-lg font-bold text-slate-800 flex items-center">
              <FileText className="w-5 h-5 mr-2 text-blue-600" />
              Document Analysis Results
            </h4>
            <div className="flex items-center space-x-3">
              <Button
                variant="default"
                size="sm"
                onClick={() => {
                  // Apply AI suggestions to all documents
                  classificationResults.forEach((result, index) => {
                    const classification = result.result.classification;
                    const fileName = result.fileName;
                    const resolvedArtifact = resolveArtifactDetails(classification.suggestedArtifact);

                    // Update manual classification with AI suggestions
                    setManualClassification(prev => ({
                      ...prev,
                      [index]: {
                        zone: classification.suggestedZone,
                        section: classification.suggestedSection,
                        artifact: resolvedArtifact.name || classification.suggestedArtifact || '',
                        artifactNumber: resolvedArtifact.number,
                        documentType: classification.documentType,
                        title: classification.extractedMetadata?.title || fileName.replace(/\.[^/.]+$/, ""),
                        description: classification.extractedMetadata?.description || 'N/A',
                        version: classification.extractedMetadata?.version || '1.0',
                        author: classification.extractedMetadata?.author || 'N/A',
                        status: 'DRAFT',
                        language: 'en'
                      }
                    }));
                  });

                  toast({
                    title: "AI Suggestions Applied",
                    description: "Applied AI suggestions to all documents",
                    variant: "default"
                  });
                }}
                className="bg-blue-600 hover:bg-blue-700 shadow-md transform transition hover:scale-105"
              >
                <Brain className="w-4 h-4 mr-2" />
                Apply AI to All
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={() => {
                  // Set all documents to Approved status
                  classificationResults.forEach((result, index) => {
                    setManualClassification(prev => ({
                      ...prev,
                      [index]: {
                        ...(prev[index] || {}),
                        status: 'APPROVED'
                      }
                    }));
                  });

                  toast({
                    title: "Status Updated",
                    description: "All documents set to Approved status",
                    variant: "default"
                  });
                }}
                className="bg-green-600 hover:bg-green-700 shadow-md transform transition hover:scale-105"
              >
                <CheckCircle className="w-4 h-4 mr-2" />
                Approve All
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  // Clear all manual classifications
                  setManualClassification({});
                  toast({
                    title: "Forms Reset",
                    description: "All forms have been reset to AI initial analysis",
                    variant: "default"
                  });
                }}
                className="text-slate-600 hover:text-red-600 hover:border-red-200"
              >
                <RotateCcw className="w-4 h-4 mr-2" />
                Reset All
              </Button>
            </div>
          </div>

          {/* Horizontal Document Selection Table */}
          <div className="bg-white border-2 border-slate-200 rounded-xl overflow-hidden shadow-sm mb-8">
            <div className="bg-slate-50 border-b border-slate-200 p-4 flex items-center justify-between">
              <h5 className="font-bold text-slate-900 flex items-center">
                <Table className="w-4 h-4 mr-2 text-blue-600" />
                ISF Bulk Classification Queue ({classificationResults.length} Documents)
              </h5>
              <div className="text-xs font-medium text-slate-500 uppercase tracking-wider">
                Select a document to inspect full metadata
              </div>
            </div>
            <div className="overflow-x-auto">
              <Table className="w-full text-sm">
                <TableHeader className="bg-slate-50/50">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="w-12 text-center font-bold text-slate-800 uppercase text-[10px]">#</TableHead>
                    <TableHead className="font-bold text-slate-800 uppercase text-[10px]">Document Name</TableHead>
                    <TableHead className="font-bold text-slate-800 uppercase text-[10px]">TMF Artifact</TableHead>
                    <TableHead className="font-bold text-slate-800 uppercase text-[10px]">Confidence</TableHead>
                    <TableHead className="font-bold text-slate-800 uppercase text-[10px]">Status</TableHead>
                    <TableHead className="text-right font-bold text-slate-800 uppercase text-[10px]">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {classificationResults.map((result, idx) => {
                    const fileName = result.fileName;
                    const classification = result.result.classification;
                    const confidence = confidenceScores[fileName] || 0.85;
                    const isActive = idx === activeBulkFileIndex;
                    const manualData = manualClassification[idx] || {};
                    const isApproved = (manualData.status || 'DRAFT') === 'APPROVED';
                    const resolvedArtifact = resolveArtifactDetails(classification.suggestedArtifact);

                    return (
                      <TableRow
                        key={idx}
                        className={cn(
                          "cursor-pointer transition-all duration-200 group",
                          isActive ? "bg-blue-50/80 border-l-4 border-l-blue-600" : "hover:bg-slate-50 border-l-4 border-l-transparent"
                        )}
                        onClick={() => setActiveBulkFileIndex(idx)}
                      >
                        <TableCell className="text-center font-bold text-slate-400">{idx + 1}</TableCell>
                        <TableCell className="font-bold text-slate-900">
                          <div className="flex items-center space-x-2">
                            <FileText className={cn("w-4 h-4", isActive ? "text-blue-600" : "text-slate-400")} />
                            <span className="truncate max-w-[200px]">{fileName}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-slate-600 font-medium whitespace-nowrap">
                          <Badge variant="outline" className="text-[10px] font-bold border-slate-200">
                            {resolvedArtifact.number || classification.suggestedSection || 'N/A'}
                          </Badge>
                          <span className="ml-2 truncate max-w-[150px] inline-block align-middle">{resolvedArtifact.name || classification.suggestedArtifact}</span>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1 bg-slate-200 rounded-full overflow-hidden">
                              <div
                                className={cn("h-full transition-all duration-500", confidence > 0.8 ? "bg-blue-500" : "bg-amber-500")}
                                style={{ width: `${Math.round(confidence * 100)}%` }}
                              />
                            </div>
                            <span className="text-[10px] font-black text-slate-600">{Math.round(confidence * 100)}%</span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge className={cn(
                            "uppercase text-[10px] px-2 h-5 font-bold tracking-tighter",
                            isApproved ? "bg-green-100 text-green-700 border-green-200" : "bg-blue-50 text-blue-700 border-blue-100"
                          )}>
                            {manualData.status || 'DRAFT'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm" className={cn(
                            "h-7 px-3 text-[10px] font-black uppercase tracking-widest",
                            isActive ? "bg-slate-900 text-white hover:bg-black" : "text-slate-400 group-hover:text-blue-600"
                          )}>
                            {isActive ? 'Active' : 'View Meta'}
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </div>

          {/* Detailed Document Classification View (Read-Only) */}
          <div className="space-y-6">
            {classificationResults.map((result, index) => {
              if (index !== activeBulkFileIndex) return null;

              const fileName = result.fileName;
              const classification = result.result.classification;
              const confidence = confidenceScores[fileName] || 0.85;
              const manualData = manualClassification[index] || {};
              const resolvedArtifact = resolveArtifactDetails(classification.suggestedArtifact);
              const metadata = classification.extractedMetadata || {};
              const artifactDataSub = artifactSubartifacts[resolvedArtifact.number] || {};

              return (
                <div key={index} className="bg-white border-2 border-slate-200 rounded-2xl overflow-hidden shadow-xl animate-in fade-in zoom-in duration-300">
                  {/* Header */}
                  <div className="bg-gradient-to-r from-slate-900 to-blue-900 p-8 flex items-center justify-between text-white">
                    <div className="flex items-center space-x-6">
                      <div className="h-16 w-16 rounded-2xl bg-blue-700 flex items-center justify-center border border-blue-500 shadow-lg">
                        <FileText className="w-8 h-8 text-blue-300" />
                      </div>
                      <div>
                        <div className="flex items-center space-x-3">
                          <h4 className="text-2xl font-black">{fileName}</h4>
                          <Badge className="bg-blue-400/20 text-blue-200 border-blue-400/30">
                            ISF Document
                          </Badge>
                        </div>
                        <p className="text-slate-300 font-medium mt-1 flex items-center">
                          <Brain className="w-4 h-4 mr-2 text-blue-400" />
                          {classification.documentType} • AI Confidence: {Math.round(confidence * 100)}%
                        </p>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <div className="flex items-center space-x-2 bg-slate-700 px-4 py-2 rounded-full border border-slate-600">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Status</span>
                        <Badge className={cn(
                          "uppercase text-[10px] px-3 h-6 font-bold",
                          (manualData.status || 'DRAFT') === 'APPROVED' ? "bg-green-500/20 text-green-300 border-green-500/30" : "bg-blue-500/20 text-blue-300 border-blue-500/30"
                        )}>
                          {manualData.status || 'DRAFT'}
                        </Badge>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-slate-400 hover:text-white hover:bg-slate-600 text-[10px] font-bold uppercase tracking-wider"
                        onClick={() => {
                          setManualClassification(prev => {
                            const next = { ...prev };
                            delete next[index];
                            return next;
                          });
                          toast({
                            title: "Reset Successful",
                            description: `Restored initial AI values for ${fileName}`,
                            variant: "default"
                          });
                        }}
                      >
                        <RotateCcw className="w-3 h-3 mr-2" />
                        Clear Manual Overrides
                      </Button>
                    </div>
                  </div>

                  <div className="p-8 space-y-10">
                    {/* Section 1: TMF Hierarchy */}
                    <div className="space-y-6">
                      <h6 className="text-[10px] font-black text-blue-600 uppercase tracking-[0.3em] flex items-center">
                        <span className="w-8 h-px bg-blue-100 mr-3"></span>
                        TMF Hierarchy Classification
                      </h6>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div className="space-y-2 group">
                          <Label className="text-[10px] font-bold text-slate-500 uppercase flex justify-between">
                            Zone Information
                            <span className="text-blue-500">AI Suggested</span>
                          </Label>
                          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 font-bold transition-all group-hover:border-blue-200 group-hover:bg-blue-50/30">
                            <span className="text-[10px] text-slate-400 block mb-1">Zone {classification.suggestedZone?.number}</span>
                            {classification.suggestedZone?.name || 'N/A'}
                          </div>
                        </div>
                        <div className="space-y-2 group">
                          <Label className="text-[10px] font-bold text-slate-500 uppercase flex justify-between">
                            Section Information
                            <span className="text-blue-500">AI Suggested</span>
                          </Label>
                          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 font-bold transition-all group-hover:border-blue-200 group-hover:bg-blue-50/30">
                            <span className="text-[10px] text-slate-400 block mb-1">Section {classification.suggestedSection}</span>
                            {sectionMapping[classification.suggestedSection] || 'N/A'}
                          </div>
                        </div>
                        <div className="space-y-2 group">
                          <Label className="text-[10px] font-bold text-slate-500 uppercase flex justify-between">
                            Artifact Information
                            <span className="text-blue-500">AI Suggested</span>
                          </Label>
                          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-900 font-bold transition-all group-hover:border-blue-200 group-hover:bg-blue-50/30 text-blue-700">
                            <span className="text-[10px] text-blue-400 block mb-1">Artifact {resolvedArtifact.number}</span>
                            {resolvedArtifact.name || classification.suggestedArtifact}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Section 2: Core Metadata & Process */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 border-t border-slate-100 pt-10">
                      <div className="space-y-6">
                        <h6 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em] flex items-center">
                          <span className="w-8 h-px bg-slate-100 mr-3"></span>
                          Document Metadata
                        </h6>
                        <div className="grid grid-cols-2 gap-6">
                          <div className="col-span-2 space-y-2">
                            <Label className="text-[10px] font-bold text-slate-500 uppercase">Document Title</Label>
                            <div className="p-3 bg-white border border-slate-200 rounded-xl text-sm text-slate-900 font-bold shadow-sm truncate">
                              {manualData.title || metadata.title || fileName.replace(/\.[^/.]+$/, "")}
                            </div>
                          </div>
                          <div className="space-y-2">
                            <Label className="text-[10px] font-bold text-slate-500 uppercase">Version Number</Label>
                            <div className="p-3 bg-white border border-slate-200 rounded-xl text-sm text-center text-slate-900 font-bold shadow-sm">
                              {manualData.version || metadata.version || '1.0'}
                            </div>
                          </div>
                          <div className="space-y-2">
                            <Label className="text-[10px] font-bold text-slate-500 uppercase">Document Date</Label>
                            <div className="p-3 bg-white border border-slate-200 rounded-xl text-sm text-slate-900 font-bold shadow-sm flex items-center justify-center">
                              <Calendar className="w-3 h-3 mr-2 text-slate-400" />
                              {manualData.documentDate || metadata.documentDate || 'N/A'}
                            </div>
                          </div>
                          <div className="col-span-2 space-y-2">
                            <Label className="text-[10px] font-bold text-slate-500 uppercase">Author / Owner</Label>
                            <div className="p-3 bg-white border border-slate-200 rounded-xl text-sm text-slate-900 font-bold shadow-sm">
                              {manualData.author || metadata.author || 'N/A'}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-6">
                        <h6 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em] flex items-center">
                          <span className="w-8 h-px bg-slate-100 mr-3"></span>
                          AI reasoning & Summary
                        </h6>
                        <div className="space-y-6">
                          <div className="p-5 bg-blue-50/50 border border-blue-100 rounded-2xl relative">
                            <Brain className="absolute top-4 right-4 w-10 h-10 text-blue-500/10" />
                            <Label className="text-[10px] font-black text-blue-700 uppercase mb-3 block tracking-wider">Classification Logic</Label>
                            <p className="text-xs text-blue-900 leading-relaxed font-bold italic">
                              "{classification.classificationReasoning || 'The document was classified based on its semantic content and structural characteristics matching the TMF reference model.'}"
                            </p>
                          </div>
                          <div className="space-y-2">
                            <Label className="text-[10px] font-bold text-slate-500 uppercase">Description / Purpose</Label>
                            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600 leading-relaxed min-h-[100px]">
                              {manualData.description || metadata.description || 'No detailed description extracted.'}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Section 3: TMF Metadata Flags (Detailed ISF view) */}
                    <div className="border-t border-slate-100 pt-10">
                      <h6 className="text-[10px] font-black text-slate-400 uppercase tracking-[0.3em] mb-6 flex items-center">
                        <span className="w-8 h-px bg-slate-100 mr-3"></span>
                        TMF Metadata Flags
                      </h6>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                        {/* Trial Level */}
                        <div className="p-6 rounded-2xl border border-slate-100 bg-slate-50/30 flex flex-col items-center text-center space-y-4">
                          <div className={cn("h-12 w-12 rounded-full flex items-center justify-center", artifactDataSub.trialLevelDocument ? "bg-blue-100 text-blue-600" : "bg-slate-100 text-slate-400")}>
                            <FileText className="w-6 h-6" />
                          </div>
                          <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Trial Level</p>
                            <p className="text-sm font-black text-slate-900">{artifactDataSub.trialLevelDocument ? 'YES' : 'NO'}</p>
                            <p className="text-[10px] text-slate-500 mt-2 font-medium">Milestone: <span className="text-slate-900 font-bold">{artifactDataSub.trialLevelMilestone || 'N/A'}</span></p>
                          </div>
                        </div>
                        {/* Country Level */}
                        <div className="p-6 rounded-2xl border border-slate-100 bg-slate-50/30 flex flex-col items-center text-center space-y-4">
                          <div className={cn("h-12 w-12 rounded-full flex items-center justify-center", artifactDataSub.countryLevelDocument ? "bg-blue-100 text-blue-600" : "bg-slate-100 text-slate-400")}>
                            <Globe className="w-6 h-6" />
                          </div>
                          <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Country Level</p>
                            <p className="text-sm font-black text-slate-900">{artifactDataSub.countryLevelDocument ? 'YES' : 'NO'}</p>
                            <p className="text-[10px] text-slate-500 mt-2 font-medium">Milestone: <span className="text-slate-900 font-bold">{artifactDataSub.countryLevelMilestone || 'N/A'}</span></p>
                          </div>
                        </div>
                        {/* Site Level */}
                        <div className="p-6 rounded-2xl border border-slate-100 bg-slate-50/30 flex flex-col items-center text-center space-y-4">
                          <div className={cn("h-12 w-12 rounded-full flex items-center justify-center", artifactDataSub.siteLevelDocument ? "bg-blue-100 text-blue-600" : "bg-slate-100 text-slate-400")}>
                            <MapPin className="w-6 h-6" />
                          </div>
                          <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase mb-1">Site Level</p>
                            <p className="text-sm font-black text-slate-900">{artifactDataSub.siteLevelDocument ? 'YES' : 'NO'}</p>
                            <p className="text-[10px] text-slate-500 mt-2 font-medium">Milestone: <span className="text-slate-900 font-bold">{artifactDataSub.siteLevelMilestone || 'N/A'}</span></p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-50 border-t border-slate-200 p-6 flex justify-between items-center">
                    <div className="flex items-center space-x-4">
                      <div className="flex flex-col">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Page Count</span>
                        <span className="text-sm font-black text-slate-900">{metadata.pageCount || 'N/A'}</span>
                      </div>
                      <div className="w-px h-8 bg-slate-200 mx-2"></div>
                      <div className="flex flex-col">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Last Modified</span>
                        <span className="text-sm font-black text-slate-900">{new Date(result.timestamp || Date.now()).toLocaleDateString()}</span>
                      </div>
                    </div>
                    <div className="text-[10px] font-black text-slate-300 uppercase italic">
                      Neurodoc ISF Intel Engine v4.0
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Single File: Complete DocumentDialog Form */}
      {
        uploadMode === 'single' && (
          <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
            {/* Zone Information Section */}
            <div className="space-y-4 bg-gray-50/50 p-6 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-2">
                <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center">
                  <span className="text-blue-600 font-semibold">1</span>
                </div>
                <h3 className="text-lg font-semibold text-gray-900">Zone Information</h3>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="zoneNumber" className="text-sm font-medium text-gray-700">Zone Number</Label>
                  <Input
                    id="zoneNumber"
                    placeholder="e.g., 1"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('zoneNumber')}
                    readOnly
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="zoneName" className="text-sm font-medium text-gray-700">Zone Name</Label>
                  <Input
                    id="zoneName"
                    placeholder="e.g., Trial Management"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('zoneName')}
                    readOnly
                  />
                </div>
              </div>
              {/* <div className="space-y-2">
              <Label htmlFor="zoneDescription" className="text-sm font-medium text-gray-700">Zone Description</Label>
              <Input
                id="zoneDescription"
                placeholder="e.g., High-level category"
                className="h-10 bg-gray-50 text-gray-500"
                {...register('zoneDescription')}
                readOnly
              />
            </div>*/}
            </div>

            {/* Section Information */}
            <div className="space-y-4 bg-gray-50/50 p-6 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-2">
                <div className="h-8 w-8 rounded-full bg-green-100 flex items-center justify-center">
                  <span className="text-green-600 font-semibold">2</span>
                </div>
                <h3 className="text-lg font-semibold text-gray-900">Section Information</h3>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="sectionNumber" className="text-sm font-medium text-gray-700">Section Number</Label>
                  <Input
                    id="sectionNumber"
                    placeholder="e.g., 01.01"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('sectionNumber')}
                    readOnly
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sectionName" className="text-sm font-medium text-gray-700">Section Name</Label>
                  <Input
                    id="sectionName"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('sectionName')}
                    readOnly
                  />
                </div>
              </div>
              {/* <div className="space-y-2">
            <Label htmlFor="sectionDescription" className="text-sm font-medium text-gray-700">Section Description</Label>
            <Input
              id="sectionDescription"
              placeholder="e.g., Sub-category"
              className="h-10 bg-gray-50 text-gray-500"
              {...register('sectionDescription')}
              readOnly
            />
          </div>*/}
            </div>

            {/* Artifact Information */}
            <div className="space-y-4 bg-gray-50/50 p-6 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-2">
                <div className="h-8 w-8 rounded-full bg-purple-100 flex items-center justify-center">
                  <span className="text-purple-600 font-semibold">3</span>
                </div>
                <h3 className="text-lg font-semibold text-gray-900">Artifact Information</h3>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="artifactNumber" className="text-sm font-medium text-gray-700">Artifact Number</Label>
                  <Input
                    id="artifactNumber"
                    placeholder="e.g., 01.01.01"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('artifactNumber')}
                    readOnly
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="artifactName" className="text-sm font-medium text-gray-700">Artifact Name</Label>
                  <Input
                    id="artifactName"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('artifactName')}
                    readOnly
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="subArtifactName" className="text-sm font-medium text-gray-700">Sub-Artifact</Label>
                <Input
                  id="subArtifactName"
                  className="h-10 bg-gray-50 text-gray-500"
                  {...register('subArtifactName')}
                  readOnly
                />
              </div>
              {/* <div className="space-y-2">
              <Label htmlFor="artifactDescription" className="text-sm font-medium text-gray-700">Artifact Description</Label>
              <Input
                id="artifactDescription"
                placeholder="e.g., Document expected here"
                className="h-10 bg-gray-50 text-gray-500"
                {...register('artifactDescription')}
                readOnly
              />
            </div>*/}
              <div className="flex items-center space-x-2 pt-2">
                <input
                  type="checkbox"
                  id="mandatory"
                  {...register('mandatory')}
                  className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  disabled
                />
                <Label htmlFor="mandatory" className="text-sm font-medium text-gray-700">Mandatory Document</Label>
              </div>
            </div>

            {/* Document Information */}
            <div className="space-y-4 bg-gray-50/50 p-6 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-2">
                <div className="h-8 w-8 rounded-full bg-orange-100 flex items-center justify-center">
                  <span className="text-orange-600 font-semibold">4</span>
                </div>
                <h3 className="text-lg font-semibold text-gray-900">Document Information</h3>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="documentType" className="text-sm font-medium text-gray-700">Document Type</Label>
                  <Input
                    id="documentType"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('documentType')}
                    readOnly
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="tmfReference" className="text-sm font-medium text-gray-700">TMF Reference</Label>
                  <Input
                    id="tmfReference"
                    placeholder="Enter TMF reference"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('tmfReference')}
                    readOnly
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="version" className="text-sm font-medium text-gray-700">Version</Label>
                  <Input
                    id="version"
                    placeholder="e.g., 1.0"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('version')}
                    readOnly
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="status" className="text-sm font-medium text-gray-700">Status</Label>
                  <Input
                    id="status"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('status')}
                    readOnly
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="documentDate" className="text-sm font-medium text-gray-700">Document Date</Label>
                  <Input
                    id="documentDate"
                    type="date"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('documentDate')}
                    readOnly
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="approvalDate" className="text-sm font-medium text-gray-700">Approval Date</Label>
                  <Input
                    id="approvalDate"
                    type="date"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('approvalDate')}
                    readOnly
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="language" className="text-sm font-medium text-gray-700">Language</Label>
                  <Input
                    id="language"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('language')}
                    readOnly
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="pageCount" className="text-sm font-medium text-gray-700">Page Count</Label>
                  <Input
                    id="pageCount"
                    type="number"
                    placeholder="Enter page count"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('pageCount')}
                    readOnly
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="documentTitle" className="text-sm font-medium text-gray-700">Document Title</Label>
                  <Input
                    id="documentTitle"
                    placeholder="Enter document title"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('documentTitle')}
                    readOnly
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="author" className="text-sm font-medium text-gray-700">Author</Label>
                  <Input
                    id="author"
                    placeholder="Enter author name"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('author')}
                    readOnly
                  />
                </div>
              </div>
            </div>

            {/* TMF Metadata Section */}
            <div className="space-y-6 bg-gray-50/50 p-6 rounded-lg border border-gray-100">
              <div className="flex items-center space-x-2">
                <div className="h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center">
                  <span className="text-indigo-600 font-semibold">5</span>
                </div>
                <h3 className="text-lg font-semibold text-gray-900">TMF Metadata</h3>
              </div>

              {/* 1. Basic Classification */}
              <div className="space-y-4 rounded-lg border border-blue-100 bg-blue-50/30 p-4">
                <h4 className="text-sm font-semibold text-gray-900 flex items-center">
                  <span className="mr-2">📋</span>
                  Basic Classification
                </h4>
                <div className="space-y-2">
                  <Label htmlFor="processBasedMetadata" className="text-sm font-medium text-gray-700">
                    Definition / Purpose
                  </Label>
                  <Textarea
                    id="processBasedMetadata"
                    placeholder="Document definition and purpose (auto-populated from TMF Reference Model)"
                    className="min-h-[80px] bg-gray-50 text-gray-500"
                    {...register('processBasedMetadata')}
                    readOnly
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="tmfLevel" className="text-sm font-medium text-gray-700">TMF Level</Label>
                    <Input
                      id="tmfLevel"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('tmfLevel')}
                      readOnly
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="coreOrRecommended" className="text-sm font-medium text-gray-700">
                      Core or Recommended
                    </Label>
                    <Input
                      id="coreOrRecommended"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('coreOrRecommended')}
                      readOnly
                    />
                  </div>
                </div>
              </div>

              {/* 2. Regulatory References */}
              <div className="space-y-4 rounded-lg border border-green-100 bg-green-50/30 p-4">
                <h4 className="text-sm font-semibold text-gray-900 flex items-center">
                  <span className="mr-2">📜</span>
                  Regulatory References
                </h4>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="ichCode" className="text-sm font-medium text-gray-700">ICH Code</Label>
                    <Input
                      id="ichCode"
                      placeholder="e.g., 5.5.7"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('ichCode')}
                      readOnly
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="iso14155Reference" className="text-sm font-medium text-gray-700">
                      ISO 14155 Reference
                    </Label>
                    <Input
                      id="iso14155Reference"
                      placeholder="Device studies reference"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('iso14155Reference')}
                      readOnly
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="uniqueIdNumber" className="text-sm font-medium text-gray-700">Unique ID Number</Label>
                  <Input
                    id="uniqueIdNumber"
                    placeholder="Enter unique ID number"
                    className="h-10 bg-gray-50 text-gray-500"
                    {...register('uniqueIdNumber')}
                    readOnly
                  />
                </div>
              </div>

              {/* 3. Document Type Flags */}
              <div className="space-y-4 rounded-lg border border-purple-100 bg-purple-50/30 p-4">
                <h4 className="text-sm font-semibold text-gray-900 flex items-center">
                  <span className="mr-2">🏷️</span>
                  Document Type Flags
                </h4>
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="sponsorDocument"
                      {...register('sponsorDocument')}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      disabled
                    />
                    <Label htmlFor="sponsorDocument" className="text-sm font-medium text-gray-700">
                      Sponsor Document
                    </Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="investigatorDocument"
                      {...register('investigatorDocument')}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      disabled
                    />
                    <Label htmlFor="investigatorDocument" className="text-sm font-medium text-gray-700">
                      Investigator Document
                    </Label>
                  </div>
                </div>
              </div>

              {/* 4. Process Information */}
              <div className="space-y-4 rounded-lg border border-amber-100 bg-amber-50/30 p-4">
                <h4 className="text-sm font-semibold text-gray-900 flex items-center">
                  <span className="mr-2">⚙️</span>
                  Process Information
                </h4>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="processNumber" className="text-sm font-medium text-gray-700">Process Number</Label>
                    <Input
                      id="processNumber"
                      placeholder="e.g., 12"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('processNumber')}
                      readOnly
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="processName" className="text-sm font-medium text-gray-700">Process Name</Label>
                    <Input
                      id="processName"
                      placeholder="e.g., Develop Trial Management Strategy"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('processName')}
                      readOnly
                    />
                  </div>
                </div>
              </div>

              {/* 5. Document Level Flags */}
              <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50/50 p-4">
                <h4 className="text-sm font-semibold text-gray-900 flex items-center mb-3">
                  <span className="mr-2">📍</span>
                  Document Level Flags
                </h4>
                <div className="grid grid-cols-3 gap-4">
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="trialLevelDocument"
                      {...register('trialLevelDocument')}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      disabled
                    />
                    <Label htmlFor="trialLevelDocument" className="text-sm font-medium text-gray-700">
                      Trial Level
                    </Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="countryRegionLevelDocument"
                      {...register('countryRegionLevelDocument')}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      disabled
                    />
                    <Label htmlFor="countryRegionLevelDocument" className="text-sm font-medium text-gray-700">
                      Country/Region Level
                    </Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="siteLevelDocument"
                      {...register('siteLevelDocument')}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      disabled
                    />
                    <Label htmlFor="siteLevelDocument" className="text-sm font-medium text-gray-700">
                      Site Level
                    </Label>
                  </div>
                </div>
              </div>

              {/* 6. Milestones & Events */}
              <div className="space-y-4 rounded-lg border border-indigo-100 bg-indigo-50/30 p-4">
                <h4 className="text-sm font-semibold text-gray-900 flex items-center mb-3">
                  <span className="mr-2">📅</span>
                  Milestones & Events
                </h4>
                <div className="grid grid-cols-1 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="trialLevelMilestoneEvent" className="text-sm font-medium text-gray-700">
                      Trial Level MILESTONE/EVENT
                    </Label>
                    <Input
                      id="trialLevelMilestoneEvent"
                      placeholder="e.g., 02 Clinical Infrastructure Ready"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('trialLevelMilestoneEvent')}
                      readOnly
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="countryLevelMilestoneEvent" className="text-sm font-medium text-gray-700">
                      Country Level MILESTONE/EVENT
                    </Label>
                    <Input
                      id="countryLevelMilestoneEvent"
                      placeholder="e.g., 01 First Country RA Approval"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('countryLevelMilestoneEvent')}
                      readOnly
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="siteLevelMilestoneEvent" className="text-sm font-medium text-gray-700">
                      Site Level MILESTONE/EVENT
                    </Label>
                    <Input
                      id="siteLevelMilestoneEvent"
                      placeholder="Enter site level milestone/event"
                      className="h-10 bg-gray-50 text-gray-500"
                      {...register('siteLevelMilestoneEvent')}
                      readOnly
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex justify-between pt-6">
              <Button type="button" variant="outline" onClick={() => setCurrentStep(1)}>
                Back
              </Button>
              <div className="space-x-2">
                <Button type="submit" disabled={isSubmitting} className="h-10 px-6">
                  {isSubmitting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    'Create Document'
                  )}
                </Button>
              </div>
            </div>
          </form>
        )
      }

      {/* Action Buttons for Bulk Upload */}
      {
        uploadMode === 'bulk' && (
          <div className="flex justify-between pt-6">
            <Button type="button" variant="outline" onClick={() => setCurrentStep(1)}>
              Back
            </Button>
            <div className="space-x-2">
              <Button
                onClick={() => {
                  console.log('[AIUploadDrawer] Continue button clicked', {
                    classificationResultsLength: classificationResults.length,
                    currentStep,
                    filesLength: files.length
                  });
                  proceedToReview();
                }}
                disabled={classificationResults.length === 0 || files.length === 0}
                className="bg-green-600 hover:bg-green-700"
              >
                <ArrowRight className="w-4 h-4 mr-2" />
                Continue to Review
              </Button>
            </div>
          </div>
        )
      }

      {/* Form Completion Summary */}
      <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">
                {Object.keys(manualClassification).length}
              </div>
              <div className="text-xs text-gray-600">Forms Filled</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {Object.values(manualClassification).filter(data => data.status === 'APPROVED').length}
              </div>
              <div className="text-xs text-gray-600">Approved</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-orange-600">
                {classificationResults.length - Object.keys(manualClassification).length}
              </div>
              <div className="text-xs text-gray-600">Pending</div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-sm text-gray-600">Completion Progress</div>
            <div className="text-lg font-semibold text-gray-900">
              {Math.round((Object.keys(manualClassification).length / classificationResults.length) * 100)}%
            </div>
          </div>
        </div>
      </div>
    </div >
  );

  const renderReviewStep = () => (
    <div className="space-y-6">
      <div className="text-center">
        <h3 className="text-lg font-semibold mb-2">Review & Upload</h3>
        <p className="text-gray-600">Review final classifications before uploading</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center space-x-2">
              <FileText className="w-5 h-5 text-blue-600" />
              <div>
                <p className="text-sm text-gray-500">Total Files</p>
                <p className="text-lg font-semibold">{files.length}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center space-x-2">
              <Target className="w-5 h-5 text-green-600" />
              <div>
                <p className="text-sm text-gray-500">Avg Confidence</p>
                <p className="text-lg font-semibold">
                  {Object.values(confidenceScores).length > 0
                    ? Math.round(Object.values(confidenceScores).reduce((a, b) => a + b, 0) / Object.values(confidenceScores).length * 100)
                    : 0}%
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center space-x-2">
              <TrendingUp className="w-5 h-5 text-purple-600" />
              <div>
                <p className="text-sm text-gray-500">Ready to Upload</p>
                <p className="text-lg font-semibold text-green-600">✓</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Final Review List */}
      <div className="space-y-3">
        <h4 className="font-medium">Upload Summary</h4>
        {classificationResults.map((result, index) => {
          const fileName = result.fileName;
          const classification = result.result.classification;
          const hierarchy = selectedHierarchy[index];

          return (
            <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
              <div className="flex items-center space-x-3">
                <FileText className="w-5 h-5 text-blue-600" />
                <div>
                  <p className="font-medium">{fileName}</p>
                  <p className="text-sm text-gray-500">
                    {classification.documentType} • Zone {classification.suggestedZone.number} • {hierarchy?.section || 'Not specified'}
                  </p>
                </div>
              </div>
              <Badge variant={classification.confidence > 0.8 ? 'default' : 'secondary'}>
                {Math.round(classification.confidence * 100)}%
              </Badge>
            </div>
          );
        })}
      </div>

      {/* Action Buttons */}
      <div className="flex justify-between">
        <Button variant="outline" onClick={() => setCurrentStep(2)}>
          Back
        </Button>
        <div className="space-x-2">
          <Button variant="outline" onClick={() => {
            resetProgressState();
            onClose();
          }}>
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={uploading}
            className="bg-green-600 hover:bg-green-700"
          >
            {uploading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="w-4 h-4 mr-2" />
                Upload Documents
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <div className="h-full flex flex-col">
        {/* Scrollable Content Area */}
        <div className="flex-1 overflow-y-auto p-6 max-h-[calc(100vh-120px)]">
          <div className="space-y-6">
            {currentStep === 1 && renderUploadStep()}
            {currentStep === 2 && renderClassificationStep()}
            {currentStep === 3 && renderReviewStep()}
          </div>
        </div>
      </div>

      {/* DocumentDialog Integration */}
      <DocumentDialog
        open={documentDialogOpen}
        initialSelectedItem={selectedFileForDialog ? mapAIToDocumentDialog(aiClassificationForDialog, selectedFileForDialog) : null}
        onClose={() => {
          setDocumentDialogOpen(false);
          setSelectedFileForDialog(null);
          setAiClassificationForDialog(null);
        }}
        onSubmit={handleDocumentDialogSubmit}
      />

      {/* Duplicate Document Dialog */}
      <DuplicateDocumentDialog
        open={!!duplicateError}
        onOpenChange={(open) => {
          if (!open) {
            setDuplicateError(null);
          }
        }}
        existingDocumentId={duplicateError?.existingDocumentId}
        fileName={duplicateError?.fileName}
        message={duplicateError?.message}
        onCancel={() => {
          setDuplicateError(null);
        }}
      />
    </>
  );
};

export default AIUploadDrawer;