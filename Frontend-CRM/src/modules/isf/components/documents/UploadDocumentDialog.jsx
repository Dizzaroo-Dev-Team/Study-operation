import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { Loader2, Upload } from 'lucide-react';
import axios from 'axios';

const UploadDocumentDialog = ({ isOpen, onClose, onUploadComplete, existingDocument, selectedStudy }) => {
  const { toast } = useToast();
  const [isUploading, setIsUploading] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [metadata, setMetadata] = useState({
    title: '',
    category: '',
    version: '',
    site: '',
    studyId: '',
    description: '',
    changes: '',
  });

  useEffect(() => {
    // Pre-fill studyId from the CRM's currently selected study whenever the dialog opens
    setMetadata(prev => ({
      ...prev,
      studyId: prev.studyId || selectedStudy || '',
    }));
  }, [isOpen, selectedStudy]);

  useEffect(() => {
    if (existingDocument) {
      setMetadata(prev => ({
        ...prev,
        title: existingDocument.metadata?.title || '',
        category: existingDocument.metadata?.category || '',
        site: existingDocument.metadata?.site || '',
        studyId: existingDocument.metadata?.studyId || selectedStudy || '',
        description: existingDocument.metadata?.description || '',
      }));
    }
  }, [existingDocument, selectedStudy]);

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      setSelectedFile(file);
      // Auto-fill title from filename
      setMetadata(prev => ({
        ...prev,
        title: file.name.split('.')[0],
      }));
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setMetadata(prev => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      toast({
        title: "No file selected",
        description: "Please select a file to upload",
        variant: "destructive",
      });
      return;
    }

    if (existingDocument && !metadata.changes) {
      toast({
        title: "Changes required",
        description: "Please describe the changes in this version",
        variant: "destructive",
      });
      return;
    }

    try {
      setIsUploading(true);
      
      if (existingDocument) {
        try {
          // Add new version to existing document
          const versionResult = await axios.post(`/api/documents/${existingDocument.id}/versions`, {
            blobName: result.blobName,
            url: result.url,
            changes: metadata.changes,
            status: 'DRAFT',
          });

          if (versionResult.status !== 200) {
            throw new Error('Failed to add new version');
          }
        } catch (error) {
          console.error('Error adding version:', error);
          toast({
            title: "Version update failed",
            description: error.response?.data?.message || "Failed to update document version",
            variant: "destructive",
          });
          return;
        }
      }
      
      toast({
        title: "Upload successful",
        description: existingDocument 
          ? "New version has been uploaded successfully"
          : "Document has been uploaded successfully",
      });

      onUploadComplete(result);
      onClose();
    } catch (error) {
      console.error('Upload error:', error);
      toast({
        title: "Upload failed",
        description: error.message || "Failed to upload document",
        variant: "destructive",
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {existingDocument ? 'Upload New Version' : 'Upload Document'}
          </DialogTitle>
          <DialogDescription>
            {existingDocument 
              ? 'Upload a new version of the existing document'
              : 'Upload a new document to the clinical trials system'}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="file">Document File</Label>
            <Input
              id="file"
              type="file"
              onChange={handleFileChange}
              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
            />
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="title">Title</Label>
            <Input
              id="title"
              name="title"
              value={metadata.title}
              onChange={handleInputChange}
              placeholder="Document title"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="category">Category</Label>
            <Input
              id="category"
              name="category"
              value={metadata.category}
              onChange={handleInputChange}
              placeholder="Document category"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="version">Version</Label>
            <Input
              id="version"
              name="version"
              value={metadata.version}
              onChange={handleInputChange}
              placeholder="Document version"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="site">Site</Label>
            <Input
              id="site"
              name="site"
              value={metadata.site}
              onChange={handleInputChange}
              placeholder="Clinical site"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="studyId">Study ID</Label>
            <Input
              id="studyId"
              name="studyId"
              value={metadata.studyId}
              onChange={handleInputChange}
              placeholder="Study identifier"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="description">Description</Label>
            <Input
              id="description"
              name="description"
              value={metadata.description}
              onChange={handleInputChange}
              placeholder="Document description"
            />
          </div>

          {existingDocument && (
            <div className="grid gap-2">
              <Label htmlFor="changes">Changes in this version</Label>
              <Input
                id="changes"
                name="changes"
                value={metadata.changes}
                onChange={handleInputChange}
                placeholder="Describe the changes in this version"
              />
            </div>
          )}
        </div>

        <div className="flex justify-end space-x-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleUpload} disabled={isUploading}>
            {isUploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                {existingDocument ? 'Upload New Version' : 'Upload'}
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default UploadDocumentDialog; 