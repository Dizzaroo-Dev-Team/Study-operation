import React, { useMemo, useState } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { useToast } from "@/components/ui/use-toast";
import {
  CheckCircle2,
  AlertCircle,
  ClipboardCheck,
  User,
  AlertTriangle,
  FileText,
  Info,
  ShieldCheck,
  FileSearch,
  Layers,
  Upload,
  Calendar,
  Globe,
  Hash,
  Building2,
  CheckCheck,
  XCircle,
  Clock,
  File,
  HardDrive,
  Fingerprint,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Eye,
  Shield,
  FolderTree,
  Tag,
  FileType,
  Link2,
  MapPin,
  Users,
  Activity,
  FileX,
  Plus,
  Trash2,
  Mail
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import useTmfHierarchy from '../../../hooks/useTmfHierarchy';
import { normalizeTMF } from '@/utils/tmfHierarchyUtils';
import tmfService from "../../../services/tmf.service";

// const CHECKLIST_ITEMS = [
//   {
//     key: "intakeReportReviewed",
//     label: "Intake report reviewed",
//     description: "Confirm all intake data has been reviewed and validated.",
//   },
//   {
//     key: "metadataVerified",
//     label: "TMF metadata verified",
//     description: "Confirm TMF classification (Zone, Section, Artifact) is correct.",
//   },
//   {
//     key: "securityChecksConfirmed",
//     label: "Security checks confirmed",
//     description: "Verify duplicate check and virus scan results are acceptable.",
//   },
// ];

const QcValidationForm = ({
  draft,
  updateDraft,
  studyTitle,
  disabled = false,
  canMarkComplete,
  isLoading,
  intakeData,
  document,
  onReplaceDocument,
}) => {
  const { toast } = useToast();
  const { hierarchyData } = useTmfHierarchy();
  const [expandedSections, setExpandedSections] = useState({
    document: true,
    security: true,
    tmfStructure: true,
    tmfMetadata: false,
    fileInfo: false,
    ingestion: true,
    reviewStages: false,
    sponsorPersons: false,
  });

  const [qcDecision, setQcDecision] = useState(null);
  const [actualEffectiveDate, setActualEffectiveDate] = useState("");
  const [publicationStatus, setPublicationStatus] = useState("UNPUBLISHED");

  React.useEffect(() => {
    // Initialize qcDecision from draft if it exists
    if (draft?.qcDecision) {
      setQcDecision(draft.qcDecision);
    }
    if (draft?.actualEffectiveDate) {
      setActualEffectiveDate(draft.actualEffectiveDate);
    }
    if (draft?.publicationStatus) {
      setPublicationStatus(draft.publicationStatus);
    }

    setSendToTmf(draft?.sendToTmf || false);
  setSendToSafety(draft?.sendToSafety || false);
  setSafetyCcEmails(draft?.safetyCcEmails || []);
  }, [draft]);

  const isQcComplete = useMemo(() => {
    return qcDecision !== null;
  }, [qcDecision]);

  const toggleSection = (section) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  // const onChecklistChange = (key) => (checked) => {
  //   updateDraft((prev) => ({
  //     ...prev,
  //     checklist: {
  //       ...prev.checklist,
  //       [key]: checked === true,
  //     },
  //   }));
  // };

  const onInputChange = (field) => (event) => {
    updateDraft({ [field]: event.target.value });
  };

  const [sendToTmf, setSendToTmf] = useState(draft?.sendToTmf || false);
  const [sendToSafety, setSendToSafety] = useState(draft?.sendToSafety || false); // New state
  const [safetyCcEmails, setSafetyCcEmails] = useState(draft?.safetyCcEmails || []);
  const [newCcEmail, setNewCcEmail] = useState("");
  const [tmfSending, setTmfSending] = useState(false);
  const [tmfError, setTmfError] = useState(null);

  const handleToggleTmf = async () => {
    // If already enabled, clicking toggles it off without calling the API again.
    if (sendToTmf) {
      setSendToTmf(false);
      updateDraft({ sendToTmf: false });
      return;
    }

    // Enabling: publish the full document payload to the Data Platform (Kafka).
    setTmfError(null);
    if (!document || !document.documentId) {
      toast({
        title: "Cannot route to TMF",
        description: "This document is missing a documentId. Please save the document and try again.",
        variant: "destructive",
      });
      return;
    }

    try {
      setTmfSending(true);
      await tmfService.sendToTmf({
        documentId: document.documentId,
        studyId: document.study || null,
        studyNumber: document.studyNumber || document.study || null,
      });

      setSendToTmf(true);
      updateDraft({ sendToTmf: true });

      toast({
        title: "TMF routing enabled",
        description: "Document payload published to the TMF pipeline.",
        variant: "default",
      });
    } catch (error) {
      const message =
        error?.response?.data?.detail ||
        error?.response?.data?.error ||
        error?.message ||
        "Failed to route document to TMF.";
      setTmfError(message);
      toast({
        title: "TMF routing failed",
        description: message,
        variant: "destructive",
      });
    } finally {
      setTmfSending(false);
    }
  };

const handleToggleSafety = () => {
  const newValue = !sendToSafety;
  setSendToSafety(newValue);
  // Tell the parent to update the flattened field
  updateDraft({ sendToSafety: newValue });
};

  const handleAddCcEmail = () => {
    if (sendToSafety && newCcEmail && /^\S+@\S+\.\S+$/.test(newCcEmail)) {
      const updated = [...safetyCcEmails, newCcEmail];
      setSafetyCcEmails(updated);
      updateDraft({ safetyCcEmails: updated });
      setNewCcEmail("");
    }
  };

  const handleRemoveCcEmail = (e, index) => {
    e.preventDefault();
    e.stopPropagation();
    const updated = safetyCcEmails.filter((_, i) => i !== index);
    setSafetyCcEmails(updated);
    updateDraft({ safetyCcEmails: updated });
  };

  // const completionPercentage = useMemo(() => {
  //   const completed = CHECKLIST_ITEMS.filter((item) => draft.checklist?.[item.key]).length;
  //   return Math.round((completed / CHECKLIST_ITEMS.length) * 100);
  // }, [draft.checklist]);

  // const allChecklistComplete = useMemo(() => {
  //   return CHECKLIST_ITEMS.every((item) => draft.checklist?.[item.key]);
  // }, [draft.checklist]);

  const intakeReport = useMemo(() => {
    if (!intakeData) return null;
    const duplicateCheck = intakeData.duplicateCheck || {};
    const virusScan = intakeData.virusScan || {};
    const metadataVerification = intakeData.metadataVerification || {};
    const extractedMetadata = intakeData.extractedMetadata || {};

    return {
      ingestionMethod: intakeData.ingestionMethod || "MANUAL_UPLOAD",
      sourceSystem: intakeData.sourceSystem || null,
      duplicateStatus: duplicateCheck.status || "PENDING",
      duplicateMatchedId: duplicateCheck.matchedDocumentId || null,
      duplicateCheckedAt: duplicateCheck.checkedAt || null,
      duplicateNotes: duplicateCheck.notes || "",
      virusStatus: virusScan.status || "PENDING",
      virusEngine: virusScan.engine || null,
      virusScannedAt: virusScan.scannedAt || null,
      virusNotes: virusScan.notes || "",
      metadataVerification,
      extractedMetadata,
      metadataConfidence: intakeData.metadataConfidence || 0,
      notes: intakeData.notes || "",
      updatedAt: intakeData.updatedAt,
      markComplete: intakeData.markComplete || false,
    };
  }, [intakeData]);

  const tmfMetadata = useMemo(() => {
    return document?.customMetadata?.tmfMetadata || {};
  }, [document]);

  const ingestionMethodLabels = {
    MANUAL_UPLOAD: "Manual Upload",
    EMAIL: "Email Attachment",
    API: "API Integration",
    INTEGRATION: "System Integration",
  };

  const formatDate = (date) => {
    if (!date) return "—";
    return new Date(date).toLocaleString('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short'
    });
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  const [reviewStages, setReviewStages] = useState(() =>
    Array.isArray(draft?.reviewStages) ? draft.reviewStages : []
  );

  React.useEffect(() => {
    if (Array.isArray(draft?.reviewStages)) {
      setReviewStages(draft.reviewStages);
    }
  }, [draft?.reviewStages]);

  const [sponsorPersons, setSponsorPersons] = useState(() =>
    Array.isArray(draft?.sponsorPersons) ? draft.sponsorPersons : []
  );

  React.useEffect(() => {
    if (Array.isArray(draft?.sponsorPersons)) {
      setSponsorPersons(draft.sponsorPersons);
    }
  }, [draft?.sponsorPersons]);

  const handleAddReviewStage = () => {
    const newStage = {
      key: `review-stage-${Date.now()}`,
      name: "",
      role: "",
      assignees: [],
      status: "PENDING",
      dueDate: null,
      startedAt: null,
      completedAt: null,
      reviewCycle: 1,
    };
    const updated = [...reviewStages, newStage];
    setReviewStages(updated);
    updateDraft({ reviewStages: updated });
  };

  const handleUpdateReviewStage = (index, field, value) => {
    const updated = [...reviewStages];
    updated[index] = { ...updated[index], [field]: value };
    setReviewStages(updated);
    updateDraft({ reviewStages: updated });
  };

  const handleRemoveReviewStage = (index) => {
    const updated = reviewStages.filter((_, i) => i !== index);
    setReviewStages(updated);
    updateDraft({ reviewStages: updated });
  };

  // 1. Updated Initializers (Inside QcValidationForm)
const handleAddSponsorPerson = () => {
  const newRoutingRow = {
    sendToTmf: {
      isEnabled: false,
      routingEmail: ""
    },
    sendToSafety: {
      isEnabled: false,
      safetyEmail: "",
      ccList: []
    }
  };
  
  const updated = [...sponsorPersons, newRoutingRow];
  setSponsorPersons(updated);
  updateDraft({ sponsorPersons: updated });
};

// 2. Updated Nested Field Handler
const handleUpdateSponsorRouting = (index, routeType, field, value) => {
  const updated = [...sponsorPersons];
  
  updated[index] = {
    ...updated[index],
    [routeType]: {
      ...updated[index][routeType],
      [field]: value
    }
  };

  setSponsorPersons(updated);
  updateDraft({ sponsorPersons: updated });
};

// 3. CC List specific handler
const handleCcEmailAction = (index, email, action) => {
  const updated = [...sponsorPersons];
  const currentCcList = updated[index].sendToSafety.ccList || [];
  
  if (action === 'ADD') {
    updated[index].sendToSafety.ccList = [...currentCcList, email];
  } else {
    updated[index].sendToSafety.ccList = currentCcList.filter((_, i) => i !== email); // email here is index
  }

  setSponsorPersons(updated);
  updateDraft({ sponsorPersons: updated });
};

  const handleRemoveSponsorPerson = (index) => {
    const updated = sponsorPersons.filter((_, i) => i !== index);
    setSponsorPersons(updated);
    updateDraft({ sponsorPersons: updated });
  };

  const handleDecisionChange = (value) => () => {
    setQcDecision(value);
    if (value === "APPROVE" || value === "APPROVE_WITH_COMMENTS") {
      updateDraft({
        qcDecision: value,
        qcDecisionNotes: "",
      });
    } else {
      updateDraft({
        qcDecision: value,
        qcDecisionNotes: "",
      });
    }
  };

  const handleTogglePublish = () => {
    const next = publicationStatus === 'PUBLISHED' ? 'UNPUBLISHED' : 'PUBLISHED';
    const payload = { publicationStatus: next };
    if (next === 'PUBLISHED' && (!actualEffectiveDate || actualEffectiveDate.trim() === '')) {
      const today = new Date().toISOString().split('T')[0];
      setActualEffectiveDate(today);
      payload.actualEffectiveDate = today;
    }
    setPublicationStatus(next);
    updateDraft(payload);
  };

  const StatusBadge = ({ status, type }) => {
    const styles = {
      duplicate: {
        CLEAR: "bg-emerald-50 text-emerald-700 border-emerald-200",
        MATCHED: "bg-amber-50 text-amber-700 border-amber-200",
        PENDING: "bg-slate-50 text-slate-600 border-slate-200"
      },
      virus: {
        CLEAN: "bg-emerald-50 text-emerald-700 border-emerald-200",
        INFECTED: "bg-red-50 text-red-700 border-red-200",
        PENDING: "bg-slate-50 text-slate-600 border-slate-200"
      }
    };

    const config = type === "duplicate" ? {
      CLEAR: { icon: CheckCircle2, label: "Clear - No Duplicates" },
      MATCHED: { icon: AlertTriangle, label: "Duplicate Found" },
      PENDING: { icon: Clock, label: "Pending Review" }
    } : {
      CLEAN: { icon: CheckCircle2, label: "Clean - No Threats" },
      INFECTED: { icon: XCircle, label: "Threat Detected" },
      PENDING: { icon: Clock, label: "Pending Scan" }
    };

    const active = config[status] || config.PENDING;
    const Icon = active.icon;

    return (
      <Badge variant="outline" className={cn("gap-1.5 font-medium px-2.5 py-0.5", styles[type][status] || styles[type].PENDING)}>
        <Icon className="h-3.5 w-3.5" />
        {active.label}
      </Badge>
    );
  };

  const SectionHeader = ({ icon: Icon, title, subtitle, section, badge, badgeVariant = "default" }) => (
    <button
      type="button"
      onClick={() => toggleSection(section)}
      className={cn(
        "w-full px-6 py-3 transition-all flex items-center justify-between group",
        expandedSections[section] ? "bg-slate-50/50" : "bg-white hover:bg-slate-50/30"
      )}
    >
      <div className="flex items-center gap-4">
        <div className={cn(
          "w-10 h-10 rounded-xl flex items-center justify-center transition-colors shadow-sm border",
          expandedSections[section] ? "bg-white border-slate-200 shadow-indigo-100/50" : "bg-slate-50 border-transparent"
        )}>
          <Icon className={cn("h-5 w-5", expandedSections[section] ? "text-indigo-600" : "text-slate-500")} />
        </div>
        <div className="text-left">
          <h4 className="text-sm font-bold text-slate-800 tracking-tight">{title}</h4>
          {subtitle && <p className="text-xs text-slate-500 font-medium">{subtitle}</p>}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {badge && (
          <Badge className={cn(
            "text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 shadow-none border",
            badgeVariant === "success" && "bg-emerald-50 text-emerald-700 border-emerald-100",
            badgeVariant === "warning" && "bg-amber-50 text-amber-700 border-amber-100",
            badgeVariant === "default" && "bg-slate-100 text-slate-600 border-slate-200"
          )}>
            {badge}
          </Badge>
        )}
        <div className="p-1 rounded-full group-hover:bg-slate-200/50 transition-colors">
          {expandedSections[section] ? (
            <ChevronUp className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          )}
        </div>
      </div>
    </button>
  );

  const DataRow = ({ label, value, icon: Icon, mono = false, highlight = false }) => (
    <div className={cn(
      // Base Card Styling: Rounded-xl with NO bottom margin
      "relative flex flex-col justify-center p-3 rounded-xl transition-all duration-300 group overflow-hidden border m-0",
      highlight
        ? "bg-indigo-50 border-indigo-200 shadow-sm"
        : "bg-slate-50/50 border-slate-100 hover:bg-white hover:border-indigo-100 hover:shadow-lg hover:shadow-indigo-500/10"
    )}>
      {/* Stylish Accent: A small dot indicator that appears on hover */}
      <div className="absolute right-3 top-3 w-1.5 h-1.5 rounded-full bg-indigo-500 scale-0 group-hover:scale-100 transition-transform duration-300" />

      {/* Left vertical accent line - subtle and rounded */}
      <div className={cn(
        "absolute left-0 top-3 bottom-3 w-0.5 rounded-r-full transition-all duration-300 opacity-0 group-hover:opacity-100",
        highlight ? "bg-indigo-600 opacity-100" : "bg-slate-300 group-hover:bg-indigo-400"
      )} />

      <div className="space-y-2">
        {/* Label and Icon */}
        <div className="flex items-center gap-2">
          <div className={cn(
            "p-1.5 rounded-lg transition-all duration-300 shadow-sm",
            highlight
              ? "bg-indigo-600 text-white"
              : "bg-white text-slate-500 group-hover:text-indigo-600 group-hover:shadow-indigo-100"
          )}>
            {Icon ? <Icon className="h-3.5 w-3.5" /> : <Activity className="h-3.5 w-3.5" />}
          </div>
          <span className="text-[10px] font-bold text-slate-400 group-hover:text-slate-600 uppercase tracking-[0.1em] leading-none transition-colors">
            {label}
          </span>
        </div>

        {/* Value Display */}
        <div className="pl-0.5">
          <span className={cn(
            "text-[13px] font-bold tracking-tight block transition-all duration-300 leading-none",
            mono
              ? "font-mono text-[11px] text-indigo-600 bg-white px-2 py-0.5 rounded border border-indigo-50 inline-block shadow-sm"
              : "text-slate-700 group-hover:text-slate-900",
            !value && "text-slate-300 italic font-medium"
          )}>
            {value || "—"}
          </span>
        </div>
      </div>
    </div>
  );

  const VerificationCard = ({ label, value, verified, subValue }) => (
    <div className={cn(
      "rounded-xl border-2 p-4 transition-all relative overflow-hidden",
      verified ? "border-emerald-100 bg-emerald-50/20" : "border-slate-100 bg-white shadow-sm"
    )}>
      {verified && <div className="absolute top-0 right-0 p-1 bg-emerald-500 rounded-bl-lg shadow-sm">
        <CheckCircle2 className="h-3 w-3 text-white" />
      </div>}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{label}</span>
      </div>
      <p className="text-sm font-bold text-slate-800 leading-tight">{value || "Not assigned"}</p>
      {subValue && <p className="text-[11px] font-mono text-slate-400 mt-2 bg-slate-50 p-1 rounded border border-slate-100">{subValue}</p>}
    </div>
  );

  const intakeSummary = useMemo(() => {
    if (!intakeReport) return null;
    const checks = { total: 0, passed: 0, failed: 0, pending: 0 };

    checks.total++;
    if (intakeReport.duplicateStatus === "CLEAR") checks.passed++;
    else if (intakeReport.duplicateStatus === "MATCHED") checks.failed++;
    else checks.pending++;

    checks.total++;
    if (intakeReport.virusStatus === "CLEAN") checks.passed++;
    else if (intakeReport.virusStatus === "INFECTED") checks.failed++;
    else checks.pending++;

    const mv = intakeReport.metadataVerification;
    const fields = ['zone', 'section', 'artifact', 'subArtifact'];
    fields.forEach(field => {
      if (document?.[field]) {
        checks.total++;
        if (mv[`${field}Verified`]) checks.passed++;
        else checks.pending++;
      }
    });
    return checks;
  }, [intakeReport, document]);

  // Resolve TMF classification to names (when API returns IDs like 69ad748722a0a77ae96fb9dd)
  const tmfDisplay = useMemo(() => {
    const out = { zone: null, section: null, artifact: null, subArtifact: null };
    if (!document) return out;
    const tmfRef = document.tmfReference ?? document.tmf_reference;
    const parts = tmfRef ? tmfRef.split(".").map((p) => String(parseInt(p, 10) || p).padStart(2, "0")) : [];
    const zoneObj = document.zone;
    const sectionObj = document.section;
    const artifactObj = document.artifact;
    const subObj = document.subArtifact ?? document.sub_artifact;

    const isId = (v) => typeof v === "string" && /^[0-9a-fA-F]{24}$/.test(v);
    const hasName = (obj) => obj && typeof obj === "object" && (obj.zoneName || obj.sectionName || obj.artifactName || obj.subArtifactName);

    if (zoneObj && hasName(zoneObj)) {
      out.zone = `${zoneObj.zoneNumber ?? ""} ${(zoneObj.zoneName || "").trim()}`.trim() || null;
    } else if (document.zoneNumber || document.zoneName) {
      out.zone = [document.zoneNumber, document.zoneName].filter(Boolean).join(" - ") || null;
    } else if (tmfRef && (isId(zoneObj) || !zoneObj) && parts.length >= 1) {
      const z = parts[0];
      const zoneInfo = hierarchyData.find((zd) => normalizeTMF(zd.Zone?.Number) === z);
      out.zone = zoneInfo ? `${z} - ${zoneInfo.Zone?.Name || ""}`.trim() : z;
    } else if (zoneObj && !isId(zoneObj)) {
      out.zone = String(zoneObj);
    }

    if (sectionObj && hasName(sectionObj)) {
      out.section = `${sectionObj.sectionNumber ?? ""} ${(sectionObj.sectionName || "").trim()}`.trim() || null;
    } else if (document.sectionNumber || document.sectionName) {
      out.section = [document.sectionNumber, document.sectionName].filter(Boolean).join(" - ") || null;
    } else if (tmfRef && (isId(sectionObj) || !sectionObj) && parts.length >= 2) {
      const z = parts[0];
      const s = parts[1];
      const zoneInfo = hierarchyData.find((zd) => normalizeTMF(zd.Zone?.Number) === z);
      const sectionInfo = zoneInfo?.Sections?.find((sec) => normalizeTMF(sec.Section?.Number) === normalizeTMF(`${z}.${s}`));
      out.section = sectionInfo ? `${sectionInfo.Section?.Number} - ${sectionInfo.Section?.Name || ""}`.trim() : `${z}.${s}`;
    } else if (sectionObj && !isId(sectionObj)) {
      out.section = String(sectionObj);
    }

    if (artifactObj && hasName(artifactObj)) {
      out.artifact = (artifactObj.artifactName || artifactObj.artifactNumber || "").trim() || null;
    } else if (document.artifactNumber || document.artifactName) {
      out.artifact = [document.artifactNumber, document.artifactName].filter(Boolean).join(" - ") || null;
    } else if (tmfRef && (isId(artifactObj) || !artifactObj) && parts.length >= 3) {
      const z = parts[0];
      const s = parts[1];
      const a = parts[2];
      const zoneInfo = hierarchyData.find((zd) => normalizeTMF(zd.Zone?.Number) === z);
      const sectionInfo = zoneInfo?.Sections?.find((sec) => normalizeTMF(sec.Section?.Number) === normalizeTMF(`${z}.${s}`));
      const artInfo = sectionInfo?.Artifacts?.find((art) => normalizeTMF(art.Artifact?.Number) === normalizeTMF(`${z}.${s}.${a}`));
      out.artifact = artInfo ? `${artInfo.Artifact?.Number} - ${artInfo.Artifact?.Name || ""}`.trim() : `${z}.${s}.${a}`;
    } else if (artifactObj && !isId(artifactObj)) {
      out.artifact = String(artifactObj);
    }

    if (subObj && typeof subObj === "object" && subObj.subArtifactName) {
      out.subArtifact = subObj.subArtifactName;
    } else if (document.subArtifactName) {
      out.subArtifact = document.subArtifactName;
    } else if (tmfRef && parts.length >= 3) {
      const z = parts[0];
      const s = parts[1];
      const a = parts[2];
      const zoneInfo = hierarchyData.find((zd) => normalizeTMF(zd.Zone?.Number) === z);
      const sectionInfo = zoneInfo?.Sections?.find((sec) => normalizeTMF(sec.Section?.Number) === normalizeTMF(`${z}.${s}`));
      const artInfo = sectionInfo?.Artifacts?.find((art) => normalizeTMF(art.Artifact?.Number) === normalizeTMF(`${z}.${s}.${a}`));
      const subArtifacts = artInfo?.SubArtifacts || [];
      out.subArtifact = subArtifacts.length > 0 ? subArtifacts[0].Name : null;
    } else if (subObj && !isId(subObj)) {
      out.subArtifact = String(subObj);
    }

    return out;
  }, [document, hierarchyData]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      {intakeReport && (
        <div className="rounded-3xl border border-slate-200 bg-white shadow-2xl shadow-indigo-100/20 overflow-hidden">
          {/* Enhanced Global Header */}
          <div className="px-6 py-5 bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 text-white relative overflow-hidden">
            {/* Abstract Background Decoration */}
            <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl -mr-20 -mt-20" />

            <div className="relative flex items-center justify-between mb-5">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-indigo-700 flex items-center justify-center border border-indigo-500 shadow-lg">
                  <FileText className="h-6 w-6 text-indigo-300" />
                </div>
                <div>
                  <h3 className="text-lg font-black tracking-tight leading-none uppercase">
                    Intake Validation Report
                  </h3>
                  <p className="text-indigo-300/60 text-[10px] font-bold uppercase tracking-[0.2em] mt-1.5 flex items-center gap-2">
                    <span className="w-1 h-1 bg-indigo-400 rounded-full" />
                    Document Lifecycle • Phase 1
                  </p>
                </div>
              </div>

              {intakeReport.markComplete && (
                <Badge className="bg-emerald-500/90 hover:bg-emerald-500 text-white border-none gap-1.5 px-4 py-1 rounded-full shadow-lg shadow-emerald-500/30 text-[10px] font-black uppercase tracking-wider">
                  <CheckCheck className="h-3.5 w-3.5" />
                  Validated
                </Badge>
              )}
            </div>

            {intakeSummary && (
              <div className="relative grid grid-cols-4 gap-3">
                {[
                  { label: 'Total Checks', val: intakeSummary.total, color: 'text-white', bg: 'bg-slate-700', border: 'border-slate-600' },
                  { label: 'Passed', val: intakeSummary.passed, color: 'text-emerald-300', bg: 'bg-emerald-800', border: 'border-emerald-600' },
                  { label: 'Pending', val: intakeSummary.pending, color: 'text-amber-300', bg: 'bg-amber-800', border: 'border-amber-600' },
                  { label: 'Failed', val: intakeSummary.failed, color: 'text-rose-300', bg: 'bg-rose-800', border: 'border-rose-600' }
                ].map((stat, i) => (
                  <div
                    key={i}
                    className={cn(
                      "rounded-xl p-3 border transition-transform hover:scale-[1.02] duration-300",
                      stat.bg,
                      stat.border
                    )}
                  >
                    <div className="flex items-baseline gap-1">
                      <p className={cn("text-xl font-black tracking-tighter", stat.color)}>
                        {stat.val.toString().padStart(2, '0')}
                      </p>
                    </div>
                    <p className="text-[9px] text-white/40 font-black uppercase tracking-widest mt-0.5">
                      {stat.label}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section: Document Information */}
          {document && (
            <div className="border-b border-slate-100/80">
              <SectionHeader
                icon={FileSearch}
                title="Document Identity"
                subtitle="Primary identifiers and registry status"
                section="document"
                badge={document.status || "Draft"}
                badgeVariant={document.status === "APPROVED" ? "success" : "default"}
              />

              {expandedSections.document && (
                <div className="px-6 py-4 space-y-4 bg-slate-50/30 animate-in fade-in zoom-in-95 duration-300">

                  {/* Main Document Spotlight Card */}
                  <div className="rounded-2xl border border-indigo-100 bg-white p-5 shadow-sm shadow-indigo-100/20 relative overflow-hidden group">
                    {/* Decorative Gradient Flare */}
                    <div className="absolute -right-4 -top-4 w-24 h-24 bg-indigo-50 rounded-full blur-3xl opacity-50 group-hover:opacity-100 transition-opacity" />

                    <div className="relative flex flex-col md:flex-row md:items-start justify-between gap-4">
                      <div className="flex-1 space-y-2">
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="outline" className="bg-indigo-50/50 text-indigo-700 border-indigo-100 px-2 py-0 text-[10px] font-bold">
                            <FileType className="h-3 w-3 mr-1" /> {document.documentType || "Unknown"}
                          </Badge>
                          <Badge variant="outline" className="bg-slate-50 text-slate-600 border-slate-200 px-2 py-0 text-[10px] font-bold">
                            <Tag className="h-3 w-3 mr-1" /> v{document.version || 1}
                          </Badge>
                        </div>

                        <h5 className="text-xl font-extrabold text-slate-900 tracking-tight leading-tight">
                          {document.title || "Untitled Document"}
                        </h5>

                        {document.description && (
                          <p className="text-sm text-slate-500 font-medium leading-relaxed line-clamp-2 hover:line-clamp-none transition-all">
                            {document.description}
                          </p>
                        )}

                        {document.tmfReference && (
                          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-900 text-indigo-300 text-[10px] font-mono shadow-sm">
                            <Link2 className="h-3 w-3" /> {document.tmfReference}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Technical Identity Grid - Tighter & Cleaner */}
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                    <DataRow label="Doc ID" value={document.documentId} icon={Fingerprint} mono />
                    <DataRow label="Language" value={document.language?.toUpperCase()} icon={Globe} />
                    <DataRow label="Doc Date" value={document.documentDate ? new Date(document.documentDate).toLocaleDateString() : null} icon={Calendar} />
                    <DataRow label="Created" value={formatDate(document.creationDate)} icon={Clock} />
                    <DataRow label="Status" value={document.status} icon={Activity} />
                    <DataRow label="QC Level" value={document.qualityControlStatus} icon={Shield} />
                  </div>

                  {/* Study Context Card - Styled as a "Sub-section" */}
                  {(document.study || document.country || document.site) && (
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <div className="w-1 h-3 bg-indigo-500 rounded-full" />
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">
                          Location & Study Context
                        </p>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {document.study && (
                          <DataRow
                            label="Study"
                            value={studyTitle}
                            icon={Building2}
                            highlight
                          />
                        )}
                        {document.country && <DataRow label="Country" value={document.country} icon={Globe} />}
                        {document.site && (
                          <DataRow
                            label="Site"
                            value={typeof document.site === 'object' ? document.site.name : document.site}
                            icon={MapPin}
                          />
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Section: Security Checks */}
          <div className="border-b border-slate-100">
            <SectionHeader
              icon={ShieldCheck}
              title="Security & Compliance"
              subtitle="Integrity verification and automated scans"
              section="security"
              badge={intakeReport.duplicateStatus === "CLEAR" && intakeReport.virusStatus === "CLEAN" ? "Passed" : "Action Needed"}
              badgeVariant={intakeReport.duplicateStatus === "CLEAR" && intakeReport.virusStatus === "CLEAN" ? "success" : "warning"}
            />
            {expandedSections.security && (
              <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3 bg-emerald-50/10 animate-in fade-in duration-300">

                {/* Duplicate Analysis Card */}
                <div className="rounded-xl bg-white border border-slate-200 p-2.5 shadow-sm hover:shadow-md transition-all group">
                  <div className="flex items-center justify-between">
                    {/* Left Side: Title & Icon */}
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center border border-indigo-100/50 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                        <Layers className="h-4 w-4 text-indigo-500 group-hover:text-white" />
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[10px] font-black text-slate-700 uppercase tracking-wider leading-none">
                          Duplicate Analysis
                        </span>
                        <span className="text-[9px] text-slate-400 font-bold uppercase mt-1">Integrity Check</span>
                      </div>
                    </div>

                    {/* Right Side: Badges */}
                    <div className="flex items-center gap-2">
                      <StatusBadge status={intakeReport.duplicateStatus} type="duplicate" />
                      <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-slate-50 border border-slate-100 text-[9px] text-slate-400 font-medium italic">
                        <Clock className="h-3 w-3 opacity-70" />
                        {formatDate(intakeReport.duplicateCheckedAt)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Virus Scan Card */}
                <div className="rounded-xl bg-white border border-slate-200 p-2.5 shadow-sm hover:shadow-md transition-all group">
                  <div className="flex items-center justify-between">
                    {/* Left Side: Title & Icon */}
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center border border-emerald-100/50 group-hover:bg-emerald-600 group-hover:text-white transition-colors">
                        <ShieldCheck className="h-4 w-4 text-emerald-500 group-hover:text-white" />
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[10px] font-black text-slate-700 uppercase tracking-wider leading-none">
                          Virus Scan
                        </span>
                        <span className="text-[9px] text-slate-400 font-bold uppercase mt-1">Security Shield</span>
                      </div>
                    </div>

                    {/* Right Side: Badges */}
                    <div className="flex items-center gap-2">
                      <StatusBadge status={intakeReport.virusStatus} type="virus" />
                      <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-slate-50 border border-slate-100 text-[9px] text-slate-400 font-medium italic">
                        <Clock className="h-3 w-3 opacity-70" />
                        {formatDate(intakeReport.virusScannedAt)}
                      </div>
                    </div>
                  </div>
                </div>

              </div>
            )}
          </div>

          {/* Section: TMF Structure - use tmfDisplay so IDs show as names (from tmfReference + hierarchy) */}
          {document && (tmfDisplay.zone || tmfDisplay.section || tmfDisplay.artifact || tmfDisplay.subArtifact || document.tmfReference || document.tmf_reference) && (
            <div className="border-b border-slate-100">
              <SectionHeader
                icon={FolderTree}
                title="TMF Classification"
                subtitle="Zone, Section, and Artifact mapping"
                section="tmfStructure"
                badge="Structure Verified"
                badgeVariant="success"
              />
              {expandedSections.tmfStructure && (
                <div className="px-4 py-2 bg-slate-50/30">
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {(tmfDisplay.zone || document.zone) && (
                      <VerificationCard
                        label="Zone"
                        value={tmfDisplay.zone || (typeof document.zone === 'object'
                          ? `${document.zone.zoneNumber ?? ''} ${(document.zone.zoneName || '').trim()}`.trim()
                          : /^[0-9a-fA-F]{24}$/.test(document.zone) ? null : document.zone) || "—"}
                        verified={intakeReport.metadataVerification?.zoneVerified}
                        subValue={document.tmfReference || document.tmf_reference ? `TMF: ${document.tmfReference || document.tmf_reference}` : null}
                      />
                    )}
                    {(tmfDisplay.section || document.section) && (
                      <VerificationCard
                        label="Section"
                        value={tmfDisplay.section || (typeof document.section === 'object' ? `${document.section.sectionNumber} - ${document.section.sectionName}` : /^[0-9a-fA-F]{24}$/.test(document.section) ? "—" : document.section) || "—"}
                        verified={intakeReport.metadataVerification?.sectionVerified}
                      />
                    )}
                    {(tmfDisplay.artifact || document.artifact) && (
                      <VerificationCard
                        label="Artifact"
                        value={tmfDisplay.artifact || (typeof document.artifact === 'object' ? document.artifact.artifactName : /^[0-9a-fA-F]{24}$/.test(document.artifact) ? "—" : document.artifact) || "—"}
                        verified={intakeReport.metadataVerification?.artifactVerified}
                      />
                    )}
                    {(tmfDisplay.subArtifact || document.subArtifact || document.sub_artifact) && (
                      <VerificationCard
                        label="Sub-Artifact"
                        value={tmfDisplay.subArtifact || (typeof (document.subArtifact ?? document.sub_artifact) === 'object' ? (document.subArtifact ?? document.sub_artifact).subArtifactName : /^[0-9a-fA-F]{24}$/.test(document.subArtifact ?? document.sub_artifact) ? "—" : (document.subArtifact ?? document.sub_artifact)) || "—"}
                        verified={intakeReport.metadataVerification?.subArtifactVerified}
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Section: TMF Process Metadata */}
          {Object.keys(tmfMetadata).length > 0 && (
            <div className="border-b border-slate-100">
              <SectionHeader
                icon={BookOpen}
                title="Process Metadata"
                subtitle="Extended attributes and regulatory codes"
                section="tmfMetadata"
                badge={`${Object.values(tmfMetadata).filter(v => !!v).length} Parameters`}
              />
              {expandedSections.tmfMetadata && (
                <div className="px-4 py-2 bg-slate-50/30">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {Object.entries(tmfMetadata).map(([key, value]) => {
                      if (value === undefined || value === null || value === '') return null;
                      const formattedLabel = key.replace(/([A-Z])/g, ' $1').trim();
                      return <DataRow key={key} label={formattedLabel} value={typeof value === 'boolean' ? (value ? 'Yes' : 'No') : value} mono={key.toLowerCase().includes('code')} highlight={key.toLowerCase().includes('process')} />;
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Section: File Information */}
          {document && (
            <div className="border-b border-slate-100">
              <SectionHeader
                icon={File}
                title="Technical Specifications"
                subtitle="File binary data and cryptographic hashes"
                section="fileInfo"
                badge={formatFileSize(document.fileSize)}
              />
              {expandedSections.fileInfo && (
                <div className="p-6 bg-slate-50/30">
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <DataRow label="File Size" value={formatFileSize(document.fileSize)} icon={HardDrive} />
                    <DataRow label="MIME Type" value={document.mimeType} icon={FileType} />
                    <DataRow label="Page Count" value={document.pageCount} icon={File} />
                    <DataRow label="Binary URL" value={document.fileUrl ? "Active" : "Locked"} icon={Link2} />
                  </div>
                  {document.fileHash && (
                    <div className="mt-4 p-4 rounded-xl bg-slate-900 text-indigo-300 font-mono text-[10px] break-all border border-slate-800 shadow-inner">
                      <span className="text-slate-500 mr-2 uppercase">SHA-256 Hash:</span> {document.fileHash}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Section: Ingestion Info */}
          <button type="button" className="w-full px-6 py-3 transition-all flex items-center justify-between group">
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center transition-colors shadow-sm border">
                <Upload className="h-5 w-5 text-indigo-600" />
              </div>
              <div className="text-left">
                <h4 className="text-sm font-bold text-slate-800 tracking-tight">Ingestion Details</h4>
                <p className="text-xs text-slate-500 font-medium">Source & extraction metrics</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Badge
                className={cn(
                  "text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 shadow-none border",
                  "bg-indigo-50 text-indigo-700 border-indigo-100"
                )}
              >
                {ingestionMethodLabels[intakeReport.ingestionMethod] || intakeReport.ingestionMethod}
              </Badge>
            </div>
          </button>

          {document && (
            <div className="border-b border-slate-100/80">
              <SectionHeader
                icon={Users}
                title="Review Stages"
                subtitle="Stakeholder assignments"
                section="reviewStages"
                badge={reviewStages.length > 0 ? `${reviewStages.length} Assigned` : null}
              />

              {expandedSections.reviewStages && (
                <div className="bg-white animate-in fade-in duration-300">
                  {reviewStages.length === 0 ? (
                    /* Stylish Empty State - Acts as the primary "Add" action */
                    <div className="px-4 pb-2">
                      <button
                        onClick={handleAddReviewStage}
                        className="w-full py-4 border-2 border-dashed border-slate-100 rounded-2xl flex flex-col items-center justify-center hover:bg-slate-50 hover:border-indigo-200 transition-all group"
                      >
                        <div className="w-12 h-12 rounded-full bg-slate-50 group-hover:bg-indigo-50 flex items-center justify-center mb-3 transition-colors shadow-sm">
                          <Plus className="h-6 w-6 text-slate-400 group-hover:text-indigo-600" />
                        </div>
                        <p className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em] group-hover:text-indigo-600">
                          Assign First Reviewer
                        </p>
                        <p className="text-[10px] text-slate-400 mt-1 lowercase italic opacity-0 group-hover:opacity-100 transition-opacity">
                          click to define a validation stage
                        </p>
                      </button>
                    </div>
                  ) : (
                    <div className="px-6 pb-4 space-y-6">
                      {/* Header for List */}
                      <div className="flex justify-between items-center border-b border-slate-50 pb-2">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                          Reviewer Configuration
                        </span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={handleAddReviewStage}
                          className="h-6 text-white bg-indigo-600 text-[10px] font-black uppercase tracking-widest px-2 gap-1"
                        >
                          <Plus className="h-3 w-3" />
                          Add Another
                        </Button>
                      </div>

                      {/* Stylish Reviewer List */}
                      <div className="space-y-3"> {/* Increased gap slightly for better separation of shadow cards */}
                        {reviewStages.map((stage, index) => (
                          <div
                            key={stage.key || index}
                            className={cn(
                              "relative flex flex-col justify-center p-4 rounded-xl transition-all duration-300 overflow-hidden border m-0",
                              // Applied active states initially: white bg, indigo border, and shadow
                              "bg-white border-indigo-100 shadow-lg shadow-indigo-500/10"
                            )}
                          >
                            {/* Stylish Accent: Dot is now visible initially (scale-100) */}
                            <div className="absolute right-3 top-3 w-1.5 h-1.5 rounded-full bg-indigo-500 scale-100 transition-transform duration-300" />

                            {/* Left vertical accent line: Now visible initially (opacity-100) with indigo color */}
                            <div className={cn(
                              "absolute left-0 top-3 bottom-3 w-0.5 rounded-r-full transition-all duration-300 opacity-100 bg-indigo-400"
                            )} />

                            {/* Content Grid */}
                            <div className="flex items-center gap-6">
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 flex-1">
                                {/* Reviewer Name */}
                                <div className="space-y-2">
                                  <div className="flex items-center gap-2 ml-0.5">
                                    <User className="h-3 w-3 text-indigo-600" />
                                    <label className="text-[9px] font-black text-indigo-600 uppercase tracking-widest">Name</label>
                                  </div>
                                  <Input
                                    value={stage.name || ""}
                                    onChange={(e) => handleUpdateReviewStage(index, "name", e.target.value)}
                                    placeholder="e.g. Dr. John Doe"
                                    disabled={disabled || isLoading}
                                    // Input matches the active card style
                                    className="h-9 border-none bg-slate-50 focus:bg-white focus:ring-1 focus:ring-indigo-100 transition-all text-xs font-bold px-3 rounded-lg shadow-none"
                                  />
                                </div>

                                {/* Role Selection */}
                                <div className="space-y-2">
                                  <div className="flex items-center gap-2 ml-0.5">
                                    <Shield className="h-3 w-3 text-indigo-600" />
                                    <label className="text-[9px] font-black text-indigo-600 uppercase tracking-widest">Role</label>
                                  </div>
                                  <Select
                                    value={stage.role || ""}
                                    onValueChange={(val) => handleUpdateReviewStage(index, "role", val)}
                                    disabled={disabled || isLoading}
                                  >
                                    <SelectTrigger className="h-9 border-none bg-slate-50 focus:bg-white transition-all text-xs font-bold px-3 rounded-lg shadow-none">
                                      <SelectValue placeholder="Select Responsibility" />
                                    </SelectTrigger>
                                    <SelectContent className="rounded-xl border-slate-100">
                                      <SelectItem value="MEDICAL_MONITOR" className="text-xs font-medium">Medical Monitor</SelectItem>
                                      <SelectItem value="LEGAL_REVIEWER" className="text-xs font-medium">Legal Reviewer</SelectItem>
                                      <SelectItem value="REGULATORY" className="text-xs font-medium">Regulatory</SelectItem>
                                      <SelectItem value="QUALITY_REVIEWER" className="text-xs font-medium">Quality Reviewer</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </div>
                              </div>

                              {/* Delete Button - Also visible initially */}
                              <div className="transition-all shrink-0">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => handleRemoveReviewStage(index)}
                                  className="h-8 w-8 text-rose-500 hover:bg-rose-50 rounded-lg transition-colors"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}


          {/* QC DECISION SECTION */}
                    <div className="p-6 bg-white border-t border-slate-100">
                      {/* Header */}
                      <div className="flex items-center gap-3 mb-6">
                        <div className="w-10 h-10 rounded-xl bg-slate-50 flex items-center justify-center border border-slate-200 shadow-sm">
                          <ClipboardCheck className="h-5 w-5 text-indigo-600" />
                        </div>
                        <div className="text-left">
                          <h4 className="text-xs font-black text-slate-900 uppercase tracking-widest leading-none">
                            Quality Control Decision
                          </h4>
                          <p className="text-[10px] text-slate-400 font-bold uppercase mt-1 tracking-wider">
                            Finalize document validation status
                          </p>
                        </div>
                      </div>
          
                      {/* Decision Grid */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {/* APPROVE */}
                        <div
                          onClick={handleDecisionChange("APPROVE")}
                          className={cn(
                            "group relative rounded-xl border-2 p-4 cursor-pointer transition-all duration-300",
                            qcDecision === "APPROVE"
                              ? "border-emerald-500 bg-emerald-50/50 shadow-md shadow-emerald-500/10 scale-[1.02]"
                              : "border-slate-200 bg-white hover:border-emerald-200 hover:bg-emerald-50/10 hover:shadow-sm"
                          )}
                        >
                          <div className="flex items-center justify-between mb-3">
                            <div className={cn(
                              "w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-300",
                              qcDecision === "APPROVE"
                                ? "bg-emerald-500 text-white shadow-emerald-200 shadow-md"
                                : "bg-slate-100 text-slate-400 group-hover:bg-emerald-100 group-hover:text-emerald-600"
                            )}>
                              <CheckCircle2 className="h-5 w-5" />
                            </div>
                            <Badge className={cn(
                              "font-black uppercase text-[8px] tracking-[0.1em] px-2 py-0 border transition-colors",
                              qcDecision === "APPROVE"
                                ? "bg-emerald-100 text-emerald-700 border-emerald-200"
                                : "bg-slate-50 text-slate-400 border-slate-200 group-hover:border-emerald-200 group-hover:text-emerald-600"
                            )}>
                              Full Pass
                            </Badge>
                          </div>
                          <p className="text-[11px] font-black text-slate-900 uppercase tracking-widest">Approve</p>
                          <p className="text-[9px] text-slate-400 font-bold uppercase mt-0.5">Ready for filing</p>
                        </div>
          
                        {/* APPROVE WITH COMMENTS */}
                        <div
                          onClick={handleDecisionChange("APPROVE_WITH_COMMENTS")}
                          className={cn(
                            "group relative rounded-xl border-2 p-4 cursor-pointer transition-all duration-300",
                            qcDecision === "APPROVE_WITH_COMMENTS"
                              ? "border-amber-500 bg-amber-50/50 shadow-md shadow-amber-500/10 scale-[1.02]"
                              : "border-slate-200 bg-white hover:border-amber-200 hover:bg-amber-50/10 hover:shadow-sm"
                          )}
                        >
                          <div className="flex items-center justify-between mb-3">
                            <div className={cn(
                              "w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-300",
                              qcDecision === "APPROVE_WITH_COMMENTS"
                                ? "bg-amber-500 text-white shadow-amber-200 shadow-md"
                                : "bg-slate-100 text-slate-400 group-hover:bg-amber-100 group-hover:text-amber-600"
                            )}>
                              <AlertCircle className="h-5 w-5" />
                            </div>
                            <Badge className={cn(
                              "font-black uppercase text-[8px] tracking-[0.1em] px-2 py-0 border transition-colors",
                              qcDecision === "APPROVE_WITH_COMMENTS"
                                ? "bg-amber-100 text-amber-700 border-amber-200"
                                : "bg-slate-50 text-slate-400 border-slate-200 group-hover:border-amber-200 group-hover:text-amber-600"
                            )}>
                              Conditional
                            </Badge>
                          </div>
                          <p className="text-[11px] font-black text-slate-900 uppercase tracking-widest">Approve with Notes</p>
                          <p className="text-[9px] text-slate-400 font-bold uppercase mt-0.5">Minor corrections</p>
                        </div>
          
                        {/* DECLINE */}
                        <div
                          onClick={handleDecisionChange("DECLINE")}
                          className={cn(
                            "group relative rounded-xl border-2 p-4 cursor-pointer transition-all duration-300",
                            qcDecision === "DECLINE"
                              ? "border-rose-500 bg-rose-50/50 shadow-md shadow-rose-500/10 scale-[1.02]"
                              : "border-slate-200 bg-white hover:border-rose-200 hover:bg-rose-50/10 hover:shadow-sm"
                          )}
                        >
                          <div className="flex items-center justify-between mb-3">
                            <div className={cn(
                              "w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-300",
                              qcDecision === "DECLINE"
                                ? "bg-rose-500 text-white shadow-rose-200 shadow-md"
                                : "bg-slate-100 text-slate-400 group-hover:bg-rose-100 group-hover:text-rose-600"
                            )}>
                              <XCircle className="h-5 w-5" />
                            </div>
                            <Badge className={cn(
                              "font-black uppercase text-[8px] tracking-[0.1em] px-2 py-0 border transition-colors",
                              qcDecision === "DECLINE"
                                ? "bg-rose-100 text-rose-700 border-rose-200"
                                : "bg-slate-50 text-slate-400 border-slate-200 group-hover:border-rose-200 group-hover:text-rose-600"
                            )}>
                              Rejected
                            </Badge>
                          </div>
                          <p className="text-[11px] font-black text-slate-900 uppercase tracking-widest">Decline</p>
                          <p className="text-[9px] text-slate-400 font-bold uppercase mt-0.5">Requires re-upload</p>
                        </div>
                      </div>
          
                      {/* Conditional Textarea */}
                      {(qcDecision === "APPROVE_WITH_COMMENTS" || qcDecision === "DECLINE") && (
                        <div className="mt-6 animate-in fade-in slide-in-from-top-2 duration-400">
                          <div className="flex items-center gap-2 mb-2 px-1">
                            <div className={cn(
                              "w-1 h-3 rounded-full",
                              qcDecision === "DECLINE" ? "bg-rose-500" : "bg-amber-500"
                            )} />
                            <Label className="text-[9px] font-black text-slate-500 uppercase tracking-widest">
                              {qcDecision === "DECLINE" ? "Rejection Reason" : "Reviewer Comments"}
                            </Label>
                          </div>
                          <Textarea
                            rows={3}
                            placeholder={qcDecision === "DECLINE" ? "Provide a detailed reason for declining..." : "Add contextual notes..."}
                            value={draft.qcDecisionNotes || ""}
                            onChange={onInputChange("qcDecisionNotes")}
                            className="resize-none rounded-xl border-slate-200 bg-slate-50/50 focus:bg-white focus:border-indigo-300 focus:ring-0 p-3 text-xs font-medium shadow-inner"
                          />
                        </div>
                      )}
                    </div>
                    
          {/* PUBLISH DOCUMENT SECTION */}
          <div className="p-6 bg-white border-t border-slate-100 space-y-4">
            {/* Header */}
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center border border-emerald-200 shadow-sm">
                <Upload className="h-5 w-5 text-emerald-600" />
              </div>
              <div className="text-left">
                <h4 className="text-xs font-black text-slate-900 uppercase tracking-widest leading-none">
                  Publish Document
                </h4>
                <p className="text-[10px] text-slate-400 font-bold uppercase mt-1 tracking-wider">
                  Set effective date and activate the document
                </p>
              </div>
            </div>

            
            {/* Effective Date */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="qcEffectiveDate" className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  <Calendar className="h-4 w-4 inline mr-1.5 text-emerald-600" />
                  Effective Date <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="qcEffectiveDate"
                  type="date"
                  value={actualEffectiveDate}
                  onChange={(e) => {
                    setActualEffectiveDate(e.target.value);
                    updateDraft({ actualEffectiveDate: e.target.value });
                  }}
                  className="h-9 text-xs"
                  disabled={disabled || isLoading}
                />
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  <Upload className="h-4 w-4 inline mr-1.5 text-emerald-600" />
                  Publication Status
                </Label>
                <div className="flex items-center gap-2">
                  <Badge className={publicationStatus === 'PUBLISHED' ? "bg-emerald-100 text-emerald-700 border-emerald-200 text-xs" : "bg-slate-100 text-slate-600 border-slate-200 text-xs"}>
                    {publicationStatus === 'PUBLISHED' ? 'Published' : (publicationStatus === 'PENDING' ? 'Pending' : 'Unpublished')}
                  </Badge>
                  <Button
                    size="sm"
                    onClick={handleTogglePublish}
                    disabled={disabled || isLoading}
                    className={cn("h-9 text-xs font-bold", publicationStatus === 'PUBLISHED' ? "bg-rose-600 hover:bg-rose-700 text-white" : "bg-emerald-600 hover:bg-emerald-700 text-white")}
                  >
                    <Upload className="h-3.5 w-3.5 mr-1.5" />
                    {publicationStatus === 'PUBLISHED' ? 'Unpublish' : 'Publish'}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Section: Submission Channels */}
          <div className="border-b border-slate-100/80">
            <SectionHeader
              icon={Globe}
              title="Distribution Channels"
              subtitle="Configure document routing for TMF and Safety"
              section="sponsorPersons"
              badge={(sendToTmf || sendToSafety) ? "Active" : null}
              badgeVariant={(sendToTmf || sendToSafety) ? "success" : "default"}
            />

            {expandedSections.sponsorPersons && (
              <div className="px-6 pb-8 space-y-4 bg-white animate-in fade-in slide-in-from-top-2 duration-300">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  
                  {/* TMF CARD */}
                  <div className={cn(
                    "relative rounded-2xl border-2 p-6 transition-all duration-300 flex flex-col justify-between",
                    sendToTmf 
                      ? "border-indigo-600 bg-indigo-50/20 ring-4 ring-indigo-500/5" 
                      : "border-slate-100 bg-white shadow-sm"
                  )}>
                    <div>
                      <div className="flex items-center justify-between mb-4">
                        {/* Dynamic Colored Icon Container */}
                        <div className={cn(
                          "w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-500 shadow-sm border",
                          sendToTmf 
                            ? "bg-indigo-600 border-indigo-400 text-white shadow-indigo-200 rotate-[360deg]" 
                            : "bg-slate-50 border-slate-200 text-slate-400"
                        )}>
                          <FolderTree className={cn("h-6 w-6", sendToTmf ? "text-white" : "text-slate-400")} />
                        </div>
                        {sendToTmf && (
                          <Badge className="bg-indigo-600 text-white border-none text-[9px] font-black uppercase tracking-tighter">
                            TMF Enabled
                          </Badge>
                        )}
                      </div>
                      <h5 className="text-sm font-black text-slate-900 uppercase tracking-tight mb-1">TMF Repository</h5>
                      <p className="text-[11px] text-slate-500 leading-relaxed mb-8">
                        Automated ingestion into the electronic Trial Master File system.
                      </p>
                    </div>
                    
                    <Button
                      type="button"
                      onClick={handleToggleTmf}
                      disabled={tmfSending}
                      variant={sendToTmf ? "default" : "outline"}
                      className={cn(
                        "w-full font-black uppercase text-[10px] tracking-widest h-10 transition-all",
                        sendToTmf ? "bg-indigo-600 hover:bg-indigo-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                      )}
                    >
                      {tmfSending
                        ? "Publishing…"
                        : sendToTmf
                        ? "Disable Routing"
                        : "Enable TMF Routing"}
                    </Button>
                    {tmfError && (
                      <p className="mt-2 text-xs text-red-600">{tmfError}</p>
                    )}
                  </div>

                  {/* SAFETY CARD */}
                  <div className={cn(
                    "relative rounded-2xl border-2 p-6 transition-all duration-300 flex flex-col",
                    sendToSafety 
                      ? "border-emerald-600 bg-emerald-50/20 ring-4 ring-emerald-500/5" 
                      : "border-slate-100 bg-white shadow-sm"
                  )}>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-4">
                        {/* Dynamic Colored Icon Container */}
                        <div className={cn(
                          "w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-500 shadow-sm border",
                          sendToSafety 
                            ? "bg-emerald-600 border-emerald-400 text-white shadow-emerald-200" 
                            : "bg-slate-50 border-slate-200 text-slate-400"
                        )}>
                          <ShieldCheck className={cn("h-6 w-6", sendToSafety ? "text-white" : "text-slate-400")} />
                        </div>
                        {sendToSafety && (
                          <Badge className="bg-emerald-600 text-white border-none text-[9px] font-black uppercase tracking-tighter">
                            Safety Enabled
                          </Badge>
                        )}
                      </div>
                      <h5 className="text-sm font-black text-slate-900 uppercase tracking-tight mb-1">Safety Department</h5>
                      <p className="text-[11px] text-slate-500 leading-relaxed mb-6">
                        Routes to safety monitors with optional stakeholder CC list.
                      </p>

                      {/* CC Section - Hidden unless active */}
                      <div className={cn(
                        "space-y-4 transition-all duration-500",
                        sendToSafety ? "opacity-100 translate-y-0 max-h-[500px]" : "opacity-0 invisible max-h-0 overflow-hidden"
                      )}>
                        <div className="flex gap-2">
                          <div className="relative flex-1">
                            <Mail className={cn(
                              "absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 transition-colors",
                              sendToSafety ? "text-emerald-500" : "text-slate-400"
                            )} />
                            <Input 
                              placeholder="safety.contact@sponsor.com" 
                              value={newCcEmail}
                              onChange={(e) => setNewCcEmail(e.target.value)}
                              className="h-9 pl-9 text-xs font-bold bg-white border-slate-200 focus:border-emerald-500 focus:ring-0"
                              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddCcEmail())}
                            />
                          </div>
                          <Button 
                            type="button" 
                            onClick={handleAddCcEmail}
                            className="bg-slate-900 hover:bg-black h-9 px-4 text-[10px] font-black uppercase tracking-widest"
                          >
                            Add CC
                          </Button>
                        </div>

                        {/* CC LIST CONTAINER */}
                        <div className="flex flex-wrap gap-2 pt-3 border-t border-emerald-200/40">
                          {safetyCcEmails.length > 0 ? safetyCcEmails.map((email, idx) => (
                            <div 
                              key={`${email}-${idx}`} 
                              className="flex items-center gap-2 bg-white border border-emerald-200 pl-2.5 pr-1.5 py-1 rounded-lg shadow-sm animate-in zoom-in-95"
                            >
                              <span className="text-[10px] font-bold text-emerald-900">{email}</span>
                              <button 
                                type="button"
                                onClick={(e) => handleRemoveCcEmail(e, idx)}
                                className="p-1 rounded-md hover:bg-rose-100 text-slate-400 hover:text-rose-600 transition-all"
                              >
                                <Trash2 className="h-3 w-3" />
                              </button>
                            </div>
                          )) : (
                            <div className="flex items-center gap-2 text-emerald-700/40 py-1">
                              <Info className="h-3 w-3" />
                              <span className="text-[9px] font-black uppercase tracking-widest">No additional CCs</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    <Button
                      type="button"
                      onClick={handleToggleSafety}
                      variant={sendToSafety ? "default" : "outline"}
                      className={cn(
                        "w-full font-black uppercase text-[10px] tracking-widest h-10 mt-6 transition-all",
                        sendToSafety ? "bg-emerald-600 hover:bg-emerald-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                      )}
                    >
                      {sendToSafety ? "Deactivate Safety" : "Activate Safety Routing"}
                    </Button>
                  </div>

                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default QcValidationForm;