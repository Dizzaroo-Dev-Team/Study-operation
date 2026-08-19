import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { 
  Folder, 
  File, 
  ChevronRight, 
  ChevronDown, 
  Plus, 
  Settings, 
  Loader2,
  Search,
  Filter,
  MoreHorizontal,
  Eye,
  Download,
  Edit,
  Trash2,
  Star,
  Clock,
  CheckCircle,
  AlertCircle,
  XCircle,
  FileText,
  FolderOpen,
  FolderPlus,
  Users,
  Shield,
  Activity,
  X,
  Building,
  Database,
  BarChart3,
  Package,
  TestTube,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronsDown,
  ChevronsUpDown,
  RefreshCw
} from 'lucide-react';
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import useTmfHierarchy from '../../hooks/useTmfHierarchy';
import { normalizeSectionNumber, normalizeTMF } from '@/utils/tmfHierarchyUtils';
import isfDocumentService from '@/services/isfDocument.service';

const getDisplayArtifactNumber = (value) => normalizeTMF(value);

const SidebarNav = ({ 
  onSelect, 
  onCreate, 
  refreshTrigger = 0,
  onRefreshDocuments,
  documents: externalDocuments,
  selectedStudy,
}) => {
  const { hierarchyData, isLoading: hierarchyLoading, refetch: refetchHierarchy } = useTmfHierarchy();
  const [expanded, setExpanded] = useState({});
  const [selectedItem, setSelectedItem] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(360); // Increased default width
  const [isDragging, setIsDragging] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Drag handlers for resizing sidebar
  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  // Add event listeners for drag functionality
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return;
      
      requestAnimationFrame(() => {
        const newWidth = e.clientX;
        const minWidth = 320; // Increased minimum width
        const maxWidth = 900; // Increased maximum width
        
        if (newWidth >= minWidth && newWidth <= maxWidth) {
          setSidebarWidth(newWidth);
        }
      });
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging]);

  // Fetch documents from API - use same service as ContentArea to get approved documents
  const fetchDocuments = async () => {
    try {
      setDocumentsLoading(true);
      // Use isfDocumentService with status=APPROVED so hierarchy counts match Approved Documents list
      const documents = await isfDocumentService.getAllDocuments({
        isfViewer: true,
        status: 'APPROVED',
        study: selectedStudy || undefined,
      });
      const docsArray = Array.isArray(documents) ? documents : [];
      console.log(`[SidebarNav] Fetched ${docsArray.length} documents for hierarchy`);
      if (docsArray.length > 0) {
        console.log(`[SidebarNav] First document sample:`, {
          title: docsArray[0].title || docsArray[0].documentTitle,
          zone: docsArray[0].zone,
          section: docsArray[0].section,
          artifact: docsArray[0].artifact,
          hasZone: !!docsArray[0].zone,
          hasSection: !!docsArray[0].section,
          hasArtifact: !!docsArray[0].artifact,
        });
      }
      setDocuments(docsArray);
    } catch (error) {
      console.error('Error fetching documents:', error);
      setDocuments([]);
    } finally {
      setDocumentsLoading(false);
    }
  };

  useEffect(() => {
    // Use external documents if provided, otherwise fetch (filtered by selectedStudy)
    if (externalDocuments) {
      setDocuments(externalDocuments);
      setDocumentsLoading(false);
    } else {
    fetchDocuments();
    }
  }, [externalDocuments, selectedStudy]);

  // Refresh documents when refreshTrigger changes
  useEffect(() => {
    if (refreshTrigger > 0 && !externalDocuments) {
      fetchDocuments();
    }
  }, [refreshTrigger, externalDocuments]);

  const handleRefreshDocuments = async () => {
    await refetchHierarchy();
    if (externalDocuments) {
      await fetchDocuments();
    }
    onRefreshDocuments?.();
  };

  const isRefreshing = documentsLoading || hierarchyLoading;
  const hardcodedZones = useMemo(() => {
    // icon/color defaults by zone number (fallbacks kept for UI)
    const iconColorMap = {
      '01': { icon: Activity, color: 'blue' },
      '02': { icon: FileText, color: 'green' },
      '03': { icon: Shield, color: 'purple' },
      '04': { icon: CheckCircle, color: 'emerald' },
      '05': { icon: Users, color: 'orange' },
      '06': { icon: Package, color: 'cyan' },
      '07': { icon: AlertCircle, color: 'red' },
      '08': { icon: TestTube, color: 'indigo' },
      '09': { icon: Building, color: 'slate' },
      '10': { icon: Database, color: 'teal' },
      '11': { icon: BarChart3, color: 'pink' }
    };
    return (hierarchyData || []).map(z => {
      const zn = z?.Zone?.Number?.toString() || '';
      const nn = z?.Zone?.Name || '';
      const normalized = zn.padStart(2, '0');
      const displayNumber = String(parseInt(normalized, 10));
      const meta = iconColorMap[normalized] || { icon: Folder, color: 'blue' };
      return {
        _id: displayNumber,
        zoneNumber: displayNumber,
        zoneName: nn,
        icon: meta.icon,
        color: meta.color,
      };
    });
  }, [hierarchyData]);

  // Build canonical hierarchy skeleton from hierarchyData
  const hierarchySkeleton = useMemo(() => {
    const skeleton = {};
    (hierarchyData || []).forEach(z => {
      const zn = (z?.Zone?.Number?.toString() || '').padStart(2, '0');
      const disp = String(parseInt(zn, 10));
      const zoneDef = hardcodedZones.find(h => h.zoneNumber === disp) || { _id: disp, zoneNumber: disp, zoneName: z?.Zone?.Name };
      const zoneId = zoneDef._id;
      if (!skeleton[zoneId]) {
        skeleton[zoneId] = { zone: { _id: zoneId, zoneNumber: disp, zoneName: z?.Zone?.Name }, sections: {} };
      }
      z.Sections?.forEach(sec => {
        let secNum = sec?.Section?.Number;
        secNum = normalizeSectionNumber(secNum ?? '');
        if (!secNum) return;
        if (!skeleton[zoneId].sections[secNum]) {
          skeleton[zoneId].sections[secNum] = {
            section: { _id: secNum, sectionNumber: secNum, sectionName: sec?.Section?.Name },
            artifacts: {}
          };
        }
        sec.Artifacts?.forEach(art => {
          const artNum = art?.Artifact?.Number;
          const artName = art?.Artifact?.Name;
          if (!artNum || !artName) return;
          const artifactsMap = skeleton[zoneId].sections[secNum].artifacts;
          if (!artifactsMap[artNum]) {
            artifactsMap[artNum] = {
              artifact: { _id: artNum, artifactNumber: artNum, artifactName: artName },
              subArtifacts: {},
              documents: []
            };
          }
          (art.SubArtifacts || []).forEach((sa, idx) => {
            const saName = sa?.Name;
            if (!saName) return;
            const key = `subart-${saName.replace(/[^a-zA-Z0-9]/g, '_')}-${idx}`;
            artifactsMap[artNum].subArtifacts[key] = {
              subArtifact: { _id: key, subArtifactName: saName },
              documents: []
            };
          });
        });
      });
    });
    return skeleton;
  }, [hierarchyData, hardcodedZones]);

  // Attach documents to the canonical skeleton by matching numbers/names
  const hierarchyWithDocs = useMemo(() => {
    // Optionally enforce client-side study filter as a safety net
    const docsForHierarchy = selectedStudy
      ? (documents || []).filter(doc => {
          const docStudy = typeof doc.study === 'object' && doc.study !== null
            ? (doc.study._id || doc.study.id || doc.study.studyId)
            : doc.study;
          return docStudy && String(docStudy) === String(selectedStudy);
        })
      : (documents || []);

    // Deep-ish clone skeleton for immutability
    const clone = JSON.parse(JSON.stringify(hierarchySkeleton));
    let attachedCount = 0;
    let skippedCount = 0;
    const skippedReasons = { noZone: 0, noSection: 0, noArtifact: 0 };
    const skippedDocs = [];
    
    (docsForHierarchy || []).forEach((doc, idx) => {
      // Extract ISF reference and derive fallback zone/section/artifact numbers (e.g. "11.01.01")
      const tmfRef = doc.tmfReference || '';
      let derivedZoneNumber = '';
      let derivedSectionNumber = '';
      let derivedArtifactNumber = '';
      if (tmfRef) {
        const parts = tmfRef.split('.');
        if (parts.length >= 1) {
          // Zone is the first part (e.g. "11")
          const rawZone = parts[0];
          const parsedZone = parseInt(rawZone, 10);
          if (!Number.isNaN(parsedZone)) {
            derivedZoneNumber = String(parsedZone);
          }
        }
        if (parts.length >= 2) {
          // Section is zone.section (e.g. "11.01")
          const rawZone = parts[0] || '';
          const rawSection = parts[1] || '';
          const normalized = normalizeSectionNumber(`${rawZone}.${rawSection}`);
          derivedSectionNumber = normalized;
        }
        if (parts.length >= 3) {
          // Artifact is zone.section.artifact (e.g. "11.01.01")
          const z = (parts[0] || '').padStart(2, '0');
          const s = (parts[1] || '').padStart(2, '0');
          const a = (parts[2] || '').padStart(2, '0');
          derivedArtifactNumber = `${z}.${s}.${a}`;
        }
      }

      // Extract zone, section, artifact info - handle both populated objects and direct properties
      // Handle populated Mongoose references (zone is an object with zoneNumber) or direct IDs
      let zoneNumber = '';
      if (doc.zone) {
        if (typeof doc.zone === 'object' && doc.zone.zoneNumber !== undefined) {
          // Populated zone object
          zoneNumber = String(Number(doc.zone.zoneNumber));
        } else if (doc.zoneNumber) {
          // Direct zoneNumber property
          zoneNumber = String(Number(doc.zoneNumber));
        } else if (typeof doc.zone === 'string' || (typeof doc.zone === 'object' && doc.zone._id)) {
          // Zone ID reference - we can't use this directly, but will try fallback below
        }
      } else if (doc.zoneNumber) {
        zoneNumber = String(Number(doc.zoneNumber));
      }

      // Fallback: derive zone from tmfReference if not present on the document
      if ((!zoneNumber || zoneNumber === 'NaN' || zoneNumber === '0') && derivedZoneNumber) {
        zoneNumber = derivedZoneNumber;
      }
      
      if (!zoneNumber || zoneNumber === 'NaN' || zoneNumber === '0') {
        skippedCount++;
        skippedReasons.noZone++;
        skippedDocs.push({ 
          doc: doc.title || doc.documentTitle || `Doc ${idx}`, 
          reason: 'No zone number found',
          tmfReference: tmfRef
        });
        return;
      }

      // Extract section number
      let sectionNumber = '';
      if (doc.section) {
        if (typeof doc.section === 'object' && doc.section.sectionNumber !== undefined) {
          // Populated section object
          sectionNumber = normalizeSectionNumber(doc.section.sectionNumber);
        } else if (doc.sectionNumber) {
          // Direct sectionNumber property
          sectionNumber = normalizeSectionNumber(doc.sectionNumber);
        } else {
          // Section ID reference - we can't use this directly, but will try fallback below
                  }
      } else if (doc.sectionNumber) {
        sectionNumber = normalizeSectionNumber(doc.sectionNumber);
      }

      // Fallback: derive section from tmfReference if not present on the document
      if (!sectionNumber && derivedSectionNumber) {
        sectionNumber = derivedSectionNumber;
      }
      
      if (!sectionNumber || sectionNumber === '') {
        skippedCount++;
        skippedReasons.noSection++;
        skippedDocs.push({ 
          doc: doc.title || doc.documentTitle || `Doc ${idx}`, 
          reason: 'No section number found',
          tmfReference: tmfRef
        });
        return;
      }

      // Extract artifact info
      let artifactNumber = doc.artifact?.artifactNumber || doc.artifactNumber || null;
      const artifactName = doc.artifact?.artifactName || doc.artifactName || null;

      // Fallback: derive artifact number from tmfReference if not present
      if (!artifactNumber && derivedArtifactNumber) {
        artifactNumber = derivedArtifactNumber;
      }
      
      if (!artifactNumber && !artifactName) {
        skippedCount++;
        skippedReasons.noArtifact++;
        skippedDocs.push({ 
          doc: doc.title || doc.documentTitle || `Doc ${idx}`, 
          reason: 'No artifact number or name found',
          tmfReference: tmfRef
        });
        return;
      }

      const subArtifactName = doc.subArtifact?.subArtifactName || doc.subArtifactName || null;

      // find zone by display number
      const zoneKey = Object.keys(clone).find(k => String(Number(clone[k]?.zone?.zoneNumber)) === zoneNumber);
      if (!zoneKey) {
        skippedCount++;
        skippedReasons.noZone++;
        skippedDocs.push({ doc: doc.title || doc.documentTitle || `Doc ${idx}`, reason: `Zone ${zoneNumber} not found in hierarchy` });
        return;
      }
      const zoneData = clone[zoneKey];

      // find section by normalized number
      const sectionData = zoneData.sections[sectionNumber];
      if (!sectionData) {
        skippedCount++;
        skippedReasons.noSection++;
        skippedDocs.push({ doc: doc.title || doc.documentTitle || `Doc ${idx}`, reason: `Section ${sectionNumber} not found in zone ${zoneNumber}` });
        return;
      }

      // find artifact by number first, fallback to name match
      // Artifact numbers can be full (11.01.01) or partial (01.01) - need to match both
      let artifactEntry = null;
      
      if (artifactNumber) {
        // Try exact match first
        if (sectionData.artifacts[artifactNumber]) {
        artifactEntry = sectionData.artifacts[artifactNumber];
        } else {
          // Try partial match - if artifactNumber is "01.01", look for "11.01.01" or "01.01.01"
          const artifactKeys = Object.keys(sectionData.artifacts);
          const matchingKey = artifactKeys.find(k => {
            const skeletonArtifactNum = sectionData.artifacts[k]?.artifact?.artifactNumber;
            if (!skeletonArtifactNum) return false;
            
            // Exact match
            if (skeletonArtifactNum === artifactNumber) return true;
            
            // Partial match - check if artifactNumber matches the last part of skeleton number
            // e.g., "01.01" matches "11.01.01" or "01.01.01"
            const skeletonParts = skeletonArtifactNum.split('.');
            const docParts = artifactNumber.split('.');
            
            // If doc has 2 parts and skeleton has 3, check if last 2 parts match
            if (docParts.length === 2 && skeletonParts.length === 3) {
              return skeletonParts[1] === docParts[0] && skeletonParts[2] === docParts[1];
            }
            
            // If both have 3 parts, check if last 2 parts match (zone might differ)
            if (docParts.length === 3 && skeletonParts.length === 3) {
              return skeletonParts[1] === docParts[1] && skeletonParts[2] === docParts[2];
            }
            
            return false;
          });
          
          if (matchingKey) {
            artifactEntry = sectionData.artifacts[matchingKey];
          }
        }
      }
      
      // If still not found, try name match (case-insensitive, partial match)
      if (!artifactEntry && artifactName) {
        const artifactKeys = Object.keys(sectionData.artifacts);
        const matchingKey = artifactKeys.find(k => {
          const skeletonArtifactName = sectionData.artifacts[k]?.artifact?.artifactName;
          if (!skeletonArtifactName) return false;
          
          // Case-insensitive exact match
          if (skeletonArtifactName.toLowerCase().trim() === artifactName.toLowerCase().trim()) {
            return true;
          }
          
          // Partial match - check if artifactName contains skeleton name or vice versa
          const skeletonLower = skeletonArtifactName.toLowerCase().trim();
          const docLower = artifactName.toLowerCase().trim();
          return skeletonLower.includes(docLower) || docLower.includes(skeletonLower);
        });
        
        if (matchingKey) {
          artifactEntry = sectionData.artifacts[matchingKey];
      }
      }
      
      if (!artifactEntry) {
        skippedCount++;
        skippedReasons.noArtifact++;
        skippedDocs.push({ 
          doc: doc.title || doc.documentTitle || `Doc ${idx}`, 
          reason: `Artifact ${artifactNumber || artifactName} not found in section ${sectionNumber}`,
          zone: zoneNumber,
          section: sectionNumber,
          artifact: artifactNumber || artifactName,
          availableArtifacts: Object.keys(sectionData.artifacts).map(k => ({
            key: k,
            number: sectionData.artifacts[k]?.artifact?.artifactNumber,
            name: sectionData.artifacts[k]?.artifact?.artifactName
          }))
        });
        return;
      }

      if (subArtifactName) {
        // find subartifact by name (case-insensitive, tolerant to minor differences)
        const targetName = subArtifactName.toLowerCase().trim();
        const saKey = Object.keys(artifactEntry.subArtifacts).find(k => {
          const skeletonName = artifactEntry.subArtifacts[k]?.subArtifact?.subArtifactName;
          if (!skeletonName) return false;
          const skeletonLower = skeletonName.toLowerCase().trim();
          
          // exact match
          if (skeletonLower === targetName) return true;
          
          // partial match (either direction)
          return skeletonLower.includes(targetName) || targetName.includes(skeletonLower);
        });
        if (saKey) {
          artifactEntry.subArtifacts[saKey].documents = artifactEntry.subArtifacts[saKey].documents || [];
          artifactEntry.subArtifacts[saKey].documents.push(doc);
          attachedCount++;
          return;
        }
      } else {
        // Fallback: if no explicit subArtifactName but exactly ONE sub-artifact exists,
        // attach the document to that sub-artifact instead of "Direct Documents".
        const subKeys = Object.keys(artifactEntry.subArtifacts || {});
        if (subKeys.length === 1) {
          const onlyKey = subKeys[0];
          artifactEntry.subArtifacts[onlyKey].documents = artifactEntry.subArtifacts[onlyKey].documents || [];
          artifactEntry.subArtifacts[onlyKey].documents.push(doc);
          attachedCount++;
          return;
        }
      }

      // Default fallback: attach as direct document on artifact
      artifactEntry.documents = artifactEntry.documents || [];
      artifactEntry.documents.push(doc);
      attachedCount++;
    });
    
    // Debug logging to help identify why documents aren't appearing
    if (docsForHierarchy && docsForHierarchy.length > 0) {
      const sampleDoc = docsForHierarchy[0];
      console.log(`[ISF Hierarchy] Processed ${docsForHierarchy.length} documents: ${attachedCount} attached, ${skippedCount} skipped`);
      console.log(`[ISF Hierarchy] Sample document structure:`, {
        title: sampleDoc?.title || sampleDoc?.documentTitle,
        _id: sampleDoc?._id,
        status: sampleDoc?.status,
        zone: sampleDoc?.zone,
        zoneType: typeof sampleDoc?.zone,
        zoneNumber: sampleDoc?.zoneNumber,
        section: sampleDoc?.section,
        sectionType: typeof sampleDoc?.section,
        sectionNumber: sampleDoc?.sectionNumber,
        artifact: sampleDoc?.artifact,
        artifactType: typeof sampleDoc?.artifact,
        artifactNumber: sampleDoc?.artifactNumber,
        artifactName: sampleDoc?.artifactName,
        subArtifact: sampleDoc?.subArtifact,
        fullDocument: sampleDoc // Full document for debugging
      });
      
      // Log detailed reasons for skipped documents
      if (skippedCount > 0 && skippedDocs.length > 0) {
        console.warn(`[ISF Hierarchy] ⚠️ ${skippedCount} document(s) skipped. Reasons:`);
        skippedDocs.forEach((skipped, idx) => {
          console.warn(`  ${idx + 1}. "${skipped.doc}": ${skipped.reason}`, skipped.zone ? `(Zone: ${skipped.zone}, Section: ${skipped.section}, Artifact: ${skipped.artifact})` : '');
        });
        console.info(`[TMF Hierarchy] 💡 Documents need zone, section, and artifact metadata to appear in hierarchy.`);
        console.info(`[TMF Hierarchy] 💡 Check if documents have TMF references assigned during workflow.`);
        console.info(`[TMF Hierarchy] 📋 Sample document structure:`, docsForHierarchy[0] ? {
          title: docsForHierarchy[0].title || docsForHierarchy[0].documentTitle,
          hasZone: !!docsForHierarchy[0].zone,
          zoneType: typeof docsForHierarchy[0].zone,
          zoneNumber: docsForHierarchy[0].zone?.zoneNumber || docsForHierarchy[0].zoneNumber,
          hasSection: !!docsForHierarchy[0].section,
          sectionType: typeof docsForHierarchy[0].section,
          sectionNumber: docsForHierarchy[0].section?.sectionNumber || docsForHierarchy[0].sectionNumber,
          hasArtifact: !!docsForHierarchy[0].artifact,
          artifactType: typeof docsForHierarchy[0].artifact,
          artifactNumber: docsForHierarchy[0].artifact?.artifactNumber || docsForHierarchy[0].artifactNumber,
          artifactName: docsForHierarchy[0].artifact?.artifactName || docsForHierarchy[0].artifactName,
        } : 'No documents');
      }
    }
    
    // Filter out zones/sections/artifacts/subartifacts that have no documents
    const filtered = {};
    Object.keys(clone).forEach(zoneKey => {
      const zoneData = clone[zoneKey];
      const filteredSections = {};
      
      Object.keys(zoneData.sections || {}).forEach(sectionKey => {
        const sectionData = zoneData.sections[sectionKey];
        const filteredArtifacts = {};
        
        Object.keys(sectionData.artifacts || {}).forEach(artifactKey => {
          const artifactData = sectionData.artifacts[artifactKey];
          const filteredSubArtifacts = {};
          
          // Filter subartifacts to keep only those with documents
          Object.keys(artifactData.subArtifacts || {}).forEach(subArtKey => {
            const subArtData = artifactData.subArtifacts[subArtKey];
            if ((subArtData.documents || []).length > 0) {
              filteredSubArtifacts[subArtKey] = subArtData;
            }
          });
          
          // Keep artifact if it has direct documents OR has subartifacts with documents
          if ((artifactData.documents || []).length > 0 || Object.keys(filteredSubArtifacts).length > 0) {
            filteredArtifacts[artifactKey] = {
              ...artifactData,
              subArtifacts: filteredSubArtifacts
            };
          }
        });
        
        // Keep section if it has artifacts with documents
        if (Object.keys(filteredArtifacts).length > 0) {
          filteredSections[sectionKey] = {
            ...sectionData,
            artifacts: filteredArtifacts
          };
        }
      });
      
      // Keep zone if it has sections with documents
      if (Object.keys(filteredSections).length > 0) {
        filtered[zoneKey] = {
          ...zoneData,
          sections: filteredSections
        };
      }
    });
    
    return filtered;
  }, [documents, hierarchySkeleton, selectedStudy]);

  // Helper function for document lookup
  const FIND_DOCUMENTS = (zoneData, parentSection, parentArtifact) => {
    if (!zoneData?.sections) {
      return null;
    }
    
    // Try to find section by multiple methods
    let sectionData = zoneData.sections[parentSection._id];
    let sectionKey = parentSection._id;
    
    if (!sectionData) {
      // Try by section name
      const nameMatch = Object.entries(zoneData.sections).find(([, data]) => 
        data.section?.sectionName === parentSection.sectionName
      );
      if (nameMatch) {
        sectionKey = nameMatch[0];
        sectionData = nameMatch[1];
      }
    }
    
    if (!sectionData) {
      return null;
    }
    
    // Try to find artifact by multiple methods
    let artifactData = sectionData.artifacts[parentArtifact._id];
    let artifactKey = parentArtifact._id;
    
    if (!artifactData) {
      // Try by artifact name
      const nameMatch = Object.entries(sectionData.artifacts).find(([, data]) => 
        data.artifact?.artifactName === parentArtifact.artifactName
      );
      if (nameMatch) {
        artifactKey = nameMatch[0];
        artifactData = nameMatch[1];
      }
    }
    
    if (!artifactData) {
      // Try by section ID (since artifacts might be keyed by section ID)
      artifactData = sectionData.artifacts[parentSection._id];
      artifactKey = parentSection._id;
    }
    
    if (!artifactData) {
      return null;
    }
    
    return { sectionData, artifactData, sectionKey, artifactKey };
  };


  const toggleExpand = async (id) => {
      setExpanded(prev => ({
        ...prev,
        [id]: !prev[id]
      }));
  };

  const handleItemSelect = async (type, item) => {
    setSelectedItem({ type, item });
    onSelect({ type, item });
  };

  // Get status icon and color
  const getStatusIcon = (status) => {
    switch (status?.toLowerCase()) {
      case 'approved':
        return { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50' };
      case 'pending':
        return { icon: Clock, color: 'text-yellow-600', bg: 'bg-yellow-50' };
      case 'rejected':
        return { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50' };
      case 'draft':
        return { icon: FileText, color: 'text-gray-600', bg: 'bg-gray-50' };
      default:
        return { icon: FileText, color: 'text-gray-600', bg: 'bg-gray-50' };
    }
  };

  // Get zone color classes
  const getZoneColor = (color) => {
    const colorMap = {
      blue: 'text-indigo-600 bg-indigo-50 border-indigo-100',
      green: 'text-emerald-600 bg-emerald-50 border-emerald-100',
      purple: 'text-violet-600 bg-violet-50 border-violet-100',
      emerald: 'text-teal-600 bg-teal-50 border-teal-100',
      orange: 'text-amber-600 bg-amber-50 border-amber-100',
      cyan: 'text-cyan-600 bg-cyan-50 border-cyan-100',
      red: 'text-rose-600 bg-rose-50 border-rose-100',
      indigo: 'text-indigo-600 bg-indigo-50 border-indigo-100',
      slate: 'text-slate-600 bg-slate-50 border-slate-100',
      teal: 'text-teal-600 bg-teal-50 border-teal-100',
      pink: 'text-fuchsia-600 bg-fuchsia-50 border-fuchsia-100'
    };
    return colorMap[color] || 'text-slate-600 bg-slate-50 border-slate-100';
  };

  // Helper component to render virtualized document list
  const VirtualizedDocumentList = ({ documents, parentZone, parentSection, parentArtifact, subArtifact }) => {
    const parentRef = useRef(null);
    
    // Only virtualize if we have more than 20 documents (lower threshold for better performance)
    const shouldVirtualize = documents.length > 20;
    
    const rowVirtualizer = useVirtualizer({
      count: documents.length,
      getScrollElement: () => parentRef.current,
      estimateSize: () => 32, // Estimated height per document row
      overscan: 10,
      enabled: shouldVirtualize
    });

    const virtualItems = useMemo(() => {
      return rowVirtualizer.getVirtualItems();
    }, [rowVirtualizer]);

    if (!shouldVirtualize) {
      // Render normally for small lists
      return (
        <div className="space-y-1">
          {documents.map(doc => (
            <div 
              key={doc._id}
              className={cn(
                "group flex items-center px-2 py-1.5 hover:bg-gray-50/80 rounded-sm cursor-pointer transition-all duration-200",
                "border border-transparent hover:border-gray-200",
                selectedItem?.type === 'document' && selectedItem?.item._id === doc._id 
                  ? "bg-gray-50/80 border-gray-200 shadow-sm" 
                  : ""
              )}
              onClick={() => handleItemSelect('document', doc)}
            >
              <div className="h-3 w-3 rounded-sm bg-gray-100 flex items-center justify-center mr-1.5 flex-shrink-0">
                <File className="h-1.5 w-1.5 text-gray-500" />
              </div>
              
              <div className="flex flex-col flex-1 min-w-0 mr-1.5">
                <span className="text-[11px] font-medium text-gray-700 leading-tight truncate">
                  {doc.title || doc.documentTitle || 'Untitled Document'}
                </span>
                <span className="text-[9px] text-gray-500">
                  {parentZone.zoneNumber}.{parentSection.sectionNumber} • {subArtifact || parentArtifact?.artifactName || 'Unknown'}
                </span>
              </div>
              
              <div className="flex items-center flex-shrink-0 space-x-1">
                {(() => {
                  const statusInfo = getStatusIcon(doc.status);
                  const StatusIcon = statusInfo.icon;
                  return (
                    <div className={cn("h-4 w-4 rounded-sm flex items-center justify-center", statusInfo.bg)}>
                      <StatusIcon className={cn("h-2 w-2", statusInfo.color)} />
                    </div>
                  );
                })()}
                
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-4 w-4 opacity-0 group-hover:opacity-100 transition-opacity">
                      <MoreHorizontal size={8} />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-32">
                    <DropdownMenuItem><Eye className="h-3 w-3 mr-2" />View</DropdownMenuItem>
                    <DropdownMenuItem><Download className="h-3 w-3 mr-2" />Download</DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem><Edit className="h-3 w-3 mr-2" />Edit</DropdownMenuItem>
                    <DropdownMenuItem className="text-red-600"><Trash2 className="h-3 w-3 mr-2" />Delete</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          ))}
        </div>
      );
    }

    // Virtualized rendering for large lists
    return (
      <div ref={parentRef} className="max-h-[300px] overflow-auto">
        <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, width: '100%', position: 'relative' }}>
          {virtualItems.map((virtualItem) => {
            const doc = documents[virtualItem.index];
            return (
              <div
                key={virtualItem.key}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualItem.size}px`,
                  transform: `translateY(${virtualItem.start}px)`,
                }}
              >
                <div 
                  className={cn(
                    "group flex items-center px-2 py-1.5 hover:bg-gray-50/80 rounded-sm cursor-pointer transition-all duration-200",
                    "border border-transparent hover:border-gray-200 h-full",
                    selectedItem?.type === 'document' && selectedItem?.item._id === doc._id 
                      ? "bg-gray-50/80 border-gray-200 shadow-sm" 
                      : ""
                  )}
                  onClick={() => handleItemSelect('document', doc)}
                >
                  <div className="h-3 w-3 rounded-sm bg-gray-100 flex items-center justify-center mr-1.5 flex-shrink-0">
                    <File className="h-1.5 w-1.5 text-gray-500" />
                  </div>
                  
                  <div className="flex flex-col flex-1 min-w-0 mr-1.5">
                    <span className="text-[11px] font-medium text-gray-700 leading-tight truncate">
                      {doc.title || doc.documentTitle || 'Untitled Document'}
                    </span>
                    <span className="text-[9px] text-gray-500">
                      {parentZone.zoneNumber}.{parentSection.sectionNumber} • {subArtifact || parentArtifact?.artifactName || 'Unknown'}
                    </span>
                  </div>
                  
                  <div className="flex items-center flex-shrink-0 space-x-1">
                    {(() => {
                      const statusInfo = getStatusIcon(doc.status);
                      const StatusIcon = statusInfo.icon;
                      return (
                        <div className={cn("h-4 w-4 rounded-sm flex items-center justify-center", statusInfo.bg)}>
                          <StatusIcon className={cn("h-2 w-2", statusInfo.color)} />
                        </div>
                      );
                    })()}
                    
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-4 w-4 opacity-0 group-hover:opacity-100 transition-opacity">
                          <MoreHorizontal size={8} />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-32">
                        <DropdownMenuItem><Eye className="h-3 w-3 mr-2" />View</DropdownMenuItem>
                        <DropdownMenuItem><Download className="h-3 w-3 mr-2" />Download</DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem><Edit className="h-3 w-3 mr-2" />Edit</DropdownMenuItem>
                        <DropdownMenuItem className="text-red-600"><Trash2 className="h-3 w-3 mr-2" />Delete</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderZones = () => {
    if (documentsLoading) {
      return (
        <div className="flex items-center justify-center p-8">
          <div className="flex flex-col items-center space-y-3">
            <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            <span className="text-sm text-gray-500 font-medium">Loading documents...</span>
          </div>
        </div>
      );
    }
    
    const hierarchy = hierarchyWithDocs;
    
    return hardcodedZones.map(zone => {
      const zoneData = hierarchy[zone._id];
      const hasDocuments = zoneData && Object.keys(zoneData.sections).length > 0;
      const documentCount = zoneData ? Object.values(zoneData.sections || {}).reduce((total, section) => 
        total + Object.values(section.artifacts || {}).reduce((sectionTotal, artifact) => 
          sectionTotal + (artifact.documents?.length || 0) + 
          Object.values(artifact.subArtifacts || {}).reduce((subTotal, subArtifact) => 
            subTotal + (subArtifact?.documents?.length || 0), 0
          ), 0
        ), 0
      ) : 0;
      
      const ZoneIcon = zone.icon || Folder;
      const zoneColor = getZoneColor(zone.color);
      
      return (
      <div key={zone._id} className="mb-1.5">
        <div 
          className={cn(
            "group flex items-center px-2.5 py-1.5 hover:bg-gray-50/80 rounded-lg cursor-pointer transition-all duration-200",
            "border border-transparent hover:border-gray-200",
            selectedItem?.type === 'zone' && selectedItem?.item._id === zone._id 
                ? "bg-blue-50/80 border-blue-200 shadow-sm" 
                : ""
          )}
          onClick={() => {
            toggleExpand(zone._id, 'zone');
            handleItemSelect('zone', zone);
          }}
        >
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-4 w-4 mr-2 flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
          >
            {expanded[zone._id] ? (
              <ChevronDown size={12} />
            ) : (
              <ChevronRight size={12} />
            )}
          </Button>
          
          <div className={cn(
            "h-6 w-6 rounded-md flex items-center justify-center mr-2 flex-shrink-0",
            zoneColor
          )}>
            <ZoneIcon className="h-3 w-3" />
          </div>
          
          <div className="flex flex-col flex-1 min-w-0 mr-2">
            <span className="text-[12px] font-semibold text-gray-800 leading-tight">
              {zone.zoneNumber}. {zone.zoneName}
            </span>
            <span className="text-[10px] text-gray-500 mt-0.5">
              {documentCount} {documentCount === 1 ? 'file' : 'files'}
            </span>
          </div>
            
          {documentCount > 0 && (
            <Badge variant="secondary" className="flex-shrink-0 bg-blue-100 text-blue-700 hover:bg-blue-200 text-[10px] h-4 px-1">
              {documentCount}
            </Badge>
          )}
        </div>
        
        {expanded[zone._id] && (
            <div className="ml-4 pl-2 border-l border-gray-100 mt-1 space-y-1">
              {renderSections(zoneData?.sections || {}, zone)}
          </div>
        )}
      </div>
      );
    });
  };
  
  const renderSections = (sections, parentZone) => {
    const normalizedZone = (parentZone.zoneNumber?.toString() || '').padStart(2, '0');
    const zoneDef = hierarchyData?.find(z =>
      String(parseInt(z?.Zone?.Number || 0, 10)) === String(parseInt(parentZone.zoneNumber, 10))
    );
    const hardcodedSections = (zoneDef?.Sections || []).map((sec) => {
      const sectionNumber = normalizeSectionNumber(sec?.Section?.Number);
      return {
        _id: sectionNumber,
        sectionNumber,
        sectionName: sec?.Section?.Name,
        subartifacts: (sec?.Artifacts || []).map(a => a?.Artifact?.Name).filter(Boolean),
        artifacts: (sec?.Artifacts || []).map(a => ({
          number: a?.Artifact?.Number,
          name: a?.Artifact?.Name,
        })).filter(a => a.number && a.name),
        isHardcoded: true,
      };
    });
    
    // Get sections from actual documents (filter out unknown sections)
    const documentSections = Object.entries(sections || {})
      .filter(([sectionId]) => {
        // Filter out unknown sections
        if (sectionId.startsWith('unknown-') || sectionId === 'unknown-section') return false;
        const sectionData = sections[sectionId];
        const secNum = normalizeSectionNumber(sectionData?.section?.sectionNumber ?? sectionId);
        // Keep only sections that belong to this zone
        return secNum.startsWith(normalizedZone + '.');
      })
      .map(([sectionId, sectionData]) => ({
        _id: normalizeSectionNumber(sectionData.section?.sectionNumber ?? sectionId),
        sectionNumber: normalizeSectionNumber(sectionData.section?.sectionNumber ?? sectionId),
        sectionName: sectionData.section?.sectionName || 'Unknown Section',
        subartifacts: [],
        artifacts: [],
        isHardcoded: false,
        sectionData: sectionData
      }))
      .filter(section => {
        // Also filter out sections with "Unknown Section" name
        return section.sectionName !== 'Unknown Section';
      });
    
    // Start from authoritative (hierarchy) sections only
    const allSections = [...hardcodedSections];
    
    // Merge document-provided section data into existing hierarchy sections (by section number)
    documentSections.forEach(docSection => {
      const existingSection = allSections.find(s => s.sectionNumber === docSection.sectionNumber);
      if (existingSection) {
        existingSection.sectionData = docSection.sectionData;
      }
    });
    
    // Do not add new sections from documents; only enrich existing hierarchy entries
    
    if (!allSections.length) {
      return (
        <div className="p-4 text-center">
          <FolderOpen className="h-8 w-8 text-gray-300 mx-auto mb-2" />
          <p className="text-sm text-gray-500 font-medium">No sections found</p>
          <p className="text-xs text-gray-400 mt-1">This zone doesn't have any sections yet</p>
        </div>
      );
    }
    
    return allSections.map((section, index) => {
      // Check if this section has documents in the hierarchy
      let sectionData = section.sectionData || sections?.[section._id];
      
      // If we don't have sectionData, try to find it by section name
      if (!sectionData) {
        const matchingSectionKey = Object.keys(sections || {}).find(key => {
          const data = sections[key];
          return data?.section?.sectionName === section.sectionName;
        });
        if (matchingSectionKey) {
          sectionData = sections[matchingSectionKey];
        }
      }
      
      // Safe document checking with defensive programming
      const hasDocuments = sectionData && (() => {
        try {
          const artifacts = sectionData.artifacts || {};
          return Object.keys(artifacts).some(artifactKey => {
            const artifact = artifacts[artifactKey];
            if (!artifact) return false;
            
            // Check direct documents
            if (artifact.documents?.length > 0) return true;
            
            // Check subartifacts
            const subArtifacts = artifact.subArtifacts || {};
            return Object.values(subArtifacts).some(subArtifact => 
              subArtifact?.documents?.length > 0
            );
          });
        } catch (error) {
          return false;
        }
      })();
      
      const documentCount = sectionData ? Object.values(sectionData.artifacts || {}).reduce((total, artifact) => 
        total + (artifact.documents?.length || 0) + 
        Object.values(artifact.subArtifacts || {}).reduce((subTotal, subArtifact) => 
          subTotal + (subArtifact?.documents?.length || 0), 0
        ), 0
      ) : 0;
      
      // Create unique key combining zone number and section
      const uniqueKey = `${parentZone.zoneNumber}-${section._id}-${index}`;
      
      return (
      <div key={uniqueKey} className="mb-1">
        <div 
          className={cn(
            "group flex items-center px-2 py-1.5 hover:bg-gray-50/80 rounded-md cursor-pointer transition-all duration-200",
            "border border-transparent hover:border-gray-200",
            selectedItem?.type === 'section' && selectedItem?.item._id === section._id 
                ? "bg-green-50/80 border-green-200 shadow-sm" 
                : ""
          )}
          onClick={() => {
            toggleExpand(uniqueKey, 'section');
            handleItemSelect('section', {
              ...section,
              zone: parentZone
            });
          }}
        >
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-3.5 w-3.5 mr-1.5 flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
          >
            {expanded[uniqueKey] ? (
              <ChevronDown size={11} />
            ) : (
              <ChevronRight size={11} />
            )}
          </Button>
          
          <div className="h-5 w-5 rounded-md bg-green-100 flex items-center justify-center mr-1.5 flex-shrink-0">
            <Folder className="h-2.5 w-2.5 text-green-600" />
          </div>
          
          <div className="flex flex-col flex-1 min-w-0 mr-1.5">
            <span className="text-[11px] font-medium text-gray-700 leading-tight">
              {section.sectionNumber} {section.sectionName}
            </span>
            <span className="text-[10px] text-gray-500">
              {parentZone.zoneNumber}
            </span>
          </div>
            
          {hasDocuments && (
            <Badge variant="secondary" className="flex-shrink-0 bg-green-100 text-green-700 hover:bg-green-200 text-[10px] h-3.5 px-1">
              {documentCount}
            </Badge>
          )}
        </div>
          
        {expanded[uniqueKey] && (
          <div className="ml-3 pl-2 border-l border-gray-100 mt-0.5 space-y-0.5">
            {renderArtifacts(sectionData?.artifacts || {}, section, parentZone)}
          </div>
        )}
      </div>
      );
    });
  };

  const renderArtifacts = (artifacts, parentSection, parentZone) => {
    // 1. Identify the hardcoded section data for the current zone/section
    const hardcodedSectionKey = normalizeSectionNumber(
      parentSection.sectionNumber || parentSection._id
    );

    // Find the master definition in your hierarchyData to get the isfStatus
    const zoneDef = hierarchyData?.find(z => 
      String(parseInt(z?.Zone?.Number || 0, 10)) === String(parseInt(parentZone.zoneNumber, 10))
    );
    const sectionDef = zoneDef?.Sections?.find(s => 
      normalizeSectionNumber(s?.Section?.Number) === hardcodedSectionKey
    );

    // 2. Build the Hardcoded Artifacts Map with "isfStatus" awareness
    const hardcodedArtifactsMap = (sectionDef?.Artifacts || []).map((artEntry, idx) => {
      const art = artEntry.Artifact;
      const artifactKey = art.Number || `${hardcodedSectionKey}.${(idx + 1).toString().padStart(2, '0')}`;
      
      return {
        artifactKey,
        artifact: {
          _id: artifactKey,
          artifactName: art.Name,
          artifactNumber: art.Number,
          isfStatus: art.isfStatus, // CRITICAL: This must be captured here
        },
        artifactData: {
          subArtifacts: (artEntry.SubArtifacts || []).reduce((acc, sa, sIdx) => {
            const key = `subart-${sa.Name.replace(/[^a-zA-Z0-9]/g, "_")}-${sIdx}`;
            acc[key] = { subArtifact: { subArtifactName: sa.Name, _id: key }, documents: [] };
            return acc;
          }, {}),
          documents: [],
        },
        isHardcoded: true,
      };
    });

    // 3. Process Live Document Artifacts
    const documentArtifacts = Object.entries(artifacts || {})
      .filter(([key]) => !key.startsWith("unknown-") && key !== "unknown-artifact")
      .map(([key, data]) => ({
        artifactKey: key,
        artifact: data?.artifact || { _id: key, artifactName: key, artifactNumber: key },
        artifactData: data,
        isHardcoded: false,
      }));

    // 4. Merge Logic: Combine Hardcoded definitions with Live Document data
    const mergedList = [...hardcodedArtifactsMap];

    documentArtifacts.forEach((docArt) => {
      const existing = mergedList.find(a => 
        a.artifact.artifactNumber === docArt.artifact.artifactNumber || 
        a.artifact.artifactName.toLowerCase().trim() === docArt.artifact.artifactName.toLowerCase().trim()
      );

      if (!existing) {
        mergedList.push(docArt);
      } else {
        // Enrich the hardcoded definition with the live documents
        existing.artifactData = {
          ...existing.artifactData,
          ...docArt.artifactData,
          documents: docArt.artifactData.documents || [],
          // Merge subartifacts to ensure documents inside them are preserved
          subArtifacts: {
            ...existing.artifactData.subArtifacts,
            ...docArt.artifactData.subArtifacts
          }
        };
      }
    });

    // 5. FINAL FILTER: Remove anything with "Hidden" status
    // This is where "Trial Master File Plan" gets removed
    const visibleArtifacts = mergedList.filter(item => 
      item.artifact?.isfStatus !== "Hidden"
    );

    // 6. Final Render
    return visibleArtifacts.map((item) => {
      const { artifactKey, artifact, artifactData } = item;
      const nodeId = `${parentSection._id}-${artifactKey}`;

      const subArtifactsEntries = Object.entries(artifactData?.subArtifacts || {});
      const docsInSubs = subArtifactsEntries.reduce(
        (t, [, s]) => t + (s?.documents?.length || 0), 0
      );

      const documentCount = (artifactData?.documents?.length || 0) + docsInSubs;
      const hasDocuments = documentCount > 0;
      const isSelected = selectedItem?.type === "artifact" && selectedItem?.item._id === nodeId;

      return (
        <div key={nodeId} className="mb-1">
          <div
            className={cn(
              "group flex items-center px-2 py-1 hover:bg-gray-50/80 rounded-md cursor-pointer transition-all duration-200",
              "border border-transparent hover:border-gray-200",
              isSelected ? "bg-orange-50/80 border-orange-200 shadow-sm" : ""
            )}
            onClick={() => {
              toggleExpand(nodeId, "artifact");
              handleItemSelect("artifact", {
                ...artifact,
                _id: nodeId,
                section: parentSection,
                zone: parentZone,
              });
            }}
          >
            <Button variant="ghost" size="icon" className="h-3 w-3 mr-1.5 flex-shrink-0 text-gray-400 hover:text-gray-600">
              {expanded[nodeId] ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            </Button>

            <div className="h-4 w-4 rounded-sm bg-orange-100 flex items-center justify-center mr-1.5">
              <Folder className="h-2 w-2 text-orange-600" />
            </div>

            <div className="flex flex-col flex-1 min-w-0 mr-1.5">
              <span className="text-[10px] font-medium text-gray-700 leading-tight">
                {artifact.artifactName}
              </span>
              <span className="text-[9px] text-gray-500">
                {getDisplayArtifactNumber(artifact.artifactNumber) || `${parentSection.sectionNumber}.01`}
              </span>
            </div>

            {hasDocuments && (
              <Badge variant="secondary" className="bg-orange-100 text-orange-700 text-[9px] h-3 px-0.5">
                {documentCount}
              </Badge>
            )}
          </div>

          {expanded[nodeId] && (
            <div className="ml-6 pl-3 border-l border-gray-100 mt-1 space-y-1">
              {renderSubArtifacts(artifactData, artifact, parentSection, parentZone)}
              {renderDirectDocuments(artifactData?.documents, artifact, parentSection, parentZone)}
            </div>
          )}
        </div>
      );
    });
  };

  const renderSubArtifacts = (artifactData, parentArtifact, parentSection, parentZone) => {
    const subArtifactsMap = artifactData?.subArtifacts || {};
    const entries = Object.entries(subArtifactsMap);
    
    return entries.map(([subKey, subData], index) => {
      const uniqueKey = `${parentSection._id}-subart-${index}`;
      const documents = subData?.documents || [];
      const subArtifact = subData?.subArtifact?.subArtifactName || subKey;

      return (
        <div key={uniqueKey} className="mb-1">
          <div 
            className={cn(
              "group flex items-center px-2.5 py-2 hover:bg-gray-50/80 rounded-md cursor-pointer transition-all duration-200",
              "border border-transparent hover:border-gray-200",
              selectedItem?.type === 'subArtifact' && selectedItem?.item._id === uniqueKey
                ? "bg-purple-50/80 border-purple-200 shadow-sm" 
                : ""
            )}
            onClick={() => {
              toggleExpand(uniqueKey, 'subArtifact');
              handleItemSelect('subArtifact', {
                _id: uniqueKey,
                subArtifactName: subArtifact,
                artifact: parentArtifact,
                section: parentSection,
                zone: parentZone
              });
            }}
          >
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-4 w-4 mr-1.5 flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
            >
              {expanded[uniqueKey] ? (
                <ChevronDown size={10} />
              ) : (
                <ChevronRight size={10} />
              )}
            </Button>
            
            <div className="h-4 w-4 rounded-sm bg-purple-100 flex items-center justify-center mr-1.5 flex-shrink-0">
              <Folder className="h-2 w-2 text-purple-600" />
            </div>
            
            <div className="flex flex-col flex-1 min-w-0 mr-1.5">
              <span className="text-[12px] font-medium text-gray-700 leading-tight">
                {subArtifact}
              </span>
              <span className="text-[10px] text-gray-500">
                {parentArtifact.artifactName}
              </span>
            </div>
            
            <div className="flex items-center flex-shrink-0 space-x-1">
              {documents.length > 0 && (
                <Badge variant="secondary" className="bg-purple-100 text-purple-700 hover:bg-purple-200 text-[10px] px-1.5 py-0.5">
                  {documents.length}
                </Badge>
              )}
              
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="h-5 w-5 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-purple-50 hover:text-purple-600"
                      onClick={(e) => {
                        e.stopPropagation();
                        onCreate('document', {
                          type: 'document',
                          data: {
                            zoneNumber: parentZone.zoneNumber,
                            zoneName: parentZone.zoneName,
                            sectionNumber: parentSection.sectionNumber.split('.').slice(0, 2).join('.'),
                            sectionName: parentSection.sectionName,
                            artifactNumber: parentArtifact.artifactNumber,
                            artifactName: parentArtifact.artifactName,
                            subArtifactName: subArtifact,
                          }
                        });
                      }}
                    >
                      <Plus size={10} />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Add document to this sub-artifact</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>
          
          {expanded[uniqueKey] && (
            <div className="ml-6 border-l border-gray-100 mt-1">
              {documents.length > 0 ? (
                <VirtualizedDocumentList
                  documents={documents}
                  parentZone={parentZone}
                  parentSection={parentSection}
                  parentArtifact={parentArtifact}
                  subArtifact={subArtifact}
                />
              ) : (
                <div className="p-2 text-center">
                  <FileText className="h-4 w-4 text-gray-300 mx-auto mb-1" />
                  <p className="text-[10px] text-gray-500">No documents</p>
                </div>
              )}
            </div>
          )}
        </div>
      );
    });
  };

  const renderDirectDocuments = (documents, parentArtifact, parentSection, parentZone) => {
    if (!documents || documents.length === 0) {
      return null;
    }
    
    return (
      <div key="direct-documents" className="mb-2">
        <div className="px-2 py-1.5 bg-gray-50/80 rounded-md mb-1">
          <div className="flex items-center">
            <FileText className="h-3 w-3 text-gray-500 mr-1.5" />
            <span className="text-[11px] font-medium text-gray-700">Direct Documents</span>
            <Badge variant="secondary" className="ml-auto bg-gray-200 text-gray-600 text-[9px] px-1.5 py-0.5">
              {documents.length}
            </Badge>
          </div>
        </div>
        <VirtualizedDocumentList
          documents={documents}
          parentZone={parentZone}
          parentSection={parentSection}
          parentArtifact={parentArtifact}
        />
      </div>
    );
  };

  return (
    <div className={cn(
      "relative h-full w-full bg-background flex-shrink-0 overflow-hidden transition-all duration-200",
      isSidebarCollapsed ? "w-14" : ""
    )} style={!isSidebarCollapsed ? { width: `${sidebarWidth}px`, minWidth: '320px', maxWidth: '900px' } : {}}>
      {/* Resize handle - only show when not collapsed */}
      {!isSidebarCollapsed && (
        <div
          className="absolute top-0 right-0 w-1 h-full hover:bg-blue-500 cursor-col-resize transition-colors duration-200 z-10"
          onMouseDown={handleMouseDown}
          style={{ 
            cursor: isDragging ? 'col-resize' : 'col-resize',
            backgroundColor: isDragging ? '#3b82f6' : '#e5e7eb',
          }}
        />
      )}
      
      <div className="h-full w-full flex flex-col border-r bg-card shadow-sm overflow-hidden">
        {/* Professional Header - Ultra Compact */}
        <div className="flex-none border-b bg-gradient-to-br from-slate-50 via-white to-slate-50">
          {isSidebarCollapsed ? (
            // Collapsed Header - Just toggle button
            <div className="flex items-center justify-center p-2">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 hover:bg-muted"
                      onClick={() => setIsSidebarCollapsed(false)}
                    >
                      <PanelLeftOpen className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="right">
                    <p className="text-xs">Expand sidebar</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          ) : (
            <>
              <div className="px-2.5 pt-2 pb-1.5">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5 flex-1 min-w-0">
                    <div className="h-6 w-6 rounded-md bg-slate-700 flex items-center justify-center flex-shrink-0">
                      <Database className="h-3 w-3 text-white" />
                    </div>
                    <div className="flex items-center gap-1.5 flex-1 min-w-0">
                      <h2 className="text-xs font-semibold text-foreground truncate">ISF Zones</h2>
                      {!documentsLoading && (
                        <>
                          <div className={cn(
                            "h-1 w-1 rounded-full flex-shrink-0",
                            "bg-emerald-500"
                          )}></div>
                          <span className="text-[9px] text-muted-foreground font-medium whitespace-nowrap">
                            {(() => {
                              // Count documents actually attached to hierarchy
                              let totalAttached = 0;
                              Object.values(hierarchyWithDocs || {}).forEach(zoneData => {
                                Object.values(zoneData.sections || {}).forEach(sectionData => {
                                  Object.values(sectionData.artifacts || {}).forEach(artifactData => {
                                    totalAttached += (artifactData.documents?.length || 0);
                                    Object.values(artifactData.subArtifacts || {}).forEach(subArtifactData => {
                                      totalAttached += (subArtifactData.documents?.length || 0);
                                    });
                                  });
                                });
                              });
                              return `${totalAttached} docs`;
                            })()}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-0.5">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-5 w-5 hover:bg-muted"
                            onClick={() => setIsSidebarCollapsed(true)}
                          >
                            <PanelLeftClose className="h-3.5 w-3.5" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                          <p className="text-xs">Collapse sidebar</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-5 w-5 hover:bg-muted"
                            onClick={() => setShowSearch(!showSearch)}
                          >
                            <Search className="h-3 w-3" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                          <p className="text-xs">Search</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>

                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-5 w-5 hover:bg-muted"
                            onClick={handleRefreshDocuments}
                            disabled={isRefreshing}
                          >
                            <RefreshCw className={cn("h-3 w-3", isRefreshing && "animate-spin")} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                          <p className="text-xs">Refresh documents</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    
                    <Separator orientation="vertical" className="h-4 mx-0.5" />
                    
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-5 w-5 hover:bg-muted"
                            onClick={() => setExpanded({})}
                          >
                            <ChevronsUpDown className="h-3 w-3" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                          <p className="text-xs">Collapse all</p>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                </div>
                
                {/* Search Bar */}
                {showSearch && (
                  <div className="mb-1.5 animate-in slide-in-from-top-2">
                    <div className="relative">
                      <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground" />
                      <Input
                        placeholder="Search documents..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="pl-7 pr-7 h-7 text-[10px] bg-background border-muted focus:border-primary"
                      />
                      {searchQuery && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="absolute right-0.5 top-1/2 transform -translate-y-1/2 h-6 w-6"
                          onClick={() => setSearchQuery('')}
                        >
                          <X className="h-2.5 w-2.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </div>
              
              {/* Current Selection Indicator - Ultra Compact */}
              {selectedItem && (
                <div className="px-2.5 pb-1 animate-in slide-in-from-top-2">
                  <div className="p-1 bg-slate-100 border border-slate-200 rounded-md">
                    <p className="text-[10px] text-slate-700 font-medium truncate leading-tight">
                      {selectedItem.type === 'zone' && `${selectedItem.item.zoneNumber}. ${selectedItem.item.zoneName}`}
                      {selectedItem.type === 'section' && `${selectedItem.item.zone.zoneNumber}.${selectedItem.item.sectionNumber} ${selectedItem.item.sectionName}`}
                      {selectedItem.type === 'artifact' && `${selectedItem.item.zone.zoneNumber}.${selectedItem.item.section.sectionNumber} • ${selectedItem.item.artifactName}`}
                      {selectedItem.type === 'subArtifact' && `${selectedItem.item.zone.zoneNumber}.${selectedItem.item.section.sectionNumber} • ${selectedItem.item.subArtifactName}`}
                      {selectedItem.type === 'document' && `${selectedItem.item.title || selectedItem.item.documentTitle || 'Document'}`}
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Content Area - Compact */}
        {!isSidebarCollapsed && (
          <div className="flex-1 min-h-0 overflow-y-auto sidebar-scroll">
            <div className="p-2">
              {documentsLoading || hierarchyLoading ? (
                <div className="flex items-center justify-center p-8">
                  <div className="flex flex-col items-center space-y-3">
                    <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
                    <span className="text-sm text-gray-500 font-medium">
                      {hierarchyLoading ? 'Loading TMF hierarchy...' : 'Loading documents...'}
                    </span>
                  </div>
                </div>
              ) : (
                <>
                  {renderZones()}
                </>
              )}
            </div>
          </div>
        )}

        {/* Professional Breadcrumb */}
        {!isSidebarCollapsed && (
          <div className="flex-none">
            {selectedItem && (() => {
              let breadcrumb = [];
              const { type, item } = selectedItem;
              
              switch (type) {
                case 'zone':
                  breadcrumb = [`Zone ${item.zoneNumber}: ${item.zoneName}`];
                  break;
                case 'section':
                  breadcrumb = [
                    `Zone ${item.zone.zoneNumber}: ${item.zone.zoneName}`,
                    `${item.sectionNumber}: ${item.sectionName}`
                  ];
                  break;
                case 'artifact':
                  breadcrumb = [
                    `Zone ${item.zone.zoneNumber}: ${item.zone.zoneName}`,
                    `${item.section.sectionNumber}: ${item.section.sectionName}`,
                    item.artifactName
                  ];
                  break;
                case 'subArtifact':
                  breadcrumb = [
                    `Zone ${item.zone.zoneNumber}: ${item.zone.zoneName}`,
                    `${item.section.sectionNumber}: ${item.section.sectionName}`,
                    item.artifactName,
                    item.subArtifactName
                  ];
                  break;
                case 'document':
                  breadcrumb = [
                    `Zone ${item.zone?.zoneNumber || 'N/A'}: ${item.zone?.zoneName || 'N/A'}`,
                    `${item.section?.sectionNumber || 'N/A'}: ${item.section?.sectionName || 'N/A'}`,
                    item.artifact?.artifactName || 'N/A',
                    item.subArtifact?.subArtifactName || 'N/A',
                    item.title || item.documentTitle || 'Document'
                  ];
                  break;
                default:
                  break;
              }
              
              return (
                <div className="px-2.5 py-1.5 bg-slate-50 border-t border-slate-200">
                  <div className="flex items-center gap-1 text-[9px] text-slate-600">
                    {breadcrumb.map((crumb, index) => (
                      <React.Fragment key={index}>
                        {index > 0 && <ChevronRight className="h-2.5 w-2.5 text-slate-400" />}
                        <span className={index === breadcrumb.length - 1 ? 'font-semibold text-slate-900' : ''}>
                          {crumb}
                        </span>
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        )}
      </div>
    </div>
  );
};

export default SidebarNav;