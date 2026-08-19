import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Upload, Loader2, Shield, Eye, User, Settings } from 'lucide-react';
import { useToast } from "@/components/ui/use-toast";
import tmfService from '../../services/tmf.service';
import { Badge } from '@/components/ui/badge';

const PermissionDocumentDialog = ({ open, onOpenChange, onSubmit, loading = false, selectedItem = null, selectedStudy = '' }) => {
  console.log('🚀 PermissionDocumentDialog rendered with props:', { open, loading, selectedItem });
  
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null);
  
  // Get current user
  const user = { firstName: 'Demo', lastName: 'User' };

  // Form management with react-hook-form
  const { 
    register, 
    handleSubmit, 
    reset, 
    control,
    setValue,
    watch,
    formState: { errors, isSubmitting: formIsSubmitting }, 
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
      author: user?.firstName ? `${user.firstName} ${user.lastName}` : '',
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
      uploadDate: new Date()
    }
  });

  // Auto-populate fields from selectedItem
  useEffect(() => {
    console.log('🔍 Auto-populate effect triggered:', { open, selectedItem });
    
    if (open && selectedItem) {
      console.log('📋 SelectedItem structure:', JSON.stringify(selectedItem, null, 2));
      
      // Extract the actual data - handle both nested and flat structures
      const itemData = selectedItem.data || selectedItem;
      console.log('📦 Extracted itemData:', itemData);
      
      // Populate zone fields
      if (itemData.zoneNumber) {
        console.log('📍 Setting zoneNumber:', itemData.zoneNumber);
        setValue('zoneNumber', itemData.zoneNumber);
      }
      if (itemData.zoneName) {
        console.log('📍 Setting zoneName:', itemData.zoneName);
        setValue('zoneName', itemData.zoneName);
      }
      if (itemData.zoneDescription) {
        setValue('zoneDescription', itemData.zoneDescription);
      }
      
      // Populate section fields
      if (itemData.sectionNumber) {
        console.log('📍 Setting sectionNumber:', itemData.sectionNumber);
        setValue('sectionNumber', itemData.sectionNumber);
      }
      if (itemData.sectionName) {
        console.log('📍 Setting sectionName:', itemData.sectionName);
        setValue('sectionName', itemData.sectionName);
      }
      if (itemData.sectionDescription) {
        setValue('sectionDescription', itemData.sectionDescription);
      }
      
      // Populate artifact fields
      if (itemData.artifactNumber) {
        console.log('📍 Setting artifactNumber:', itemData.artifactNumber);
        setValue('artifactNumber', itemData.artifactNumber);
      }
      if (itemData.artifactName) {
        console.log('📍 Setting artifactName:', itemData.artifactName);
        setValue('artifactName', itemData.artifactName);
      }
      if (itemData.artifactDescription) {
        setValue('artifactDescription', itemData.artifactDescription);
      }
      
      // Populate subArtifact field
      if (itemData.subArtifactName) {
        console.log('📍 Setting subArtifactName:', itemData.subArtifactName);
        setValue('subArtifactName', itemData.subArtifactName);
      }
      
      console.log('✅ All fields auto-populated');
    } else {
      console.log('❌ Conditions not met - open:', open, 'selectedItem:', selectedItem);
    }
  }, [open, selectedItem, setValue]);

  // Ensure study is set from the selectedStudy prop and not editable in form
  useEffect(() => {
    if (open && selectedStudy) {
      setValue('study', selectedStudy);
    }
  }, [open, selectedStudy, setValue]);

  // Handle file upload
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      setUploadedFile(file);
      setValue('mimeType', file.type);
      setValue('fileName', file.name);
      setValue('fileSize', file.size);
    }
  };

  // Form submission handler
  const onFormSubmit = async (data) => {
    console.log('📤 Form submission started');
    
    if (!uploadedFile) {
      toast({
        title: "Error",
        description: "Please select a file to upload",
        variant: "destructive"
      });
      return;
    }

    setIsSubmitting(true);
    
    try {
      // Create FormData for file upload
      const formData = new FormData();
      
      // Add file
      formData.append('file', uploadedFile);
      
      // Add all form fields
      Object.keys(data).forEach(key => {
        if (data[key] !== null && data[key] !== undefined) {
          formData.append(key, data[key]);
        }
      });

      // Call the onSubmit prop with FormData
      if (onSubmit) {
        await onSubmit(formData);
      }
      
      // Reset form and close dialog
      reset();
      setUploadedFile(null);
      onOpenChange(false);
      
      toast({
        title: "Success",
        description: "Document uploaded successfully",
      });
      
    } catch (error) {
      console.error('Upload error:', error);
      toast({
        title: "Error",
        description: error.message || "Failed to upload document",
        variant: "destructive"
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle dialog close
  const handleClose = () => {
    reset();
    setUploadedFile(null);
    onOpenChange(false);
  };

  return (
    <Sheet open={open} onOpenChange={handleClose}>
      <SheetContent side="right" className="w-full sm:max-w-[600px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Upload className="w-5 h-5" />
            Upload Document
          </SheetTitle>
          <SheetDescription>
            Upload a new document to the ISF repository
          </SheetDescription>
        </SheetHeader>
        
        <div className="mt-6">
          <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-6">
            {/* File Upload Section */}
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
              <input
                type="file"
                id="file"
                className="hidden"
                onChange={handleFileChange}
                accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx"
              />
              <label htmlFor="file" className="cursor-pointer">
                <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
                <p className="text-sm text-gray-600 mb-2">
                  Click to upload or drag and drop
                </p>
                <p className="text-xs text-gray-500">
                  PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX (MAX. 10MB)
                </p>
                {uploadedFile && (
                  <div className="mt-4">
                    <Badge variant="secondary">
                      {uploadedFile.name}
                    </Badge>
                  </div>
                )}
              </label>
            </div>

            {/* Document Information */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">Document Information</h3>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Document Title *</label>
                  <input
                    {...register('documentTitle', { required: 'Document title is required' })}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="Enter document title"
                  />
                  {errors.documentTitle && (
                    <p className="text-red-500 text-xs mt-1">{errors.documentTitle.message}</p>
                  )}
                </div>
                
                <div>
                  <label className="text-sm font-medium">Version</label>
                  <input
                    {...register('version')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="1.0"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium">Description</label>
                <textarea
                  {...register('description')}
                  rows={3}
                  className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Enter document description"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Document Type</label>
                  <select
                    {...register('documentType')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select type</option>
                    <option value="PROTOCOL">Protocol</option>
                    <option value="INFORMED_CONSENT">Informed Consent</option>
                    <option value="SAFETY_REPORT">Safety Report</option>
                    <option value="REGULATORY_DOCUMENT">Regulatory Document</option>
                    <option value="OTHER">Other</option>
                  </select>
                </div>
                
                <div>
                  <label className="text-sm font-medium">TMF Reference</label>
                  <input
                    {...register('tmfReference')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="e.g., 01.01.01"
                  />
                </div>
              </div>
            </div>

            {/* TMF Hierarchy Information */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">TMF Hierarchy</h3>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Zone Number</label>
                  <input
                    {...register('zoneNumber')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-gray-50"
                    readOnly
                  />
                </div>
                
                <div>
                  <label className="text-sm font-medium">Zone Name</label>
                  <input
                    {...register('zoneName')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-gray-50"
                    readOnly
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Section Number</label>
                  <input
                    {...register('sectionNumber')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-gray-50"
                    readOnly
                  />
                </div>
                
                <div>
                  <label className="text-sm font-medium">Section Name</label>
                  <input
                    {...register('sectionName')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-gray-50"
                    readOnly
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium">Artifact Number</label>
                  <input
                    {...register('artifactNumber')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-gray-50"
                    readOnly
                  />
                </div>
                
                <div>
                  <label className="text-sm font-medium">Artifact Name</label>
                  <input
                    {...register('artifactName')}
                    className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-gray-50"
                    readOnly
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium">Sub-Artifact Name</label>
                <input
                  {...register('subArtifactName')}
                  className="w-full mt-1 px-3 py-2 border border-gray-300 rounded-md bg-gray-50"
                  readOnly
                />
              </div>
            </div>

            {/* Submit Buttons */}
            <SheetFooter className="pt-4 border-t">
              <Button type="button" variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting || !uploadedFile}>
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4 mr-2" />
                    Upload Document
                  </>
                )}
              </Button>
            </SheetFooter>
          </form>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default PermissionDocumentDialog;
