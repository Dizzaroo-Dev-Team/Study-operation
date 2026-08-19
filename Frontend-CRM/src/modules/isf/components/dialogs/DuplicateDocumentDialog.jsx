import React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { FileX, ExternalLink, AlertTriangle, Copy } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const DuplicateDocumentDialog = ({
  open,
  onOpenChange,
  existingDocumentId,
  fileName,
  message,
  onViewExisting,
  onProceedAnyway,
  onCancel,
}) => {
  const handleViewDocument = () => {
    if (onViewExisting) {
      onViewExisting(existingDocumentId);
    }
    onOpenChange(false);
  };

  const handleViewInList = () => {
    // This would need to be handled by the parent component
    // since we can't navigate from here
    onOpenChange(false);
  };

  const handleProceedAnyway = () => {
    if (onProceedAnyway) {
      onProceedAnyway();
    }
    onOpenChange(false);
  };

  const handleCancel = () => {
    if (onCancel) {
      onCancel();
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100">
              <FileX className="h-5 w-5 text-amber-600" />
            </div>
            <div>
              <DialogTitle className="text-xl">Duplicate Document Detected</DialogTitle>
              <DialogDescription className="mt-1">
                A document with identical content already exists in the system.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Document Already Exists</AlertTitle>
            <AlertDescription className="mt-2">
              <p className="text-sm">
                {message || `The document "${fileName || "Unknown"}" matches an existing document in the system.`}
              </p>
            </AlertDescription>
          </Alert>

          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Existing Document ID:</span>
                <Badge variant="outline" className="font-mono text-xs">
                  {existingDocumentId || "Unknown"}
                </Badge>
              </div>
              {fileName && (
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-gray-700">File Name:</span>
                  <span className="text-sm text-gray-600 truncate max-w-[200px]" title={fileName}>
                    {fileName}
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4">
            <p className="text-sm text-blue-900">
              <strong>What would you like to do?</strong>
            </p>
            <ul className="mt-2 space-y-1 text-sm text-blue-800 list-disc list-inside">
              <li>View the existing document to review its details</li>
              <li>Navigate to the document list to find it</li>
              <li>Cancel this upload if it's truly a duplicate</li>
            </ul>
          </div>
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            variant="outline"
            onClick={handleCancel}
            className="w-full sm:w-auto"
          >
            Cancel
          </Button>
          <Button
            variant="outline"
            onClick={handleViewInList}
            className="w-full sm:w-auto"
          >
            <Copy className="h-4 w-4 mr-2" />
            View in List
          </Button>
          <Button
            variant="default"
            onClick={handleViewDocument}
            className="w-full sm:w-auto"
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            View Existing Document
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default DuplicateDocumentDialog;

