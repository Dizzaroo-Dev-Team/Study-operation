import { useCallback, useEffect, useMemo, useRef, useState, lazy, Suspense } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useQueryClient } from "@tanstack/react-query";
import {
  monitoringQueryKeys,
  useDecideVisitRescheduleRequest,
  usePendingVisitRescheduleRequest,
  useUpdateVisit,
  useCloseVisit,
  useVisitFindings,
} from "@/lib/queries/useMonitoring";
import { Btn, Badge, VisitTypeBadge, StatusBadge, VisitWorkflowStepper, Skeleton } from "../../ui";
import {
  type VisitRescheduleRequestItem,
} from "../../../services/monitorService";
import { VisitWorkflowProvider, useVisitWorkflow } from "../../../context/VisitWorkflowContext";
import type { Visit } from "../../../types";

const OverviewTab = lazy(() => import("./OverviewTab").then((m) => ({ default: m.OverviewTab })));
const ConfirmationLetterTab = lazy(() =>
  import("./ConfirmationLetterTab").then((m) => ({ default: m.ConfirmationLetterTab })),
);
const PreVisitTab = lazy(() => import("./PreVisitTab").then((m) => ({ default: m.PreVisitTab })));
const VisitFindingsTab = lazy(() => import("./VisitFindingsTab").then((m) => ({ default: m.VisitFindingsTab })));
const VisitReportTab = lazy(() => import("./VisitReportTab").then((m) => ({ default: m.VisitReportTab })));
const FollowUpLetterTab = lazy(() =>
  import("./FollowUpLetterTab").then((m) => ({ default: m.FollowUpLetterTab })),
);


function TabSkeleton() {
  return (
    <div className="fade-in" style={{ padding: 24 }}>
      <Skeleton />
    </div>
  );
}

// Tab indices (stable for localStorage / deep links):
//   0 = Overview, 1 = Confirmation Letter, 2 = Pre-Visit
//   4 = Findings, 5 = Visit Report, 6 = Follow-up Letter (closure is auto, no tab)
function tabIndexForStepperActiveIndex(stepperActiveIndex: number): number {
  if (stepperActiveIndex <= 1) return 1;
  if (stepperActiveIndex === 2) return 2;
  if (stepperActiveIndex === 3) return 4;
  if (stepperActiveIndex >= 4) return 6;
  return 6;
}

function workflowPhaseForStepperIdx(s: number): number {
  if (s <= 1) return 1;
  if (s === 2) return 2;
  if (s === 3) return 3;
  if (s === 4) return 4;
  return 5;
}

function workflowPhaseForTabIdx(t: number): number {
  if (t === 0) return 1;
  if (t <= 2) return 2;
  if (t === 4 || t === 5) return 3;
  if (t === 6) return 4;
  return 1;
}

const VISIT_WORKFLOW_STEPS = [
  { id: "schedule",         label: "Visit Schedule" },
  { id: "site-confirmation",label: "Site Confirmation" },
  { id: "pre-visit",        label: "Pre-Visit" },
  { id: "report",           label: "Visit Report" },
  { id: "follow-up",        label: "Follow-up Letter" },
  { id: "closure",          label: "Visit Closure" },
] as const;

function rescheduleSlots(request: VisitRescheduleRequestItem | null) {
  if (!request) return [];
  const slots = Array.isArray(request.proposed_slots) && request.proposed_slots.length > 0
    ? request.proposed_slots
    : [{
        index: 1,
        proposed_datetime_iso: request.proposed_date,
        proposed_end_datetime_iso: request.proposed_end_date,
      }];
  return slots
    .filter((slot) => slot.proposed_datetime_iso)
    .map((slot, idx) => ({ ...slot, index: Number(slot.index || idx + 1) }));
}

function formatRescheduleSlot(slot: { proposed_datetime_iso: string; proposed_end_datetime_iso?: string | null }) {
  const start = new Date(slot.proposed_datetime_iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
  const end = slot.proposed_end_datetime_iso
    ? new Date(slot.proposed_end_datetime_iso).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "";
  return end ? `${start} - ${end}` : start;
}

function isOpenFindingStatus(status: string | null | undefined): boolean {
  const normalized = String(status || "").trim().toLowerCase();
  return normalized !== "resolved" && normalized !== "archived" && normalized !== "closed";
}

function VisitDetailViewContent({ visit, onBack, showToast, initialTab, onTabChange }: {
  visit: Visit | null;
  onBack: () => void;
  showToast: (msg: string, type?: string) => void;
  initialTab?: number;
  onTabChange?: (tab: number) => void;
}) {
  const queryClient = useQueryClient();
  const workflow = useVisitWorkflow();
  const { overview } = workflow;

  const [activeTab, setActiveTab] = useState(initialTab ?? 0);
  const isInitialVisitMount = useRef(true);
  const prevStepperActiveIndexRef = useRef<number | null>(null);
  const skipNextStepperTabSyncRef = useRef(false);
  const lastSyncedStepperTargetTabRef = useRef<number | null>(null);
  const [pendingReschedule, setPendingReschedule] = useState<VisitRescheduleRequestItem | null>(null);
  const [rescheduleBusy, setRescheduleBusy] = useState(false);
  const [rescheduleAction, setRescheduleAction] = useState<"approved" | "rejected" | null>(null);
  const [selectedRescheduleSlot, setSelectedRescheduleSlot] = useState(1);
  const [showDeclineReason, setShowDeclineReason] = useState(false);
  const [declineReason, setDeclineReason] = useState("");
  const [localVisitDate, setLocalVisitDate] = useState<string | null>(null);
  const [localVisitStatus, setLocalVisitStatus] = useState<string | null>(null);
  const [visitReportStatus, setVisitReportStatus] = useState<string>("Draft");
  const [preVisitReportStatus, setPreVisitReportStatus] = useState<string>("DRAFT");
  const [preVisitReviewedAt, setPreVisitReviewedAt] = useState<string | null>(null);
  const [isFollowUpAcknowledged, setIsFollowUpAcknowledged] = useState(false);
  const [openPreVisitCount, setOpenPreVisitCount] = useState<number>(-1);
  const [openFindingsCount, setOpenFindingsCount] = useState<number>(
    typeof visit?.findings === "number" ? visit.findings : 0
  );
  const { user } = useAuth();
  const siteName = visit?.site || "—";
  const studyName = visit?.study || "N/A";
  const visitDate = localVisitDate || visit?.date || "TBD";
  const visitId = String(visit?.id ?? 1);
  const pendingRescheduleQuery = usePendingVisitRescheduleRequest(visitId);
  const findingsForCountQuery = useVisitFindings(visitId);
  const decideRescheduleMutation = useDecideVisitRescheduleRequest();
  const updateVisitMutation = useUpdateVisit();
  const visitLabelNumber =
    visit?.visitSeq != null ? String(visit.visitSeq) : String(visit?.id ?? "N/A");
  const confirmationLetterConfirmedAt = workflow.confirmationLetterConfirmedAt;
  const overviewStatusRaw = overview?.visitDetails?.status?.trim() ?? "";
  const overviewIsClosed =
    overviewStatusRaw.toLowerCase() === "closed" || Boolean(overview?.closedAt);

  const displayStatusLabel =
    (overviewIsClosed ? "Closed" : null) ||
    localVisitStatus ||
    overviewStatusRaw ||
    (confirmationLetterConfirmedAt ? "Site Confirmed" : "") ||
    visit?.status ||
    "Scheduled";
  const normalizedStatus = String(displayStatusLabel).trim().toLowerCase();
  const isSiteConfirmed = normalizedStatus === "site confirmed" || normalizedStatus === "visit confirmed";
  const preVisitStatusNormalized = String(preVisitReportStatus).trim().toUpperCase();
  const isPreVisitReviewed =
    Boolean(preVisitReviewedAt) ||
    preVisitStatusNormalized === "ACKNOWLEDGED" ||
    preVisitStatusNormalized === "REVIEWED";
  const isVisitReportApproved = String(visitReportStatus).trim().toLowerCase() === "approved";
  const isVisitClosed = normalizedStatus === "closed" || overviewIsClosed;

  useEffect(() => {
    setVisitReportStatus(workflow.visitReportStatus);
  }, [workflow.visitReportStatus]);

  useEffect(() => {
    setPreVisitReportStatus(workflow.preVisitReportStatus);
  }, [workflow.preVisitReportStatus]);

  useEffect(() => {
    setPreVisitReviewedAt(workflow.preVisitReviewedAt);
  }, [workflow.preVisitReviewedAt]);

  useEffect(() => {
    setIsFollowUpAcknowledged(workflow.isFollowUpAcknowledged);
  }, [workflow.isFollowUpAcknowledged]);

  const closeVisitMutation = useCloseVisit(visitId);

  // Auto-close visit when follow-up letter is acknowledged
  useEffect(() => {
    if (isFollowUpAcknowledged && !isVisitClosed && !closeVisitMutation.isPending) {
      closeVisitMutation.mutate(undefined, {
        onSuccess: () => setLocalVisitStatus("Closed"),
      });
    }
  }, [isFollowUpAcknowledged, isVisitClosed, closeVisitMutation]);

  useEffect(() => {
    const overviewStatus = overview?.visitDetails?.status?.trim();
    const overviewClosed =
      overviewStatus?.toLowerCase() === "closed" || Boolean(overview?.closedAt);
    if (overviewClosed) {
      setLocalVisitStatus("Closed");
      return;
    }
    if (workflow.confirmationLetterConfirmedAt) {
      setLocalVisitStatus("Site Confirmed");
      return;
    }
    if (overviewStatus) {
      setLocalVisitStatus(overviewStatus);
    }
  }, [workflow.confirmationLetterConfirmedAt, overview?.visitDetails?.status, overview?.closedAt]);

  useEffect(() => {
    if (isInitialVisitMount.current) {
      isInitialVisitMount.current = false;
      return;
    }
    prevStepperActiveIndexRef.current = null;
    lastSyncedStepperTargetTabRef.current = null;
    skipNextStepperTabSyncRef.current = false;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visitId]);

  useEffect(() => {
    setOpenFindingsCount(typeof visit?.findings === "number" ? visit.findings : 0);
    setOpenPreVisitCount(-1);
  }, [visitId, visit?.findings]);

  useEffect(() => {
    if (!findingsForCountQuery.data) return;
    setOpenFindingsCount(
      findingsForCountQuery.data.filter((finding) => isOpenFindingStatus(finding.status)).length,
    );
  }, [findingsForCountQuery.data]);

  useEffect(() => {
    setPendingReschedule(pendingRescheduleQuery.data ?? null);
    setSelectedRescheduleSlot(1);
  }, [pendingRescheduleQuery.data]);

  const handleRescheduleDecision = async (decision: "approved" | "rejected") => {
    if (!pendingReschedule) return;
    const reason = decision === "rejected" ? declineReason.trim() : "";
    if (decision === "rejected" && reason.length < 3) {
      showToast("Please provide a reason for declining", "error");
      return;
    }
    try {
      setRescheduleBusy(true);
      setRescheduleAction(decision);
      await decideRescheduleMutation.mutateAsync({
        visitId,
        requestId: pendingReschedule.id,
        decision,
        reason: reason || undefined,
        selectedSlotIndex: decision === "approved" ? selectedRescheduleSlot : undefined,
      });
      if (decision === "approved") {
        const chosenSlot =
          rescheduleSlots(pendingReschedule).find((slot) => slot.index === selectedRescheduleSlot) ??
          rescheduleSlots(pendingReschedule)[0];
        const nextDate = new Date(chosenSlot?.proposed_datetime_iso || pendingReschedule.proposed_date).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        });
        setLocalVisitDate(nextDate);
        setLocalVisitStatus("Visit Confirmed");
      } else {
        setLocalVisitStatus("Scheduled");
      }
      setPendingReschedule(null);
      setShowDeclineReason(false);
      setDeclineReason("");
      showToast(
        decision === "approved" ? "Reschedule approved and visit date updated" : "Reschedule request declined",
        "success",
      );
    } catch {
      showToast("Failed to update reschedule request", "error");
    } finally {
      setRescheduleBusy(false);
      setRescheduleAction(null);
    }
  };

  const openFindings = openFindingsCount;
  const sdvText =
    overview?.sdvProgress
      ? `${overview.sdvProgress.verifiedSubjects}/${overview.sdvProgress.totalSubjects} Subjects`
      : "N/A";
  const piName = overview?.siteContact?.principalInvestigator || "N/A";
  const studyCoordinator = overview?.siteContact?.studyCoordinator || "N/A";
  const lastModifiedText = overview?.lastModified
    ? new Date(overview.lastModified).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : "—";

  const renderTab = () => {
    switch (activeTab) {
      case 0:
        return <OverviewTab />;
      case 1:
        return (
          <ConfirmationLetterTab
            visitId={visitId}
            showToast={showToast}
            visitStatus={displayStatusLabel}
            isVisitClosed={isVisitClosed}
          />
        );
      case 2:
        return (
          <PreVisitTab
            visitId={visitId}
            showToast={showToast}
            onOpenCountChange={setOpenPreVisitCount}
            isVisitClosed={isVisitClosed}
            preVisitReportStatus={preVisitReportStatus}
            preVisitReviewedAt={preVisitReviewedAt}
            onPreVisitReportStatusChange={setPreVisitReportStatus}
            onPreVisitReviewedChange={setPreVisitReviewedAt}
            siteIdForPrimaryStatus={overview?.visitDetails?.siteId}
            siteIrbSummary={overview?.siteContact?.irbApproval}
            onPreVisitReportSent={() => {
              setPreVisitReportStatus("SENT");
              void queryClient.refetchQueries({ queryKey: monitoringQueryKeys.preVisit(visitId) });
              void queryClient.refetchQueries({ queryKey: monitoringQueryKeys.visitOverview(visitId) });
            }}
          />
        );
      case 4:
        return (
          <VisitFindingsTab
            visitId={visitId}
            studyId={visit?.studyId}
            showToast={showToast}
            onOpenFindingsCountChange={setOpenFindingsCount}
            isVisitClosed={isVisitClosed}
            assignedCraName={visit?.cra?.name}
            assignedCraEmail={visit?.cra?.email}
          />
        );
      case 5:
        return (
          <VisitReportTab
            visitId={visitId}
            visitSeq={visit?.visitSeq}
            showToast={showToast}
            onStatusChange={setVisitReportStatus}
            authorEmail={user?.email}
            isVisitClosed={isVisitClosed}
          />
        );
      case 6:
        return (
          <FollowUpLetterTab
            visitId={visitId}
            showToast={showToast}
            isVisitClosed={isVisitClosed}
            isAcknowledged={isFollowUpAcknowledged}
          />
        );

      default:
        return null;
    }
  };

  useEffect(() => {
    if (!isVisitReportApproved) return;
    if (overviewIsClosed) return;
    if (normalizedStatus === "post-visit action" || normalizedStatus === "closed") return;

    let cancelled = false;
    updateVisitMutation.mutate(
      { visitId, payload: { status: "Post-Visit Action" } },
      {
        onSuccess: () => {
          if (cancelled) return;
          setLocalVisitStatus("Post-Visit Action");
        },
      },
    );

    return () => {
      cancelled = true;
    };
  }, [isVisitReportApproved, normalizedStatus, visitId, overviewIsClosed]);

  const stepperActiveIndex = useMemo(() => {
    let p = 1;
    if (isSiteConfirmed) p = Math.max(p, 2);
    if (isSiteConfirmed && isPreVisitReviewed) p = Math.max(p, 3);
    if (isVisitReportApproved) p = Math.max(p, 4);
    if (isFollowUpAcknowledged) p = Math.max(p, 6);
    if (isVisitClosed) p = Math.max(p, 6);
    return p;
  }, [isSiteConfirmed, isPreVisitReviewed, isVisitReportApproved, isFollowUpAcknowledged, isVisitClosed]);

  const changeTab = useCallback(
    (tab: number) => {
      const tabPhase = workflowPhaseForTabIdx(tab);
      const stepperPhase = workflowPhaseForStepperIdx(stepperActiveIndex);
      skipNextStepperTabSyncRef.current = tabPhase < stepperPhase;
      setActiveTab(tab);
      onTabChange?.(tab);
    },
    [onTabChange, stepperActiveIndex],
  );

  useEffect(() => {
    const prev = prevStepperActiveIndexRef.current;
    const targetTab = tabIndexForStepperActiveIndex(stepperActiveIndex);
    if (prev === null || stepperActiveIndex > prev) {
      const isDuplicateResync =
        skipNextStepperTabSyncRef.current &&
        lastSyncedStepperTargetTabRef.current !== null &&
        targetTab === lastSyncedStepperTargetTabRef.current;

      if (isDuplicateResync) {
        skipNextStepperTabSyncRef.current = false;
      } else {
        setActiveTab(targetTab);
        onTabChange?.(targetTab);
        lastSyncedStepperTargetTabRef.current = targetTab;
        skipNextStepperTabSyncRef.current = false;
      }
    }
    prevStepperActiveIndexRef.current = stepperActiveIndex;
  }, [stepperActiveIndex, onTabChange]);

  return (
    <div className="fade-in">
      <VisitWorkflowStepper
        steps={[...VISIT_WORKFLOW_STEPS]}
        activeIndex={stepperActiveIndex}
      />
      <div className="detail-header">
        <div className="detail-title-row">
          <div>
            <div className="detail-title">{siteName}</div>
            <div className="detail-subtitle">{studyName} · Monitoring Visit #{visitLabelNumber}</div>
            <div className="detail-badges">
              <VisitTypeBadge type={visit?.type || "On-Site"} />
              <StatusBadge status={displayStatusLabel} />
              <Badge color="gray">Visit #{visitLabelNumber}</Badge>
              {isVisitClosed && (
                <span style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  fontSize: 12,
                  fontWeight: 700,
                  color: "#92400e",
                  background: "#fef3c7",
                  border: "1.5px solid #fcd34d",
                  borderRadius: 20,
                  padding: "3px 10px",
                  letterSpacing: "0.01em",
                }}>
                  🔒 Locked (Read-Only)
                </span>
              )}
            </div>
          </div>
          <div className="detail-actions">
            <Btn variant="ghost" size="sm" onClick={onBack}>← Back</Btn>
          </div>
        </div>
        <div className="detail-meta">
          {[
            { label: "Visit Date",       val: visitDate },
            { label: "CRA",              val: visit?.cra?.name || "N/A" },
            { label: "PI",               val: piName },
            { label: "Study Coordinator", val: studyCoordinator },
            { label: "Open Findings",    val: <span style={{ color: openFindings > 0 ? "var(--red)" : "var(--text-muted)" }}>{openFindings} open</span> },
            { label: "SDV Progress",     val: <span style={{ color: "var(--green)" }}>{sdvText}</span> },
            { label: "Last Modified",    val: <span style={{ color: "var(--text-muted)" }}>{lastModifiedText}</span> },
          ].map((m, i) => (
            <div key={i} className="meta-item">
              <span className="meta-label">{m.label}</span>
              <span className="meta-val">{m.val}</span>
            </div>
          ))}
        </div>
      </div>

      {pendingReschedule && (
        <div className="card" style={{ marginBottom: 12, borderLeft: "4px solid var(--orange)" }}>
          <div style={{ fontSize: 14, lineHeight: 1.5 }}>
            The site has requested to reschedule this visit. Choose one of the proposed options below to confirm the new visit slot.
            Reason:{' '}
            <em>{pendingReschedule.reason}</em>.
          </div>
          <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
            {rescheduleSlots(pendingReschedule).map((slot) => (
              <label
                key={slot.index}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 10px",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  cursor: rescheduleBusy ? "not-allowed" : "pointer",
                }}
              >
                <input
                  type="radio"
                  name="reschedule-slot"
                  checked={selectedRescheduleSlot === slot.index}
                  disabled={rescheduleBusy}
                  onChange={() => setSelectedRescheduleSlot(slot.index)}
                />
                <span style={{ fontSize: 13 }}>
                  <strong>Option {slot.index}:</strong> {formatRescheduleSlot(slot)}
                </span>
              </label>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <Btn
              variant="ghost"
              size="sm"
              disabled={rescheduleBusy}
              onClick={() => setShowDeclineReason((v) => !v)}
            >
              {showDeclineReason ? "Cancel Decline" : (rescheduleBusy && rescheduleAction === "rejected" ? "Declining..." : "Decline")}
            </Btn>
            <Btn variant="primary" size="sm" disabled={rescheduleBusy} onClick={() => void handleRescheduleDecision("approved")}>
              {rescheduleBusy && rescheduleAction === "approved" ? "Accepting..." : "Accept"}
            </Btn>
          </div>
          {showDeclineReason && (
            <div style={{ marginTop: 10 }}>
              <textarea
                className="form-textarea"
                style={{ minHeight: 84 }}
                placeholder="Reason for declining (e.g. CRA is unavailable on that date)"
                value={declineReason}
                onChange={(e) => setDeclineReason(e.target.value)}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                <Btn
                  variant="secondary"
                  size="sm"
                  disabled={rescheduleBusy}
                  onClick={() => void handleRescheduleDecision("rejected")}
                >
                  {rescheduleBusy && rescheduleAction === "rejected" ? "Declining..." : "Confirm Decline"}
                </Btn>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="tabs-bar">
        <button
          className={`tab-item${activeTab === 0 ? " active" : ""}`}
          onClick={() => changeTab(0)}
        >
          Overview
        </button>
        <button
          className={`tab-item${activeTab === 1 ? " active" : ""}`}
          onClick={() => changeTab(1)}
        >
          Confirmation Letter
        </button>
        <button
          className={`tab-item${activeTab === 2 ? " active" : ""}`}
          onClick={() => changeTab(2)}
        >
          Pre-Visit <span className="tab-count">{Math.max(openPreVisitCount, 0)}</span>
        </button>

        <button
          type="button"
          className={`tab-item${activeTab === 4 ? " active" : ""}`}
          onClick={() => changeTab(4)}
          title="Open and resolved issues"
        >
          Findings
          {openFindingsCount > 0 && (
            <span className="tab-count" aria-label={`${openFindingsCount} open findings`}>
              {openFindingsCount}
            </span>
          )}
        </button>
        <button
          type="button"
          className={`tab-item${activeTab === 5 ? " active" : ""}`}
          onClick={() => changeTab(5)}
          title="Formal Monitoring Visit Report (MVR)"
        >
          Visit Report
        </button>
        <button
          type="button"
          className={`tab-item${activeTab === 6 ? " active" : ""}`}
          onClick={() => changeTab(6)}
          title="Letter sent to PI after visit"
        >
          Follow-up Letter
        </button>


      </div>

      <Suspense fallback={<TabSkeleton />}>{renderTab()}</Suspense>
    </div>
  );
}

export function VisitDetailView(props: {
  visit: Visit | null;
  onBack: () => void;
  showToast: (msg: string, type?: string) => void;
  initialTab?: number;
  onTabChange?: (tab: number) => void;
}) {
  const visitId = String(props.visit?.id ?? "");
  if (!visitId) return null;

  return (
    <VisitWorkflowProvider visitId={visitId}>
      <VisitDetailViewContent {...props} />
    </VisitWorkflowProvider>
  );
}
