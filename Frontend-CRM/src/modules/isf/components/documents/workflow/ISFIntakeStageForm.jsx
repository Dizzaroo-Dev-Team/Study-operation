import React, { useMemo, useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CheckCircle2,
  AlertCircle,
  Clock,
  Upload,
  ShieldCheck,
  FileSearch,
  Info,
  FileText,
  Layers,
  Calendar,
  Globe,
  Building2,
  Hash,
  BookOpen,
  CheckCheck,
  FileX,
  User,
  Shield,
  Tag,
  Key,
  MapPin,
  Stethoscope,
  Activity,
  History,
  Archive,
  ClipboardCheck,
  Zap,
  Layout,
  Flag,
  RotateCcw
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getDocumentClassificationMetadata } from "@/utils/documentMetadata";
import useTmfHierarchy from '../../../hooks/useTmfHierarchy';
import { getZonesFromHierarchy, normalizeTMF } from '@/utils/tmfHierarchyUtils';

const ISFIntakeStageForm = ({ draft, onChange, studyTitle, disabled, canMarkComplete, document, onReplaceDocument, onLegibilityChange }) => {
  const { hierarchyData, artifactSubartifacts } = useTmfHierarchy();
  const merge = (update) => {
    if (typeof onChange !== "function") return;
    onChange((prev) => ({
      ...prev,
      ...(typeof update === "function" ? update(prev) : update),
    }));
  };

  // Helper to handle Document Level Flags (Yes/No/X -> boolean)
  const toBool = (val) => {
    if (typeof val === 'boolean') return val;
    if (!val) return false;
    const s = String(val).toLowerCase();
    return s === 'yes' || s === 'x' || s === 'true';
  };

  // Helper to normalize TMF numbers for matching between draft data and dropdown values
  // Handle mixed data types: Zone.Number (string), Section.Number (number), Artifact.Number (string)
  const normalizeTMF = (val) => {
    if (val === null || val === undefined) return "";
    const s = String(val).trim();
    if (!s) return "";
    
    // Convert to consistent format for matching
    const parts = s.split('.');
    
    // First part (zone): 2 digits with leading zero
    if (parts.length > 0) {
      const parsed = parseInt(parts[0], 10);
      if (!isNaN(parsed)) {
        parts[0] = parsed.toString().padStart(2, '0');
      }
    }
    
    // Second part (section): 2 digits with leading zero  
    if (parts.length > 1) {
      const parsed = parseInt(parts[1], 10);
      parts[1] = isNaN(parsed) ? parts[1] : parsed.toString().padStart(2, '0');
    }
    
    // Third part (artifact): 2 digits with leading zero
    if (parts.length > 2) {
      const parsed = parseInt(parts[2], 10);
      parts[2] = isNaN(parsed) ? parts[2] : parsed.toString().padStart(2, '0');
    }
    
    return parts.join('.');
  };

  const handleTextChange = (field) => (event) => merge({ [field]: event.target.value });

  const handleSelectChange = (field) => (value) => merge({ [field]: value });

  const handleCheckboxChange = (field) => (checked) => merge({ [field]: checked === true });

  // Derive classification metadata
  const classificationMetadata = useMemo(
    () => getDocumentClassificationMetadata(document),
    [document]
  );

  // Check status indicators
  const duplicateCheckStatus = useMemo(() => {
    const s = (draft.duplicateStatus || "").toUpperCase();
    if (s === "CLEAR") {
      return { icon: CheckCircle2, color: "text-emerald-600", bg: "bg-emerald-50", label: "Clear" };
    }
    if (s === "MATCHED") {
      return { icon: AlertCircle, color: "text-amber-600", bg: "bg-amber-50", label: "Matched" };
    }
    return { icon: Clock, color: "text-slate-400", bg: "bg-slate-50", label: "Pending" };
  }, [draft.duplicateStatus]);

  const virusScanStatus = useMemo(() => {
    const s = (draft.virusStatus || "").toUpperCase();
    if (s === "CLEAN") {
      return { icon: CheckCircle2, color: "text-emerald-600", bg: "bg-emerald-50", label: "Clean" };
    }
    if (s === "INFECTED") {
      return { icon: AlertCircle, color: "text-red-600", bg: "bg-red-50", label: "Infected" };
    }
    return { icon: Clock, color: "text-slate-400", bg: "bg-slate-50", label: "Pending" };
  }, [draft.virusStatus]);

  const isReadyForCompletion = (draft.duplicateStatus || "").toUpperCase() === "CLEAR" && (draft.virusStatus || "").toUpperCase() === "CLEAN";
  // Calculate verification progress
  const verificationProgress = useMemo(() => {
    const zone = document?.zone;
    const section = document?.section;
    const artifact = document?.artifact;
    const subArtifact = document?.subArtifact;

    const items = [zone, section, artifact, subArtifact].filter(Boolean);
    if (items.length === 0) return { verified: 0, total: 0, percentage: 100 };

    const verified = [
      zone && draft?.metadataVerification?.zoneVerified,
      section && draft?.metadataVerification?.sectionVerified,
      artifact && draft?.metadataVerification?.artifactVerified,
      subArtifact && draft?.metadataVerification?.subArtifactVerified,
    ].filter(Boolean).length;

    return { verified, total: items.length, percentage: Math.round((verified / items.length) * 100) };
  }, [document, draft?.metadataVerification]);

  // States for editable TMF structure - purely string-based to match draft
  // States for editable TMF structure - purely string-based to match draft
  const [selectedZone, setSelectedZone] = useState("");
  const [selectedSection, setSelectedSection] = useState("");
  const [selectedArtifact, setSelectedArtifact] = useState("");
  const [selectedSubArtifact, setSelectedSubArtifact] = useState("");

  // Sync internal dropdown state when draft changes with normalization
  useEffect(() => {
    setSelectedZone(normalizeTMF(draft.zoneNumber));
    setSelectedSection(normalizeTMF(draft.sectionNumber));
    setSelectedArtifact(normalizeTMF(draft.artifactNumber));
    setSelectedSubArtifact(draft.subArtifactName ? String(draft.subArtifactName) : "");
  }, [draft.zoneNumber, draft.sectionNumber, draft.artifactNumber, draft.subArtifactName]);

  // Auto-populate metadata when artifact changes or from AI suggestions
  useEffect(() => {
    const artNum = draft.artifactNumber;

    // 1. Logic for TMF Reference Model auto-population
    if (artNum && artifactSubartifacts[artNum]) {
      const metadata = artifactSubartifacts[artNum];
      merge(prev => {
        const update = {};
        if (!prev.processBasedMetadata) update.processBasedMetadata = metadata.definition || "";
        if (!prev.coreOrRecommended) update.coreOrRecommended = metadata.coreOrRecommended || "";
        const formatMultipleValues = (val) => {
          if (!val) return "";
          if (typeof val !== 'string') return val;
          return val.split(/[\n,]/).map(s => s.trim()).filter(Boolean).join(', ');
        };
        if (!prev.ichCode) update.ichCode = formatMultipleValues(metadata.ichCode);
        if (!prev.iso14155Reference) update.iso14155Reference = formatMultipleValues(metadata.iso14155Reference);
        if (!prev.uniqueIdNumber) update.uniqueIdNumber = metadata.uniqueIdNumber || "";
        if (prev.sponsorDocument === undefined) update.sponsorDocument = metadata.sponsorDocument || false;
        if (prev.investigatorDocument === undefined) update.investigatorDocument = metadata.investigatorDocument || false;
        if (!prev.processNumber) update.processNumber = metadata.processNumber || "";
        if (!prev.processName) update.processName = metadata.processName || "";

        if (prev.trialLevelDocument === undefined) update.trialLevelDocument = toBool(metadata.trialLevelDocument);
        if (!prev.trialLevelMilestoneEvent) update.trialLevelMilestoneEvent = metadata.trialLevelMilestone || "";
        if (prev.countryRegionLevelDocument === undefined) update.countryRegionLevelDocument = toBool(metadata.countryLevelDocument);
        if (!prev.countryLevelMilestoneEvent) update.countryLevelMilestoneEvent = metadata.countryLevelMilestone || "";
        if (prev.siteLevelDocument === undefined) update.siteLevelDocument = toBool(metadata.siteLevelDocument);
        if (!prev.siteLevelMilestoneEvent) update.siteLevelMilestoneEvent = metadata.siteLevelMilestone || "";

        if (!prev.tmfLevel) {
          if (metadata.trialLevelDocument) update.tmfLevel = "Trial";
          else if (metadata.countryLevelDocument) update.tmfLevel = "Country";
          else if (metadata.siteLevelDocument) update.tmfLevel = "Site";
        }
        return Object.keys(update).length > 0 ? { ...prev, ...update } : prev;
      });
    }
  }, [draft.artifactNumber]);

  // 2. Separate useEffect for auto-populating draft from document prop or AI suggestions
  useEffect(() => {
    if (!document) return;

    // A. Extract suggestions from classification results
    const suggestions = document?.classificationResults?.[0]?.result?.classification ||
      document?.extractedMetadata ||
      {};

    // B. Extract metadata from document.customMetadata.tmfMetadata (support API snake_case)
    const customMeta = document?.customMetadata ?? document?.custom_metadata;
    const tmfMetadata = customMeta?.tmfMetadata || {};

    merge(prev => {
      const update = {};
      const docTitleVal = document.title ?? document.documentTitle;
      const docTypeVal = document.documentType ?? document.document_type;
      const tmfRefVal = document.tmfReference ?? document.tmf_reference;
      const docDateVal = document.documentDate ?? document.document_date;
      const pageCountVal = document.pageCount ?? document.page_count;

      // 1. Populate fundamental fields from document root
      if (!prev.documentTitle && docTitleVal) {
        update.documentTitle = docTitleVal;
      }
      if (!prev.description && document.description) update.description = document.description;
      if (!prev.documentType && docTypeVal) update.documentType = docTypeVal;
      if (!prev.version && document.version != null) update.version = document.version;
      if (!prev.tmfReference && tmfRefVal) update.tmfReference = tmfRefVal;
      if (!prev.documentDate && docDateVal) update.documentDate = docDateVal;
      if (!prev.language && document.language) update.language = String(document.language).toLowerCase();
      if (!prev.author && document.author) update.author = typeof document.author === 'string' ? document.author : (document.author != null ? String(document.author) : '');

      // Status population with normalization
      if (!prev.status && document.status) {
        const s = String(document.status).toLowerCase();
        if (s === 'draft') update.status = 'Draft';
        else if (s === 'final') update.status = 'Final';
        else if (s === 'superseded') update.status = 'Superseded';
        else if (s === 'obsolete') update.status = 'Obsolete';
        else update.status = document.status;
      }

      if (prev.pageCount == null && pageCountVal != null) update.pageCount = pageCountVal;

      // Virus/Duplicate status normalization
      const getValidStatus = (...statuses) => {
        const valid = statuses.find(s => s && String(s).toUpperCase() !== 'UNKNOWN' && String(s).toUpperCase() !== 'PENDING');
        return valid || statuses[0] || "PENDING";
      };

      const virusStatus = getValidStatus(
        document.workflow?.intake?.virusScan?.status,
        document.virusStatus,
        document.virus_status,
        customMeta?.validation?.virusScan?.status
      );
      
      const duplicateStatus = getValidStatus(
        document.workflow?.intake?.duplicateCheck?.status,
        document.duplicateStatus,
        document.duplicate_status,
        "CLEAR" 
      );
      
      if (virusStatus) update.virusStatus = String(virusStatus).toUpperCase();
      if (duplicateStatus) update.duplicateStatus = String(duplicateStatus).toUpperCase();

      // 2. Populate TMF Hierarchy from document objects or tmfReference fallback
      const populateFromTMFReference = (tmfRef) => {
        if (!tmfRef) return null;
        const parts = tmfRef.split('.');
        if (parts.length >= 3) {
          const [zoneNum, sectionNum, artifactNum] = parts;
          return {
            zone: zoneNum.padStart(2, '0'),
            section: sectionNum.padStart(2, '0'),
            artifact: artifactNum.padStart(2, '0')
          };
        }
        return null;
      };

      // Zone population
      if (!prev.zoneNumber) {
        if (document.zone && typeof document.zone === 'object' && document.zone.zoneNumber !== undefined) {
          // Populated zone object (Neurodoc style)
          const zn = document.zone.zoneNumber !== undefined ? document.zone.zoneNumber : document.zone;
          update.zoneNumber = String(zn);
          update.zoneName = document.zone.zoneName || "";
        } else if (tmfRefVal) {
          // Fallback to tmfReference parsing (ObjectId case)
          const tmfData = populateFromTMFReference(tmfRefVal);
          if (tmfData) {
            update.zoneNumber = tmfData.zone;
            // Find zone name from hierarchyData
            const zoneInfo = hierarchyData.find(z => normalizeTMF(z.Zone.Number) === tmfData.zone);
            update.zoneName = zoneInfo?.Zone.Name || "";
            // Update selected state immediately for pre-selection
            setSelectedZone(tmfData.zone);
          }
        }
      }

      // Section population
      if (!prev.sectionNumber) {
        if (document.section && typeof document.section === 'object' && document.section.sectionNumber !== undefined) {
          // Populated section object (Neurodoc style)
          const fullSec = String(document.section.sectionNumber !== undefined ? document.section.sectionNumber : document.section);
          const secNum = fullSec.includes(':') ? fullSec.split(':')[0].trim() : fullSec.trim();
          update.sectionNumber = secNum;
          update.sectionName = document.section.sectionName || "";
        } else if (tmfRefVal) {
          // Fallback to tmfReference parsing (ObjectId case)
          const tmfData = populateFromTMFReference(tmfRefVal);
          if (tmfData) {
            update.sectionNumber = tmfData.section.replace(/^0+/, ''); // Remove leading zero for display
            // Find section name from hierarchyData
            const zoneInfo = hierarchyData.find(z => normalizeTMF(z.Zone.Number) === tmfData.zone);
            const sectionInfo = zoneInfo?.Sections?.find(s => normalizeTMF(s.Section.Number) === normalizeTMF(`${tmfData.zone}.${tmfData.section}`));
            update.sectionName = sectionInfo?.Section.Name || "";
            // Update selected state immediately for pre-selection
            setSelectedSection(tmfData.section.replace(/^0+/, ''));
          }
        }
      }

      // Artifact population
      if (!prev.artifactNumber) {
        if (document.artifact && typeof document.artifact === 'object' && document.artifact.artifactNumber !== undefined) {
          // Populated artifact object (Neurodoc style)
          const fullArt = String(document.artifact.artifactNumber !== undefined ? document.artifact.artifactNumber : document.artifact);
          const artNum = fullArt.includes(' ') ? fullArt.split(' ')[0].trim() : fullArt.trim();
          update.artifactNumber = artNum;
          update.artifactName = document.artifact.artifactName || "";
        } else if (tmfRefVal) {
          // Fallback to tmfReference parsing (ObjectId case)
          const tmfData = populateFromTMFReference(tmfRefVal);
          if (tmfData) {
            update.artifactNumber = tmfData.artifact.replace(/^0+/, ''); // Remove leading zero for display
            // Find artifact name from hierarchyData
            const zoneInfo = hierarchyData.find(z => normalizeTMF(z.Zone.Number) === tmfData.zone);
            const sectionInfo = zoneInfo?.Sections?.find(s => normalizeTMF(s.Section.Number) === normalizeTMF(`${tmfData.zone}.${tmfData.section}`));
            const artifactInfo = sectionInfo?.Artifacts?.find(a => normalizeTMF(a.Artifact.Number) === normalizeTMF(`${tmfData.zone}.${tmfData.section}.${tmfData.artifact}`));
            update.artifactName = artifactInfo?.Artifact.Name || "";
            // Update selected state immediately for pre-selection
            setSelectedArtifact(tmfData.artifact.replace(/^0+/, ''));
          }
        }
      }

      // SubArtifact population
      if (!prev.subArtifactName) {
        if (document.subArtifact && typeof document.subArtifact === 'object' && document.subArtifact.subArtifactName !== undefined) {
          // Populated subArtifact object (Neurodoc style)
          update.subArtifactName = String(document.subArtifact.subArtifactName !== undefined ? document.subArtifact.subArtifactName : document.subArtifact);
          // Update selected state immediately for pre-selection
          setSelectedSubArtifact(String(document.subArtifact.subArtifactName !== undefined ? document.subArtifact.subArtifactName : document.subArtifact));
        } else if (tmfRefVal) {
          // Fallback: find sub-artifacts from hierarchyData using tmfReference
          const tmfData = populateFromTMFReference(tmfRefVal);
          if (tmfData) {
            // Find the artifact in hierarchyData to get sub-artifacts
            const zoneInfo = hierarchyData.find(z => normalizeTMF(z.Zone.Number) === tmfData.zone);
            const sectionInfo = zoneInfo?.Sections?.find(s => normalizeTMF(s.Section.Number) === normalizeTMF(`${tmfData.zone}.${tmfData.section}`));
            const artifactInfo = sectionInfo?.Artifacts?.find(a => normalizeTMF(a.Artifact.Number) === normalizeTMF(`${tmfData.zone}.${tmfData.section}.${tmfData.artifact}`));
            const subArtifacts = artifactInfo?.SubArtifacts || [];
            
            if (subArtifacts.length > 0) {
              // For now, select the first sub-artifact (could be enhanced with specific logic)
              const firstSubArtifact = subArtifacts[0].Name;
              update.subArtifactName = firstSubArtifact;
              // Update selected state immediately for pre-selection
              setSelectedSubArtifact(firstSubArtifact);
            }
          }
        }
      }

      // 3. Populate from customMetadata.tmfMetadata
      Object.keys(tmfMetadata).forEach(key => {
        if (!prev[key] && tmfMetadata[key] !== undefined && tmfMetadata[key] !== null) {
          // Handle boolean flags specially
          if (['trialLevelDocument', 'countryRegionLevelDocument', 'siteLevelDocument', 'sponsorDocument', 'investigatorDocument', 'mandatory'].includes(key)) {
            update[key] = toBool(tmfMetadata[key]);
          } else {
            update[key] = tmfMetadata[key];
          }
        }
      });

      // 4. AI suggestions (highest precedence for empty fields)
      if (Object.keys(suggestions).length > 0) {
        if (!prev.documentTitle && (suggestions.suggestedTitle || suggestions.title)) {
          update.documentTitle = suggestions.suggestedTitle || suggestions.title;
        }
        if (!prev.description && (suggestions.suggestedDescription || suggestions.description)) {
          update.description = suggestions.suggestedDescription || suggestions.description;
        }
        if (!prev.documentType && (suggestions.suggestedDocumentType || suggestions.documentType)) {
          update.documentType = suggestions.suggestedDocumentType || suggestions.documentType;
        }
        if (!prev.tmfReference && (suggestions.tmfReference)) {
          update.tmfReference = suggestions.tmfReference;
        }
        if (!prev.language && (suggestions.language)) {
          update.language = String(suggestions.language).toLowerCase();
        }
        if (!prev.author && (suggestions.author)) {
          update.author = suggestions.author;
        }
        if (!prev.documentDate && (suggestions.documentDate)) {
          update.documentDate = suggestions.documentDate;
        }

        // Hierarchy suggestions (overrides root if present)
        if (!prev.zoneNumber && suggestions.suggestedZone?.number) {
          update.zoneNumber = String(suggestions.suggestedZone.number);
          update.zoneName = suggestions.suggestedZone.name || "";
        }
        if (!prev.sectionNumber && suggestions.suggestedSection?.number) {
          update.sectionNumber = String(suggestions.suggestedSection.number);
          update.sectionName = suggestions.suggestedSection.name || "";
        }
        if (!prev.artifactNumber && suggestions.suggestedArtifact?.number) {
          update.artifactNumber = String(suggestions.suggestedArtifact.number);
          update.artifactName = suggestions.suggestedArtifact.name || "";
        }
      }

      return Object.keys(update).length > 0 ? { ...prev, ...update } : prev;
    });
  }, [document]);

  const zones = getZonesFromHierarchy(hierarchyData);
  const currentZoneData = hierarchyData.find(z => normalizeTMF(z.Zone.Number) === selectedZone);
  const availableSections = currentZoneData?.Sections || [];
  const currentSectionData = availableSections.find(s => {
  const sectionNumber = normalizeTMF(s.Section.Number);
  // Handle both formats: "01" should match "8.01" -> "08.01"
  const selectedSectionFormatted = selectedZone ? `${selectedZone}.${selectedSection.padStart(2, '0')}` : selectedSection;
  return sectionNumber === selectedSectionFormatted;
});
  const availableArtifacts = currentSectionData?.Artifacts || [];
  const currentArtifactData = availableArtifacts.find(a => {
  const artifactNumber = normalizeTMF(a.Artifact.Number);
  // Handle both formats: "04" should match "08.01.04"
  const selectedArtifactFormatted = selectedZone && selectedSection ? `${selectedZone}.${selectedSection.padStart(2, '0')}.${selectedArtifact.padStart(2, '0')}` : selectedArtifact;
  return artifactNumber === selectedArtifactFormatted;
});
  const availableSubArtifacts = currentArtifactData?.SubArtifacts || [];

  const isDisabled = draft.markComplete;

  // Normalize document for display (support both camelCase and API snake_case)
  const doc = document || {};
  const docTitle = doc.title ?? doc.documentTitle;
  const docType = doc.documentType ?? doc.document_type;
  const docVersion = doc.version ?? 1;
  const tmfRef = doc.tmfReference ?? doc.tmf_reference;
  const docDate = doc.documentDate ?? doc.document_date;
  const docLang = doc.language;
  const fileSizeMb = ((doc.fileSize ?? doc.file_size ?? 0) / 1024 / 1024).toFixed(2);
  const ingestionType = doc.ingestionType ?? doc.ingestion_type;
  const customMeta = doc.customMetadata ?? doc.custom_metadata;

  return (
    <div className="space-y-3 pb-6">
      {/* Top Row: Document Overview & Security & Compliance */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Document Overview Card */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/30">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center shadow-indigo-100 shadow-lg">
                <FileText className="h-5 w-5 text-white" />
              </div>
              <div className="min-w-0">
                <h3 className="text-sm font-bold text-slate-900 truncate">
                  {docTitle || "Untitled Document"}
                </h3>
                <div className="flex items-center gap-2 mt-0.5">
                  <Badge variant="secondary" className="text-[10px] h-4.5 px-1.5 font-semibold bg-slate-100 text-slate-600">
                    {docType || "Unknown Type"}
                  </Badge>
                  <span className="text-[11px] font-medium text-slate-400">v{docVersion}</span>
                </div>
              </div>
            </div>
            {tmfRef && (
              <Badge className="bg-indigo-50 text-indigo-700 hover:bg-indigo-50 border-indigo-100 text-[11px] font-mono px-2 py-0.5">
                {tmfRef}
              </Badge>
            )}
          </div>

          <div className="p-4 flex-1 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-slate-600">
                  <Calendar className="h-3.5 w-3.5 text-slate-400" />
                  <div className="flex flex-col">
                    <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Date</span>
                    <span className="text-xs font-semibold">{docDate ? new Date(docDate).toLocaleDateString() : "N/A"}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-slate-600">
                  <Globe className="h-3.5 w-3.5 text-slate-400" />
                  <div className="flex flex-col">
                    <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Language</span>
                    <span className="text-xs font-semibold">{(docLang && String(docLang).toUpperCase()) || "N/A"}</span>
                  </div>
                </div>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-slate-600">
                  <Hash className="h-3.5 w-3.5 text-slate-400" />
                  <div className="flex flex-col">
                    <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Size</span>
                    <span className="text-xs font-semibold">{fileSizeMb} MB</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-slate-600">
                  <Building2 className="h-3.5 w-3.5 text-slate-400" />
                  <div className="flex flex-col">
                    <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Study</span>
                    <span className="text-xs font-semibold truncate max-w-[150px]">
                      {studyTitle || "N/A"}
                    </span>
                  </div>
                </div>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-slate-600">
                  <FileText className="h-3.5 w-3.5 text-slate-400" />
                  <div className="flex flex-col">
                    <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">Ingestion Method</span>
                    <span className="text-xs font-semibold">{ingestionType || "N/A"}</span>
                  </div>
                </div>
              </div>
            </div>
            {(doc.description != null && doc.description !== '') && (
              <div className="pt-3 border-t border-slate-50">
                <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400 block mb-0.5">Description</span>
                <p className="text-xs text-slate-600 leading-relaxed line-clamp-2">
                  {doc.description}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Security & Compliance Card */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/30 flex items-center justify-between">
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Security & Compliance</h4>
            <Badge className="bg-emerald-50 text-emerald-700 border-none shadow-none text-[10px] px-1.5 h-4.5">Automated</Badge>
          </div>
          <div className="p-4 space-y-3 flex-1">
            <div>
              <p className="text-[11px] text-slate-500 leading-snug">
                Safety and integrity validations performed automatically during ingestion to ensure document health.
              </p>
            </div>

            <div className="space-y-3">
              <div className={cn(
                "p-3 rounded-xl border flex items-center justify-between gap-3 transition-all",
                virusScanStatus.bg, "border-slate-100"
              )}>
                <div className="flex items-center gap-2.5">
                  <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center", virusScanStatus.bg)}>
                    <virusScanStatus.icon className={cn("h-4 w-4", virusScanStatus.color)} />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold uppercase text-slate-400 tracking-tight">Virus Scan</span>
                    <span className={cn("text-xs font-bold", virusScanStatus.color)}>{virusScanStatus.label}</span>
                  </div>
                </div>
                {draft.virusStatus === "CLEAN" && <CheckCheck className="h-3.5 w-3.5 text-emerald-500" />}
              </div>

              <div className={cn(
                "p-3 rounded-xl border flex items-center justify-between gap-3 transition-all",
                duplicateCheckStatus.bg, "border-slate-100"
              )}>
                <div className="flex items-center gap-2.5">
                  <div className={cn("w-7 h-7 rounded-lg flex items-center justify-center", duplicateCheckStatus.bg)}>
                    <duplicateCheckStatus.icon className={cn("h-4 w-4", duplicateCheckStatus.color)} />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold uppercase text-slate-400 tracking-tight">Duplicate Check</span>
                    <span className={cn("text-xs font-bold", duplicateCheckStatus.color)}>{duplicateCheckStatus.label}</span>
                  </div>
                </div>
                {draft.duplicateStatus === "CLEAR" && <CheckCheck className="h-3.5 w-3.5 text-emerald-500" />}
              </div>
            </div>
          </div>
        </div>

        {/* Legibility & Page Validation Card */}
        <div className="rounded-2xl border border-blue-200 bg-white shadow-sm overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-blue-100 bg-blue-50/40 flex items-center justify-between">
            <h4 className="text-xs font-bold text-blue-700 uppercase tracking-widest">
              Legibility
            </h4>
            <Badge className="bg-blue-100 text-blue-700 border-none text-[10px] px-1.5 h-4.5">
              Automated
            </Badge>
          </div>

          <div className="p-4 flex-1 flex flex-col justify-between">
            <div className="flex items-start gap-3">
              <div className="text-xs leading-relaxed">
                <p className="font-bold text-blue-900 mb-0.5">
                  Document Legibility & Page Count
                </p>
                <p className="text-blue-700/80 mt-2 italic">
                  The system validates extractable text availability for machine reading
                  and verifies total page count against study requirements.
                </p>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-blue-100/50 space-y-2">
              <Label className="text-[10px] font-bold text-blue-700 uppercase tracking-wider">Clear option</Label>
              <Select
                value={draft.legibilityClear || "Select Option"}
                onValueChange={(val) => {
                  merge({ legibilityClear: val });  // updates parent state
                  onLegibilityChange?.(val);           // optional side-effects
                }}
                disabled={isDisabled}
              >
                <SelectTrigger className={cn(
                  "h-9 text-xs font-bold transition-all border-2",
                  draft.legibilityClear === "CLEAR"
                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                    : draft.legibilityClear === "UNCLEAR"
                      ? "bg-red-50 text-red-700 border-red-200"
                      : ""
                )}>
                  <SelectValue placeholder="Select Option" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Select Option" className="font-bold focus:bg-emerald-50 focus:text-emerald-700">Select Option</SelectItem>
                  <SelectItem value="CLEAR" className="text-emerald-700 font-bold focus:bg-emerald-50 focus:text-emerald-700">Clear</SelectItem>
                  <SelectItem value="UNCLEAR" className="text-red-700 font-bold focus:bg-red-50 focus:text-red-700">Unclear</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </div>

      {/* 1. Core Document Information */}
      <Card className="border-slate-200 shadow-sm overflow-hidden rounded-2xl">
        <CardHeader className="bg-slate-50/50 border-b border-slate-100 py-2.5">
          <CardTitle className="text-sm font-bold flex items-center gap-2">
            <FileText className="h-4 w-4 text-indigo-600" />
            Core Document Information
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-1">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Document Title</Label>
              <Input
                value={draft.documentTitle || draft.title || ""}
                onChange={handleTextChange("documentTitle")}
                disabled={isDisabled}
                className="h-10 bg-slate-50/50 border-slate-200"
              />
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">Document Type</Label>
              <Select value={draft.documentType || ""} onValueChange={handleSelectChange("documentType")} disabled={isDisabled}>
                <SelectTrigger className="h-10 bg-slate-50/50 border-slate-200">
                  <SelectValue placeholder="Select Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PROTOCOL">Protocol</SelectItem>
                  <SelectItem value="INVESTIGATOR_BROCHURE">Investigator Brochure</SelectItem>
                  <SelectItem value="INFORMED_CONSENT">Informed Consent</SelectItem>
                  <SelectItem value="REGULATORY_DOCUMENT">Regulatory Document</SelectItem>
                  <SelectItem value="CLINICAL_REPORT">Clinical Report</SelectItem>
                  <SelectItem value="SAFETY_REPORT">Safety Report</SelectItem>
                  <SelectItem value="QUALITY_DOCUMENT">Quality Document</SelectItem>
                  <SelectItem value="TRAINING_DOCUMENT">Training Document</SelectItem>
                  <SelectItem value="OTHER">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Version</Label>
              <Input value={draft.version || ""} onChange={handleTextChange("version")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">TMF Reference</Label>
              <Input value={draft.tmfReference || ""} onChange={handleTextChange("tmfReference")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Document Date</Label>
              <Input type="date" value={draft.documentDate ? new Date(draft.documentDate).toISOString().split('T')[0] : ""} onChange={handleTextChange("documentDate")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Approval Date</Label>
              <Input type="date" value={draft.approvalDate ? new Date(draft.approvalDate).toISOString().split('T')[0] : ""} onChange={handleTextChange("approvalDate")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Language</Label>
              <Select value={draft.language || "en"} onValueChange={handleSelectChange("language")} disabled={isDisabled}>
                <SelectTrigger className="h-10 bg-slate-50/50 border-slate-200">
                  <SelectValue placeholder="Select Language" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="es">Spanish</SelectItem>
                  <SelectItem value="fr">French</SelectItem>
                  <SelectItem value="de">German</SelectItem>
                  <SelectItem value="it">Italian</SelectItem>
                  <SelectItem value="ja">Japanese</SelectItem>
                  <SelectItem value="zh">Chinese</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {/* <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Author</Label>
              <Input value={draft.author || ""} onChange={handleTextChange("author")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div> */}

            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">Page Count</Label>
              <Input type="number" value={draft.pageCount || ""} onChange={handleTextChange("pageCount")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>

            <div className="space-y-1.5 lg:col-span-2">
              <Label className="text-xs font-bold text-slate-700">Description</Label>
              <Textarea
                value={draft.description || ""}
                onChange={handleTextChange("description")}
                disabled={isDisabled}
                rows={4}
                className="bg-slate-50/50 border-slate-200 resize-none"
                placeholder="Enter description..."
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 2. TMF Classification & Hierarchy */}
      <Card className="border-slate-200 shadow-sm overflow-hidden rounded-2xl">
        <CardHeader className="bg-slate-50/50 border-b border-slate-100 py-2.5">
          <CardTitle className="text-sm font-bold flex items-center gap-2">
            <Layers className="h-4 w-4 text-indigo-600" />
            TMF Classification & Hierarchy
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">Zone</Label>
              <Select
                value={selectedZone || ""}
                onValueChange={(val) => {
                  const zone = zones.find(z => normalizeTMF(z.number) === val);
                  merge({ 
                    zoneNumber: val, 
                    zoneName: zone?.name || "",
                    sectionNumber: "",
                    sectionName: "",
                    artifactNumber: "",
                    artifactName: "",
                    subArtifactName: ""
                  });
                }}
                disabled={isDisabled}
              >
                <SelectTrigger className="h-10 bg-slate-50/50 border-slate-200">
                  <SelectValue placeholder="Select Zone" />
                </SelectTrigger>
                <SelectContent>
                  {zones.map(z => (
                    <SelectItem key={z.number} value={normalizeTMF(z.number)}>{z.number}. {z.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">Section</Label>
              <Select
                value={selectedZone && selectedSection ? `${selectedZone}.${selectedSection.padStart(2, '0')}` : selectedSection || ""}
                onValueChange={(val) => {
                  const sec = availableSections.find(s => normalizeTMF(s.Section.Number) === val);
                  // Extract the section number part (e.g., "08.01" -> "01")
                  const sectionNumber = val.split('.').slice(1).join('.');
                  merge({ 
                    sectionNumber: sectionNumber.replace(/^0+/, ''), // Remove leading zero for storage
                    sectionName: sec?.Section.Name || "",
                    artifactNumber: "",
                    artifactName: "",
                    subArtifactName: ""
                  });
                }}
                disabled={isDisabled || !selectedZone}
              >
                <SelectTrigger className="h-10 bg-slate-50/50 border-slate-200">
                  <SelectValue placeholder="Select Section" />
                </SelectTrigger>
                <SelectContent>
                  {availableSections.map(s => (
                    <SelectItem key={s.Section.Number} value={normalizeTMF(s.Section.Number)}>
                      {s.Section.Number} {s.Section.Name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">Artifact</Label>
              <Select
                value={selectedZone && selectedSection && selectedArtifact ? `${selectedZone}.${selectedSection.padStart(2, '0')}.${selectedArtifact.padStart(2, '0')}` : selectedArtifact || ""}
                onValueChange={(val) => {
                  const art = availableArtifacts.find(a => normalizeTMF(a.Artifact.Number) === val);
                  // Extract the artifact number part (e.g., "08.01.04" -> "04")
                  const artifactNumber = val.split('.').slice(2).join('.');
                  merge({ 
                    artifactNumber: artifactNumber.replace(/^0+/, ''), // Remove leading zero for storage
                    artifactName: art?.Artifact.Name || "",
                    subArtifactName: ""
                  });
                }}
                disabled={isDisabled || !selectedSection}
              >
                <SelectTrigger className="h-10 bg-slate-50/50 border-slate-200">
                  <SelectValue placeholder="Select Artifact" />
                </SelectTrigger>
                <SelectContent>
                  {availableArtifacts.map(a => (
                    <SelectItem key={a.Artifact.Number} value={normalizeTMF(a.Artifact.Number)}>
                      {a.Artifact.Number} {a.Artifact.Name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">Sub-Artifact</Label>
              <Select
                value={selectedSubArtifact ? String(selectedSubArtifact) : ""}
                onValueChange={(val) => {
                  setSelectedSubArtifact(val);
                  merge({ subArtifactName: val });
                }}
                disabled={isDisabled || !selectedArtifact}
              >
                <SelectTrigger className="h-10 bg-slate-50/50 border-slate-200">
                  <SelectValue placeholder="Select Sub-Artifact" />
                </SelectTrigger>
                <SelectContent>
                  {availableSubArtifacts.map(sa => (
                    <SelectItem key={sa.Name} value={sa.Name}>{sa.Name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 4. TMF Metadata & Regulatory Details */}
      <Card className="border-slate-200 shadow-sm overflow-hidden rounded-2xl">
        <CardHeader className="bg-slate-50/50 border-b border-slate-100 py-2.5">
          <CardTitle className="text-sm font-bold flex items-center gap-2">
            <Shield className="h-4 w-4 text-indigo-600" />
            TMF Metadata & Regulatory Details
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="space-y-2 lg:col-span-3">
              <Label className="text-xs font-bold text-slate-700">Definition / Purpose</Label>
              <Textarea
                value={draft.processBasedMetadata || ""}
                onChange={handleTextChange("processBasedMetadata")}
                disabled={isDisabled}
                className="bg-slate-50/50 border-slate-200 min-h-[80px]"
                placeholder="Auto-populated from TMF Reference Model"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">TMF Level</Label>
              <Select value={draft.tmfLevel || ""} onValueChange={handleSelectChange("tmfLevel")} disabled={isDisabled}>
                <SelectTrigger className="h-10 bg-slate-50/50 border-slate-200">
                  <SelectValue placeholder="Select TMF level" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Trial">Trial Level</SelectItem>
                  <SelectItem value="Country">Country/Region Level</SelectItem>
                  <SelectItem value="Site">Site Level</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">Core or Recommended</Label>
              <Select value={draft.coreOrRecommended || ""} onValueChange={handleSelectChange("coreOrRecommended")} disabled={isDisabled}>
                <SelectTrigger className="h-10 bg-slate-50/50 border-slate-200">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Core">Core</SelectItem>
                  <SelectItem value="Recommended">Recommended</SelectItem>
                  <SelectItem value="Optional">Optional</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">ICH Code</Label>
              <Input value={draft.ichCode || ""} onChange={handleTextChange("ichCode")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-700">ISO 14155 Reference</Label>
              <Input value={draft.iso14155Reference || ""} onChange={handleTextChange("iso14155Reference")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Unique ID Number</Label>
              <Input value={draft.uniqueIdNumber || ""} onChange={handleTextChange("uniqueIdNumber")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
            <div className="flex items-center space-x-6 pt-4">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="sponsorDocument"
                  checked={draft.sponsorDocument === true}
                  onCheckedChange={(checked) => merge({ sponsorDocument: checked === true })}
                  disabled={isDisabled}
                />
                <Label htmlFor="sponsorDocument" className="text-xs font-bold text-slate-700 cursor-pointer">Sponsor Document</Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="investigatorDocument"
                  checked={draft.investigatorDocument === true}
                  onCheckedChange={(checked) => merge({ investigatorDocument: checked === true })}
                  disabled={isDisabled}
                />
                <Label htmlFor="investigatorDocument" className="text-xs font-bold text-slate-700 cursor-pointer">Investigator Document</Label>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 6. Process Information & Milestones */}
      <Card className="border-slate-200 shadow-sm overflow-hidden rounded-2xl">
        <CardHeader className="bg-slate-50/50 border-b border-slate-100 py-2.5">
          <CardTitle className="text-sm font-bold flex items-center gap-2">
            <Zap className="h-4 w-4 text-indigo-600" />
            Process Information & Milestones
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-1">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-3 mb-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Process Number</Label>
              <Input value={draft.processNumber || ""} onChange={handleTextChange("processNumber")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold text-slate-700">Process Name</Label>
              <Input value={draft.processName || ""} onChange={handleTextChange("processName")} disabled={isDisabled} className="h-10 bg-slate-50/50 border-slate-200" />
            </div>
          </div>

          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Trial Level */}
              <div className="space-y-3 p-4 rounded-xl border border-slate-100 bg-slate-50/30">
                <div className="flex items-center gap-2 mb-2">
                  <Layout className="h-4 w-4 text-indigo-500" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Trial Level</span>
                </div>
                <Select
                  value={draft.trialLevelDocument?.toString()}
                  onValueChange={(val) => merge({ trialLevelDocument: val === "true" })}
                  disabled={isDisabled}
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue placeholder="Relevant?" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">Yes</SelectItem>
                    <SelectItem value="false">No</SelectItem>
                  </SelectContent>
                </Select>
                {draft.trialLevelDocument === true && (
                  <div className="pt-2 animate-in fade-in slide-in-from-top-1">
                    <Label className="text-[10px] font-bold text-slate-400 uppercase">Trial Milestone</Label>
                    <Input
                      value={draft.trialLevelMilestoneEvent || ""}
                      onChange={handleTextChange("trialLevelMilestoneEvent")}
                      disabled={isDisabled}
                      className="h-8 text-xs mt-1 border-indigo-100 focus-visible:ring-indigo-500"
                      placeholder="e.g., Clinical Infrastructure Ready"
                    />
                  </div>
                )}
              </div>

              {/* Country Level */}
              <div className="space-y-3 p-4 rounded-xl border border-slate-100 bg-slate-50/30">
                <div className="flex items-center gap-2 mb-2">
                  <Flag className="h-4 w-4 text-indigo-500" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Country Level</span>
                </div>
                <Select
                  value={draft.countryRegionLevelDocument?.toString()}
                  onValueChange={(val) => merge({ countryRegionLevelDocument: val === "true" })}
                  disabled={isDisabled}
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue placeholder="Relevant?" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">Yes</SelectItem>
                    <SelectItem value="false">No</SelectItem>
                  </SelectContent>
                </Select>
                {draft.countryRegionLevelDocument === true && (
                  <div className="pt-2 animate-in fade-in slide-in-from-top-1">
                    <Label className="text-[10px] font-bold text-slate-400 uppercase">Country Milestone</Label>
                    <Input
                      value={draft.countryLevelMilestoneEvent || ""}
                      onChange={handleTextChange("countryLevelMilestoneEvent")}
                      disabled={isDisabled}
                      className="h-8 text-xs mt-1 border-indigo-100 focus-visible:ring-indigo-500"
                      placeholder="e.g., First Country RA Approval"
                    />
                  </div>
                )}
              </div>

              {/* Site Level */}
              <div className="space-y-3 p-4 rounded-xl border border-slate-100 bg-slate-50/30">
                <div className="flex items-center gap-2 mb-2">
                  <MapPin className="h-4 w-4 text-indigo-500" />
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Site Level</span>
                </div>
                <Select
                  value={draft.siteLevelDocument?.toString()}
                  onValueChange={(val) => merge({ siteLevelDocument: val === "true" })}
                  disabled={isDisabled}
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue placeholder="Relevant?" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="true">Yes</SelectItem>
                    <SelectItem value="false">No</SelectItem>
                  </SelectContent>
                </Select>
                {draft.siteLevelDocument === true && (
                  <div className="pt-2 animate-in fade-in slide-in-from-top-1">
                    <Label className="text-[10px] font-bold text-slate-400 uppercase">Site Milestone</Label>
                    <Input
                      value={draft.siteLevelMilestoneEvent || ""}
                      onChange={handleTextChange("siteLevelMilestoneEvent")}
                      disabled={isDisabled}
                      className="h-8 text-xs mt-1 border-indigo-100 focus-visible:ring-indigo-500"
                      placeholder="e.g., 01 Investigator Site Set-up"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Completion Section */}
      <div className={cn(
        "rounded-2xl border-2 p-6 transition-all shadow-sm",
        isReadyForCompletion && draft.markComplete
          ? "border-emerald-300 bg-gradient-to-br from-emerald-50 to-green-50/50"
          : isReadyForCompletion
            ? "border-emerald-200 bg-emerald-50/30"
            : "border-slate-200 bg-slate-50/50"
      )}>
        <div className="flex items-start gap-4">
          <Checkbox
            id="mark-complete"
            checked={draft.markComplete}
            onCheckedChange={handleCheckboxChange("markComplete")}
            className={cn(
              "mt-1 h-6 w-6 rounded-md",
              draft.markComplete &&
              isReadyForCompletion &&
              "border-emerald-500 bg-emerald-500"
            )}
          />

          <div className="flex-1 space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <Label htmlFor="mark-complete" className="text-base font-bold text-slate-900 cursor-pointer">
                Mark Intake Complete
              </Label>
              {isReadyForCompletion ? (
                <Badge className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-700 border-none">
                  <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
                  Ready to Advance
                </Badge>
              ) : (
                <Badge className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-700 border-none">
                  <AlertCircle className="h-3.5 w-3.5 mr-1.5" />
                  Requirements Pending
                </Badge>
              )}
            </div>

            {!isReadyForCompletion && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <p className="text-xs font-bold text-amber-800 mb-2">Complete these requirements:</p>
                <ul className="text-xs text-amber-700 space-y-2">
                  {draft.duplicateStatus !== "CLEAR" && (
                    <li className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                      Set Duplicate Check to CLEAR
                    </li>
                  )}
                  {draft.virusStatus !== "CLEAN" && (
                    <li className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                      Set Virus Scan to CLEAN
                    </li>
                  )}
                  {draft.legibilityClear !== "CLEAR" && (
                    <li className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                      Set Legibility to CLEAR
                    </li>
                  )}
                </ul>
              </div>
            )}

            {isReadyForCompletion && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                <p className="text-sm font-medium text-emerald-800 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  All security and compliance checks passed. Ready to advance to QC Validation.
                </p>
              </div>
            )}

            <div className="space-y-2">
              <Label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Transition Notes (Optional)</Label>
              <Textarea
                value={draft.transitionNotes || ""}
                onChange={handleTextChange("transitionNotes")}
                placeholder="Recorded in audit trail upon completion..."
                rows={2}
                disabled={disabled || !draft.markComplete}
                className="resize-none bg-white border-slate-200"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ISFIntakeStageForm;
