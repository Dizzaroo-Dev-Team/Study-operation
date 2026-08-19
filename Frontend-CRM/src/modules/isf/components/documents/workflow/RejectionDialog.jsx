import React, { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, ArrowLeft, XCircle, Clock, FileWarning } from "lucide-react";
import { cn } from "@/lib/utils";

// Rejection categories - matches backend REJECTION_CATEGORIES
const REJECTION_CATEGORIES = {
  INCOMPLETE_METADATA: "Incomplete Metadata",
  INCORRECT_CLASSIFICATION: "Incorrect Classification",
  QUALITY_ISSUE: "Quality Issue",
  COMPLIANCE_ISSUE: "Compliance Issue",
  CONTENT_ERROR: "Content Error",
  MISSING_INFORMATION: "Missing Information",
  SECURITY_CONCERN: "Security Concern",
  OTHER: "Other",
};

// Stage display names
const STAGE_NAMES = {
  INTAKE: "Intake / Capture",
  QC_VALIDATION: "TMF Owner Validation",
  REVIEW_PREPARATION: "Review Preparation",
  IN_REVIEW: "Review",
  REVIEW: "Review",
  PRE_APPROVAL: "Pre-Approval",
  APPROVAL: "Approval",
  ACTIVATION: "Activation",
};

// Return-to stage options based on current stage
const getReturnToOptions = (currentStage) => {
  const stages = {
    QC_VALIDATION: [{ value: "INTAKE", label: "Intake / Capture" }],
    REVIEW_PREPARATION: [
      { value: "INTAKE", label: "Intake / Capture" },
      { value: "QC_VALIDATION", label: "TMF Owner Validation" },
    ],
    IN_REVIEW: [
      { value: "INTAKE", label: "Intake / Capture" },
      { value: "QC_VALIDATION", label: "TMF Owner Validation" },
      { value: "REVIEW_PREPARATION", label: "Review Preparation" },
    ],
    REVIEW: [
      { value: "INTAKE", label: "Intake / Capture" },
      { value: "QC_VALIDATION", label: "TMF Owner Validation" },
      { value: "REVIEW_PREPARATION", label: "Review Preparation" },
    ],
    PRE_APPROVAL: [
      { value: "INTAKE", label: "Intake / Capture" },
      { value: "QC_VALIDATION", label: "TMF Owner Validation" },
      { value: "IN_REVIEW", label: "Review" },
    ],
    APPROVAL: [
      { value: "INTAKE", label: "Intake / Capture" },
      { value: "QC_VALIDATION", label: "TMF Owner Validation" },
      { value: "IN_REVIEW", label: "Review" },
      { value: "PRE_APPROVAL", label: "Pre-Approval" },
    ],
  };

  return stages[currentStage] || [];
};

const RejectionDialog = ({
  open,
  onOpenChange,
  currentStage,
  documentTitle,
  onReject,
  isLoading = false,
}) => {
  const [reason, setReason] = useState("");
  const [category, setCategory] = useState("OTHER");
  const [returnToStage, setReturnToStage] = useState("");
  const [actionRequired, setActionRequired] = useState("");
  const [dueDate, setDueDate] = useState("");

  const returnOptions = getReturnToOptions(currentStage);
  const stageName = STAGE_NAMES[currentStage] || currentStage;

  const handleSubmit = () => {
    if (!reason.trim()) {
      return;
    }

    onReject({
      stage: currentStage,
      reason: reason.trim(),
      category,
      returnToStage: returnToStage || null,
      actionRequired: actionRequired.trim() || null,
      dueDate: dueDate || null,
    });
  };

  const handleClose = () => {
    setReason("");
    setCategory("OTHER");
    setReturnToStage("");
    setActionRequired("");
    setDueDate("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-[95vw] sm:max-w-[550px] max-h-[90vh] flex flex-col p-0">
        <DialogHeader className="px-4 pt-4 sm:px-6 sm:pt-6 pb-2 flex-shrink-0">
          <DialogTitle className="flex items-center gap-2 text-red-600 text-base sm:text-lg">
            <XCircle className="h-4 w-4 sm:h-5 sm:w-5 flex-shrink-0" />
            Reject Document
          </DialogTitle>
          <DialogDescription asChild>
            <div className="pt-1 sm:pt-2 space-y-1">
              <span className="text-xs sm:text-sm text-slate-600">
                Rejecting at{" "}
                <Badge variant="outline" className="font-semibold text-xs">
                  {stageName}
                </Badge>{" "}
                stage.
              </span>
              {documentTitle && (
                <span className="block text-xs sm:text-sm font-medium text-slate-900 truncate max-w-full">
                  {documentTitle}
                </span>
              )}
            </div>
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 space-y-4 py-3">
          {/* Warning Banner */}
          <div className="flex items-start gap-2 sm:gap-3 rounded-lg border border-amber-200 bg-amber-50 p-2 sm:p-3">
            <AlertTriangle className="h-4 w-4 sm:h-5 sm:w-5 text-amber-600 mt-0.5 flex-shrink-0" />
            <div className="text-xs sm:text-sm text-amber-800">
              <p className="font-semibold">This action will be recorded in the audit trail.</p>
            </div>
          </div>

          {/* Rejection Category */}
          <div className="space-y-1.5">
            <Label htmlFor="category" className="text-xs sm:text-sm font-semibold text-slate-700">
              Category <span className="text-red-500">*</span>
            </Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="h-9 sm:h-10 text-sm">
                <SelectValue placeholder="Select a category" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(REJECTION_CATEGORIES).map(([key, label]) => (
                  <SelectItem key={key} value={key} className="text-sm">
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Rejection Reason */}
          <div className="space-y-1.5">
            <Label htmlFor="reason" className="text-xs sm:text-sm font-semibold text-slate-700">
              Reason <span className="text-red-500">*</span>
            </Label>
            <Textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe why this document is being rejected..."
              rows={3}
              className="resize-none text-sm"
            />
          </div>

          {/* Return To Stage */}
          {returnOptions.length > 0 && (
            <div className="space-y-1.5">
              <Label htmlFor="returnToStage" className="text-xs sm:text-sm font-semibold text-slate-700">
                <ArrowLeft className="h-3 w-3 sm:h-4 sm:w-4 inline mr-1" />
                Return To Stage
              </Label>
              <Select 
                value={returnToStage || "__NONE__"} 
                onValueChange={(value) => setReturnToStage(value === "__NONE__" ? "" : value)}
              >
                <SelectTrigger className="h-9 sm:h-10 text-sm">
                  <SelectValue placeholder="Select stage (optional)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__NONE__" className="text-sm">Do not return (keep rejected)</SelectItem>
                  {returnOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value} className="text-sm">
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Action Required */}
          <div className="space-y-1.5">
            <Label htmlFor="actionRequired" className="text-xs sm:text-sm font-semibold text-slate-700">
              <FileWarning className="h-3 w-3 sm:h-4 sm:w-4 inline mr-1" />
              Action Required
            </Label>
            <Textarea
              id="actionRequired"
              value={actionRequired}
              onChange={(e) => setActionRequired(e.target.value)}
              placeholder="Specify the action needed to resolve..."
              rows={2}
              className="resize-none text-sm"
            />
          </div>

          {/* Due Date */}
          <div className="space-y-1.5">
            <Label htmlFor="dueDate" className="text-xs sm:text-sm font-semibold text-slate-700">
              <Clock className="h-3 w-3 sm:h-4 sm:w-4 inline mr-1" />
              Due Date
            </Label>
            <Input
              id="dueDate"
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="h-9 sm:h-10 text-sm"
              min={new Date().toISOString().split("T")[0]}
            />
          </div>
        </div>

        <DialogFooter className="px-4 pb-4 sm:px-6 sm:pb-6 pt-2 flex-shrink-0 gap-2 flex-col-reverse sm:flex-row">
          <Button variant="outline" onClick={handleClose} disabled={isLoading} className="w-full sm:w-auto h-9 sm:h-10 text-sm">
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleSubmit}
            disabled={!reason.trim() || isLoading}
            className="gap-2 w-full sm:w-auto h-9 sm:h-10 text-sm"
          >
            {isLoading ? (
              <>
                <span className="animate-spin">⏳</span>
                Rejecting...
              </>
            ) : (
              <>
                <XCircle className="h-4 w-4" />
                Reject Document
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default RejectionDialog;

