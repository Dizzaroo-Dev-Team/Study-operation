import React, { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { SimpleTooltip } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Sparkles, FileText, Calendar, Info, Layers, PenTool, Archive } from "lucide-react";
import { cn } from "@/lib/utils";

const ARCHIVE_STATUSES = {
  LOCKED: "Locked",
  ARCHIVED: "Archived",
  SUPERSEDED: "Superseded",
};

const RevisionForm = ({
  draft,
  updateDraft,
  disabled = false,
  isLoading,
  document,
  onSave,
}) => {

  const onInputChange = (field) => (event) => {
    updateDraft({ [field]: event.target.value });
  };

  const onSelectChange = (field) => (value) => {
    updateDraft({ [field]: value });
  };

  const onDateChange = (field) => (event) => {
    updateDraft({ [field]: event.target.value || null });
  };

  const formatDateInput = (value) => {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toISOString().split("T")[0];
  };

  const documentRevision = draft.documentRevision || "NO";
  const archiveOlderVersion = draft.archiveOlderVersion || "NO";
  const requiresChange = draft.requiresChange || false;

  const completionPercentage = useMemo(() => {
    // Logical progress calculation:
    // If no decision made yet (empty string): 0% (not started)
    // If NO revision needed: 100% (complete - no action required)
    // If YES revision needed:
    //   - If archiveOlderVersion is NO: 100% (decision made, no archiving needed - complete)
    //   - If archiveOlderVersion is YES: 
    //     * Archive status and date both set: 100% (complete)
    //     * Only one set: 50% (partial)
    //     * Neither set: 0% (incomplete)
    
    // If no decision has been made, return 0%
    if (!documentRevision || documentRevision === "" || documentRevision === null) {
      return 0;
    }
    
    if (documentRevision === "NO") {
      return 100;
    } else if (documentRevision === "YES") {
      if (archiveOlderVersion === "NO") {
        return 100; // Decision made, no archiving needed - complete
      } else if (archiveOlderVersion === "YES") {
        const hasArchiveStatus = draft.archiveStatus && draft.archiveStatus.trim() !== "";
        const hasArchiveDate = draft.archiveDate && draft.archiveDate !== null && draft.archiveDate !== "";
        
        if (hasArchiveStatus && hasArchiveDate) {
          return 100; // Both required fields complete
        } else if (hasArchiveStatus || hasArchiveDate) {
          return 50; // One of two fields complete
        } else {
          return 0; // Neither field complete
        }
      }
    }
    
    return 0;
  }, [documentRevision, archiveOlderVersion, draft.archiveStatus, draft.archiveDate]);

  return (
    <div className="space-y-6">
      {/* Stage Progress */}
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center justify-between text-sm font-semibold text-slate-700">
          <span>Stage Progress</span>
          <Badge
            className={cn(
              "rounded-full px-2.5 py-0.5 text-xs font-semibold",
              completionPercentage === 100
                ? "bg-emerald-100 text-emerald-700"
                : completionPercentage > 50
                ? "bg-sky-100 text-sky-700"
                : "bg-amber-100 text-amber-700"
            )}
          >
            {completionPercentage}% Complete
          </Badge>
        </div>
        <Progress
          value={completionPercentage}
          className="mt-2 h-2"
          indicatorClassName={
            completionPercentage === 100
              ? "bg-emerald-500"
              : completionPercentage > 50
              ? "bg-sky-500"
              : "bg-amber-500"
          }
        />
      </div>

      {/* Document Revision Section */}
      <div className="space-y-4 rounded-lg border border-gray-100 bg-gray-50/50 p-6">
        <div className="flex items-center space-x-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100">
            <PenTool className="h-4 w-4 text-blue-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">Document Revision</h3>
        </div>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="documentRevision" className="text-sm font-medium text-gray-700">Document Revision Required?</Label>
            <Select
              value={documentRevision}
              onValueChange={(value) => {
                updateDraft({ documentRevision: value });
                if (value === "NO") {
                  updateDraft({ archiveOlderVersion: "NO", archiveStatus: null, archiveDate: null, requiresChange: false });
                }
              }}
              disabled={disabled || isLoading}
            >
              <SelectTrigger className="h-10">
                <SelectValue placeholder="Select option" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="YES">YES</SelectItem>
                <SelectItem value="NO">NO</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {documentRevision === "YES" && (
            <>
              {/* Archive Older Version */}
              <div className="space-y-2 pt-4 border-t border-gray-200">
                <Label htmlFor="archiveOlderVersion" className="text-sm font-medium text-gray-700">Archive Older Version?</Label>
                <Select
                  value={archiveOlderVersion}
                  onValueChange={(value) => {
                    updateDraft({ archiveOlderVersion: value });
                    if (value === "NO") {
                      updateDraft({ archiveStatus: null, archiveDate: null });
                    }
                  }}
                  disabled={disabled || isLoading}
                >
                  <SelectTrigger className="h-10">
                    <SelectValue placeholder="Select option" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="YES">YES</SelectItem>
                    <SelectItem value="NO">NO</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Archive Details */}
              {archiveOlderVersion === "YES" && (
                <div className="space-y-4 pt-4 border-t border-gray-200">
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="archiveStatus" className="text-sm font-medium text-gray-700">
                        Archive Status
                      </Label>
                      <Select
                        value={draft.archiveStatus || ""}
                        onValueChange={onSelectChange("archiveStatus")}
                        disabled={disabled || isLoading}
                      >
                        <SelectTrigger className="h-10">
                          <SelectValue placeholder="Select status" />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(ARCHIVE_STATUSES).map(([key, label]) => (
                            <SelectItem key={key} value={key}>
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="archiveDate" className="text-sm font-medium text-gray-700">
                        Date of Archiving
                      </Label>
                      <Input
                        id="archiveDate"
                        type="date"
                        value={formatDateInput(draft.archiveDate)}
                        onChange={onDateChange("archiveDate")}
                        className="h-10"
                        disabled={disabled || isLoading}
                        max={new Date().toISOString().split('T')[0]}
                      />
                      {draft.archiveDate && (() => {
                        const archiveDate = new Date(draft.archiveDate);
                        const today = new Date();
                        today.setHours(0, 0, 0, 0);
                        if (archiveDate > today) {
                          return (
                            <div className="mt-2 p-2 rounded-lg bg-amber-50 border border-amber-200">
                              <p className="text-xs text-amber-700">
                                <Info className="h-3 w-3 inline mr-1" />
                                <strong>Warning:</strong> Archive date is in the future. Archiving dates should be today or in the past.
                              </p>
                            </div>
                          );
                        }
                        return null;
                      })()}
                    </div>
                  </div>
                </div>
              )}

              {/* Change Required */}
              <div className="space-y-2 pt-4 border-t border-gray-200">
                <Label htmlFor="requiresChange" className="text-sm font-medium text-gray-700">
                  Change Required?
                </Label>
                <Select
                  value={requiresChange ? "YES" : "NO"}
                  onValueChange={(value) => {
                    updateDraft({ requiresChange: value === "YES" });
                  }}
                  disabled={disabled || isLoading}
                >
                  <SelectTrigger className="h-10">
                    <SelectValue placeholder="Select option" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="YES">YES</SelectItem>
                    <SelectItem value="NO">NO</SelectItem>
                  </SelectContent>
                </Select>
                {requiresChange && (
                  <div className="mt-3 space-y-3">
                    <div className="p-3 rounded-lg bg-amber-50 border border-amber-200">
                      <p className="text-sm text-amber-700">
                        <strong>Note:</strong> If change is required, please contact the administrator to replace the document. This will reset the workflow to QC Validation stage and re-run all validation checks.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Notes Section */}
      <div className="space-y-4 rounded-lg border border-gray-100 bg-gray-50/50 p-6">
        <div className="flex items-center space-x-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100">
            <FileText className="h-4 w-4 text-indigo-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">Notes</h3>
        </div>
        <div className="space-y-2">
          <Textarea
            id="notes"
            value={draft.notes || ""}
            onChange={onInputChange("notes")}
            placeholder="Add any notes regarding revision or archiving"
            rows={4}
            disabled={disabled || isLoading}
          />
        </div>
      </div>

    </div>
  );
};

export default RevisionForm;
