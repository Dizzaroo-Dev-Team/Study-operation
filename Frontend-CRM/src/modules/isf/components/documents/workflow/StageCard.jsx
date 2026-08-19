import React from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import StageMetricsList from "./StageMetricsList";
import ComplianceTagList from "./ComplianceTagList";
import StageActionButtons from "./StageActionButtons";
import { cn } from "@/lib/utils";
import { CheckCircle2, CircleDot, Clock3, ShieldAlert, XCircle, Lock } from "lucide-react";
import { canPerformAnyWorkflowOperation } from "@/config/workflowPermissions";

const STATUS_ACCENTS = {
  completed: {
    card: "border-emerald-200/60 bg-gradient-to-br from-emerald-50/80 via-white to-white shadow-lg shadow-emerald-100/50 hover:shadow-xl hover:shadow-emerald-100/60",
    badge: "bg-emerald-500 text-white border-emerald-600 shadow-sm",
    progressTrack: "bg-emerald-100/80",
    progressIndicator: "bg-gradient-to-r from-emerald-500 to-emerald-600",
    stageNumber: "bg-gradient-to-br from-emerald-500 to-emerald-600 text-white border-0 shadow-md",
    stageIcon: "bg-gradient-to-br from-emerald-100 to-emerald-50 text-emerald-700 border border-emerald-200/50 shadow-sm",
    icon: CheckCircle2,
  },
  active: {
    card: "border-sky-300/60 bg-gradient-to-br from-sky-50/80 via-white to-white shadow-xl shadow-sky-100/60 ring-2 ring-sky-200/50 hover:shadow-2xl hover:shadow-sky-200/70",
    badge: "bg-sky-500 text-white border-sky-600 shadow-sm",
    progressTrack: "bg-sky-100/80",
    progressIndicator: "bg-gradient-to-r from-sky-500 to-sky-600",
    stageNumber: "bg-gradient-to-br from-sky-500 to-sky-600 text-white border-0 shadow-md",
    stageIcon: "bg-gradient-to-br from-sky-100 to-sky-50 text-sky-700 border border-sky-200/50 shadow-sm",
    icon: CircleDot,
  },
  rejected: {
    card: "border-red-200/60 bg-gradient-to-br from-red-50/80 via-white to-white shadow-lg shadow-red-100/50 ring-2 ring-red-200/50",
    badge: "bg-red-500 text-white border-red-600 shadow-sm",
    progressTrack: "bg-red-100/80",
    progressIndicator: "bg-gradient-to-r from-red-500 to-red-600",
    stageNumber: "bg-gradient-to-br from-red-500 to-red-600 text-white border-0 shadow-md",
    stageIcon: "bg-gradient-to-br from-red-100 to-red-50 text-red-700 border border-red-200/50 shadow-sm",
    icon: XCircle,
  },
  gated: {
    card: "border-amber-200/60 bg-gradient-to-br from-amber-50/80 via-white to-white shadow-lg shadow-amber-100/50",
    badge: "bg-amber-500 text-white border-amber-600 shadow-sm",
    progressTrack: "bg-amber-100/80",
    progressIndicator: "bg-gradient-to-r from-amber-500 to-amber-600",
    stageNumber: "bg-gradient-to-br from-amber-500 to-amber-600 text-white border-0 shadow-md",
    stageIcon: "bg-gradient-to-br from-amber-100 to-amber-50 text-amber-700 border border-amber-200/50 shadow-sm",
    icon: ShieldAlert,
  },
  pending: {
    card: "border-slate-200/60 bg-white hover:bg-slate-50/50",
    badge: "bg-slate-400 text-white border-slate-500 shadow-sm",
    progressTrack: "bg-slate-200/60",
    progressIndicator: "bg-gradient-to-r from-slate-400 to-slate-500",
    stageNumber: "bg-gradient-to-br from-slate-400 to-slate-500 text-white border-0 shadow-sm",
    stageIcon: "bg-slate-100 text-slate-600 border border-slate-200",
    icon: Clock3,
  },
  locked: {
    card: "border-slate-200/60 bg-slate-50/50 opacity-60 cursor-not-allowed",
    badge: "bg-slate-300 text-slate-500 border-slate-400 shadow-sm",
    progressTrack: "bg-slate-200/40",
    progressIndicator: "bg-slate-300",
    stageNumber: "bg-slate-300 text-slate-500 border-0 shadow-sm",
    stageIcon: "bg-slate-100 text-slate-400 border border-slate-200",
    icon: Lock,
  },
};

const StageCard = React.memo(function StageCard({ stage, index, userRole, actions, onOpen, statusConfig, isLocked = false, lockedReason = null, hideActions = false }) {

  const rawProgress = Number.isFinite(stage.progress) ? Math.min(Math.max(stage.progress, 0), 100) : 0;
  const isActive = stage.statusKey === "active";
  const isCompleted = stage.statusKey === "completed";
  const isRejected = stage.statusKey === "rejected";

  const stageProgress = rawProgress;
  const progressLabel = Number.isFinite(stageProgress) ? `${Math.round(stageProgress)}%` : "—";

  let effectiveStatusKey = (stageProgress === 100 && !isRejected) ? "completed" : stage.statusKey;
  if (isLocked) {
    effectiveStatusKey = "locked";
  }
  const accent = STATUS_ACCENTS[effectiveStatusKey] ?? STATUS_ACCENTS.pending;
  const StatusIcon = isLocked ? Lock : (accent.icon ?? Clock3);

  const handleOpen = (event) => {
    event?.stopPropagation?.();
    if (isLocked) return; // Don't open if locked
    onOpen?.(stage);
  };

  const handleClick = () => {
    if (isLocked || hideActions) return; // Don't open if locked
    onOpen?.(stage);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (isLocked || hideActions) return; // block key activation
      onOpen?.(stage);
    }
  };

  const toneClass = statusConfig?.tone ?? "bg-slate-100 text-slate-600 border-slate-200";
  // If progress is 100% and stage is not rejected, show "Completed" status label
  // This ensures that stages with 100% progress show as "Completed" even if statusKey is "active"
  let statusLabel = stage.statusLabel || statusConfig?.label || "Pending";
  if (isLocked) {
    statusLabel = "Locked";
  } else if (stageProgress === 100 && !isRejected) {
    statusLabel = "Completed";
  }

  // Only apply role-based locking when we actually know the user's role.
  // A null/unknown role means auth hasn't resolved yet (or this consumer didn't
  // pass one) — matching the parent workflow's `userRole &&` guard, we defer to
  // the isLocked/lockedReason the parent already computed rather than force a
  // lock and render a "Your role (null) …" message.
  if (!hideActions && userRole) {
    const canPerform = canPerformAnyWorkflowOperation(
      userRole,
      stage.key,
      ["edit", "review", "registerTraining", "manageChange", "resolveFindings", "approve"]
    );

    if (!canPerform) {
      isLocked = true;
      lockedReason = `Your role (${userRole}) does not have access to this stage`;
    }
  }


  return (
    <Card
      className={cn(
        "group relative flex flex-col border bg-white transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
        accent.card,
        isCompleted && "saturate-[1.02]",
        isActive && "ring-2 ring-offset-1",
        !isActive && !isLocked && "hover:-translate-y-1 hover:shadow-lg",
        (isLocked || hideActions) ? "cursor-not-allowed" : "cursor-pointer"
      )}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      tabIndex={isLocked ? -1 : 0}
      title={isLocked ? lockedReason || "Complete previous stages first" : undefined}
    >
      <CardHeader className="space-y-3 pb-2.5 px-4 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-all duration-200",
                accent.stageNumber
              )}
            >
              {String(index + 1).padStart(2, "0")}
            </div>
            <div
              className={cn(
                "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-all duration-200",
                accent.stageIcon
              )}
            >
              {stage.icon ? <stage.icon className="h-5 w-5" /> : null}
            </div>
          </div>
          <Badge className={cn(
            "flex items-center gap-1 border-0 px-2.5 py-1 text-[11px] font-semibold shrink-0",
            accent.badge
          )}>
            <StatusIcon className="h-3 w-3" />
            {statusLabel}
          </Badge>
        </div>
        <div className="space-y-1">
          <CardTitle className="text-base font-semibold text-slate-900 leading-snug line-clamp-1">
            {stage.title}
          </CardTitle>
          <CardDescription className="text-xs text-slate-600 leading-relaxed line-clamp-2">
            {stage.subtitle}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3 px-4 pb-4">
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Progress</span>
            <span className="text-xs font-semibold text-slate-900">{progressLabel}</span>
          </div>
          <Progress
            value={stageProgress}
            className={cn("h-2 rounded-full", accent.progressTrack)}
            indicatorClassName={cn(accent.progressIndicator, "rounded-full transition-all duration-300")}
          />
        </div>
        {isCompleted ? (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            <span>Completed</span>
          </div>
        ) : isRejected ? (
          <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700">
            <XCircle className="h-3.5 w-3.5 shrink-0" />
            <span className="line-clamp-1">{stage.rejectionReason ? `Rejected: ${stage.rejectionReason.substring(0, 35)}${stage.rejectionReason.length > 35 ? '...' : ''}` : 'Rejected'}</span>
          </div>
        ) : null}
        <div className="flex-1 min-h-0">
          <StageMetricsList
            metrics={stage.metrics}
            className="space-y-1.5 text-xs"
            labelClassName="text-[11px] font-medium text-slate-500"
            valueClassName="text-xs font-semibold text-slate-900"
          />
          <div className="mt-2">
            <ComplianceTagList tags={stage.compliance} />
          </div>
        </div>

        {isLocked ? (
          <div className="pt-2 mt-auto border-t border-slate-100">
            <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-xs font-medium text-slate-500">
              <Lock className="h-3.5 w-3.5 shrink-0" />
              <span className="line-clamp-1">{lockedReason || "Complete previous stage first"}</span>
            </div>
          </div>
        ) : hideActions ? (
          <div className="pt-2 mt-auto border-t border-emerald-200 bg-emerald-50 rounded-lg flex items-center justify-center px-3 py-2 text-xs font-medium text-emerald-700">
            <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
            <span>Document Published</span>
          </div>
        ) : (
          <div className="pt-2 mt-auto border-t border-slate-100">
            <StageActionButtons
              actions={actions}
              onPrimary={handleOpen}
              onSecondary={(e) => {
                // For QC_VALIDATION stage, secondary action should focus on TMF Owner field
                if (stage.key === "QC_VALIDATION" && actions?.secondary?.label === "Assign TMF Owner") {
                  handleOpen(e);
                  // Focus on TMF Owner field after sheet opens
                  setTimeout(() => {
                    const field = document.getElementById("qaLead");
                    if (field) {
                      field.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      field.focus();
                    }
                  }, 400);
                } else {
                  handleOpen(e);
                }
              }}
              onTertiary={(e) => {
                // Handle tertiary action - opens stage with specific focus
                handleOpen(e);
                // For REVIEW_PREPARATION: "Will remain in 3rd stage (Delegate my reviewer)"
                if (stage.key === "REVIEW_PREPARATION" && actions?.tertiary?.label === "Will remain in 3rd stage (Delegate my reviewer)") {
                  setTimeout(() => {
                    // Focus on delegate reviewer field after sheet opens
                    const field = document.getElementById("delegateReviewer");
                    if (field) {
                      field.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      field.focus();
                    }
                  }, 400);
                }
              }}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
});

export default StageCard;


