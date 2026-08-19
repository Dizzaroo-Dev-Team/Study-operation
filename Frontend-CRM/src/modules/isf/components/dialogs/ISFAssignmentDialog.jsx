import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { Loader2, FolderTree } from 'lucide-react';
import tmfService from '../../services/tmf.service';
import documentService from '../../services/document.service';

const ISFAssignmentDialog = ({ open, onOpenChange, document, onSuccess }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [zones, setZones] = useState([]);
  const [sections, setSections] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [subArtifacts, setSubArtifacts] = useState([]);
  
  const [selectedZone, setSelectedZone] = useState(null);
  const [selectedSection, setSelectedSection] = useState(null);
  const [selectedArtifact, setSelectedArtifact] = useState(null);
  const [selectedSubArtifact, setSelectedSubArtifact] = useState(null);

  // Load zones on mount
  useEffect(() => {
    if (open) {
      loadZones();
      // Pre-populate if document already has ISF metadata
      if (document) {
        if (document.zone?._id) {
          setSelectedZone(document.zone._id);
        }
        if (document.section?._id) {
          setSelectedSection(document.section._id);
        }
        if (document.artifact?._id) {
          setSelectedArtifact(document.artifact._id);
        }
        if (document.subArtifact?._id) {
          setSelectedSubArtifact(document.subArtifact._id);
        }
      }
    } else {
      // Reset on close
      setSelectedZone(null);
      setSelectedSection(null);
      setSelectedArtifact(null);
      setSelectedSubArtifact(null);
      setSections([]);
      setArtifacts([]);
      setSubArtifacts([]);
    }
  }, [open, document]);

  const loadZones = async () => {
    try {
      const zonesData = await tmfService.zones.getAll();
      setZones(zonesData);
    } catch (error) {
      console.error('Error loading zones:', error);
      toast({
        title: "Error",
        description: "Failed to load zones",
        variant: "destructive"
      });
    }
  };

  const handleZoneChange = async (zoneId) => {
    setSelectedZone(zoneId);
    setSelectedSection(null);
    setSelectedArtifact(null);
    setSelectedSubArtifact(null);
    setSections([]);
    setArtifacts([]);
    setSubArtifacts([]);

    if (zoneId) {
      try {
        const sectionsData = await tmfService.sections.getAllByZone(zoneId);
        setSections(sectionsData);
      } catch (error) {
        console.error('Error loading sections:', error);
        toast({
          title: "Error",
          description: "Failed to load sections",
          variant: "destructive"
        });
      }
    }
  };

  const handleSectionChange = async (sectionId) => {
    setSelectedSection(sectionId);
    setSelectedArtifact(null);
    setSelectedSubArtifact(null);
    setArtifacts([]);
    setSubArtifacts([]);

    if (sectionId) {
      try {
        const artifactsData = await tmfService.artifacts.getAllBySection(sectionId);
        setArtifacts(artifactsData);
      } catch (error) {
        console.error('Error loading artifacts:', error);
        toast({
          title: "Error",
          description: "Failed to load artifacts",
          variant: "destructive"
        });
      }
    }
  };

  const handleArtifactChange = async (artifactId) => {
    setSelectedArtifact(artifactId);
    setSelectedSubArtifact(null);
    setSubArtifacts([]);

    if (artifactId) {
      try {
        const subArtifactsData = await tmfService.subArtifacts.getAllByArtifact(artifactId);
        setSubArtifacts(subArtifactsData);
      } catch (error) {
        console.error('Error loading sub-artifacts:', error);
        // Sub-artifacts are optional, so don't show error
      }
    }
  };

  const handleSubmit = async () => {
    if (!selectedZone || !selectedSection || !selectedArtifact) {
      toast({
        title: "Validation Error",
        description: "Please select Zone, Section, and Artifact",
        variant: "destructive"
      });
      return;
    }

    if (!document?._id) {
      toast({
        title: "Error",
        description: "Document ID is missing",
        variant: "destructive"
      });
      return;
    }

    setLoading(true);
    try {
      const zone = zones.find(z => z._id === selectedZone);
      const section = sections.find(s => s._id === selectedSection);
      const artifact = artifacts.find(a => a._id === selectedArtifact);

      const metadata = {
        zoneId: selectedZone,
        zoneNumber: zone?.zoneNumber,
        sectionId: selectedSection,
        sectionNumber: section?.sectionNumber,
        artifactId: selectedArtifact,
        artifactNumber: artifact?.artifactNumber,
        artifactName: artifact?.artifactName,
      };

      if (selectedSubArtifact) {
        metadata.subArtifactId = selectedSubArtifact;
        const subArtifact = subArtifacts.find(sa => sa._id === selectedSubArtifact);
        if (subArtifact) {
          metadata.subArtifactName = subArtifact.subArtifactName;
        }
      }

      await documentService.updateTMFMetadata(document._id, metadata);

      toast({
        title: "Success",
        description: "ISF metadata assigned successfully",
        variant: "default"
      });

      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      console.error('Error assigning ISF metadata:', error);
      toast({
        title: "Error",
        description: error.message || "Failed to assign ISF metadata",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderTree className="w-5 h-5" />
            Assign ISF Metadata
          </DialogTitle>
          <DialogDescription>
            Assign this document to the ISF hierarchy structure
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {document && (
            <div className="p-3 bg-gray-50 rounded-md">
              <p className="text-sm font-medium">{document.title || document.documentTitle}</p>
              <p className="text-xs text-gray-500">{document.fileName}</p>
            </div>
          )}

          <div className="space-y-2">
            <Label>Zone *</Label>
            <Select value={selectedZone} onValueChange={handleZoneChange}>
              <SelectTrigger>
                <SelectValue placeholder="Select a zone" />
              </SelectTrigger>
              <SelectContent>
                {zones.map((zone) => (
                  <SelectItem key={zone._id || zone.id} value={zone._id || zone.id}>
                    {zone.zoneName || zone.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Section *</Label>
            <Select value={selectedSection} onValueChange={handleSectionChange} disabled={!selectedZone}>
              <SelectTrigger>
                <SelectValue placeholder="Select a section" />
              </SelectTrigger>
              <SelectContent>
                {sections.map((section) => (
                  <SelectItem key={section._id || section.id} value={section._id || section.id}>
                    {section.sectionName || section.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Artifact *</Label>
            <Select value={selectedArtifact} onValueChange={handleArtifactChange} disabled={!selectedSection}>
              <SelectTrigger>
                <SelectValue placeholder="Select an artifact" />
              </SelectTrigger>
              <SelectContent>
                {artifacts.map((artifact) => (
                  <SelectItem key={artifact._id || artifact.id} value={artifact._id || artifact.id}>
                    {artifact.artifactName || artifact.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Sub-Artifact (Optional)</Label>
            <Select value={selectedSubArtifact} onValueChange={setSelectedSubArtifact} disabled={!selectedArtifact}>
              <SelectTrigger>
                <SelectValue placeholder="Select a sub-artifact" />
              </SelectTrigger>
              <SelectContent>
                {subArtifacts.map((subArtifact) => (
                  <SelectItem key={subArtifact._id || subArtifact.id} value={subArtifact._id || subArtifact.id}>
                    {subArtifact.subArtifactName || subArtifact.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={loading || !selectedZone || !selectedSection || !selectedArtifact}>
            {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            Assign ISF Metadata
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ISFAssignmentDialog;
