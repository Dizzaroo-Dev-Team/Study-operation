import { useState, useEffect, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Btn, Skeleton } from "../ui";
import { VisitsTable, tableScopeResetKey } from "../tables";
import { CreateVisitModal } from "../modals";
import { useStudyTeamAssigneeNames } from "../../hooks/useStudyTeamAssigneeNames";
import { assigneeBadgeFromName } from "../../utils/studyTeamAssignees";
import type { Visit, Finding } from "../../types";
import { useStudySite } from "../../../../contexts/StudySiteContext";
import { useMonitoringDashboard, useCreateVisit, useUpdateVisit, useDeleteVisit, monitoringQueryKeys } from "@/lib/queries/useMonitoring";
import {
  type DashboardFindingRow,
  type DashboardVisitRow,
} from "../../services/monitorService";
import { visitMatchesWorkspace } from "../../utils/visitWorkspace";

/** Terminal “done” visit states from the API (close flow sets Closed; legacy rows may be Completed). */
function isCountedAsCompletedVisit(status: string): boolean {
  const s = (status || "").trim();
  return s === "Completed" || s === "Closed";
}

/** Visiting still in-flight for upcoming / scheduling metrics — excludes Closed. */
function isActivePipelineVisitStatus(status: string): boolean {
  const s = (status || "").trim();
  return !["Completed", "Closed", "Cancelled", "Archived"].includes(s);
}

export function DashboardView({ showToast, onVisitClick }: {
  showToast: (msg: string, type?: string) => void;
  onVisitClick: (v: Visit) => void;
}) {
  const queryClient = useQueryClient();
  const { studies, filteredSites, selectedStudyId, selectedSiteId } = useStudySite();
  // "Assign CRA" lists every IAM user tagged CRA on this study (Study Setup →
  // Users / Study Team), not scoped down to a single site.
  const { names: studyTeamAssignees, isPending: studyTeamAssigneesPending } = useStudyTeamAssigneeNames(selectedStudyId, { onlyCra: true });
  const [visits, setVisits] = useState<Visit[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [overdueCount, setOverdueCount] = useState(0);
  const [showCreateVisit, setShowCreateVisit] = useState(false);
  const [editingVisit, setEditingVisit] = useState<Visit | null>(null);
  const [page, setPage] = useState(1);
  const [tableStatusFilter, setTableStatusFilter] = useState("All Statuses");
  const DASHBOARD_PAGE_SIZE = 25;

  const dashboardStudyFilter = useMemo(() => {
    if (!selectedStudyId) return undefined;
    const study = studies.find((s) => s.id === selectedStudyId);
    // Send postgres id + protocol code so backend can match duplicate study rows.
    return study?.id || study?.study_id || selectedStudyId;
  }, [studies, selectedStudyId]);

  const dashboardSiteFilter = useMemo(() => {
    if (!selectedSiteId) return undefined;
    const site = filteredSites.find(
      (s) => s.id === selectedSiteId || s.site_id === selectedSiteId,
    );
    return site?.site_id || site?.id || selectedSiteId;
  }, [filteredSites, selectedSiteId]);

  const dashboardQuery = useMonitoringDashboard({
    page,
    page_size: DASHBOARD_PAGE_SIZE,
    site_id: dashboardSiteFilter,
    study_id: dashboardStudyFilter,
    status: tableStatusFilter === "All Statuses" ? undefined : tableStatusFilter,
  });
  const createVisitMutation = useCreateVisit();
  const updateVisitMutation = useUpdateVisit();
  const deleteVisitMutation = useDeleteVisit();
  const loading = dashboardQuery.isPending;

  const siteNamesForModal = useMemo(
    () => filteredSites.map((s) => s.name).filter(Boolean).sort(),
    [filteredSites],
  );
  const studyNamesForModal = useMemo(
    () => studies.map((s) => s.name).filter(Boolean).sort(),
    [studies],
  );

  const visitsTableScopeKey = tableScopeResetKey(selectedStudyId, selectedSiteId);

  useEffect(() => {
    setPage(1);
    setTableStatusFilter("All Statuses");
  }, [selectedSiteId, selectedStudyId, dashboardSiteFilter, dashboardStudyFilter]);

  useEffect(() => {
    setShowCreateVisit(false);
    setEditingVisit(null);
  }, [selectedSiteId, selectedStudyId]);

  useEffect(() => {
    setPage(1);
  }, [tableStatusFilter]);

  useEffect(() => {
    const dashboard = dashboardQuery.data;
    if (!dashboard) return;
    const rows = dashboard.items ?? dashboard.visits ?? [];
    setVisits(
      rows.map((v) => {
        const displayCra = (v.cra_name || "").trim() || "Unassigned";
        const badge = assigneeBadgeFromName(displayCra);
        return {
          id: v.id,
          siteId: v.site_id ?? undefined,
          studyId: v.study_id ?? undefined,
          date: v.date,
          dateIso: v.date_iso ? String(v.date_iso) : undefined,
          endDate: v.end_date ?? undefined,
          endDateIso: v.end_date_iso ? String(v.end_date_iso) : undefined,
          site: v.site_name,
          study: v.study_name,
          cra: { initials: badge.initials, name: displayCra, color: badge.color },
          type: v.type || "On-Site",
          priority: v.priority ?? "Medium",
          status: v.status || "Scheduled",
          findings: v.open_findings,
          findingsColor: v.open_findings > 0 ? "red" : "muted",
          visitSeq: v.site_visit_number != null ? Number(v.site_visit_number) : undefined,
          estimatedDurationDays: v.estimated_duration_days ?? null,
        };
      }),
    );
    setFindings(
      dashboard.findings.map((f: DashboardFindingRow): Finding => ({
        id: f.id,
        visitId: f.visit_id,
        subjectId: f.subjectId ?? "",
        reference: f.reference ?? "",
        category: f.category,
        description: f.description,
        severity: f.severity,
        status: f.status,
        site: f.site,
        assignee: f.assignee,
        dueDate: f.dueDate,
        dueColor: f.dueColor,
        resolution: f.resolution,
        isOverdue: f.isOverdue ?? false,
      })),
    );
    setOverdueCount(dashboard.overdue_count ?? 0);
  }, [dashboardQuery.data]);

  useEffect(() => {
    if (dashboardQuery.isError) {
      showToast("Failed to load monitoring dashboard data", "error");
    }
  }, [dashboardQuery.isError, showToast]);

  const visitFromApiRow = (row: DashboardVisitRow): Visit => {
    const displayCra = (row.cra_name || "").trim() || "Unassigned";
    const badge = assigneeBadgeFromName(displayCra);
    const rawIso = row.date_iso != null && row.date_iso !== "" ? String(row.date_iso) : undefined;
    const dateIso = rawIso && rawIso.length >= 10 ? rawIso : undefined;
    return {
      id: row.id,
      siteId: row.site_id ?? undefined,
      studyId: row.study_id ?? undefined,
      date: row.date,
      dateIso,
      endDate: row.end_date ?? undefined,
      endDateIso: row.end_date_iso ? String(row.end_date_iso) : undefined,
      site: row.site_name,
      study: row.study_name,
      cra: { initials: badge.initials, name: displayCra, color: badge.color },
      type: row.type || "On-Site",
      priority: row.priority ?? "Medium",
      status: row.status || "Scheduled",
      findings: row.open_findings,
      findingsColor: row.open_findings > 0 ? "red" : "muted",
      visitSeq: row.site_visit_number != null ? Number(row.site_visit_number) : undefined,
      estimatedDurationDays: row.estimated_duration_days ?? null,
    };
  };

  const handleVisitModalSubmit = async (form: any) => {
    const scopeIds = {
      study_pg_id: selectedStudyId ?? undefined,
      site_pg_id: selectedSiteId ?? undefined,
    };
    if (
      editingVisit &&
      !visitMatchesWorkspace(editingVisit, selectedStudyId, selectedSiteId, filteredSites, studies)
    ) {
      showToast("This visit belongs to another site or study. Re-open it from the dashboard.", "error");
      setShowCreateVisit(false);
      setEditingVisit(null);
      return;
    }
    try {
      if (editingVisit) {
        const updated = await updateVisitMutation.mutateAsync({
          visitId: String(editingVisit.id),
          payload: { ...form, ...scopeIds },
        });
        const merged = visitFromApiRow(updated);
        setVisits(p => p.map(v => String(v.id) === String(updated.id) ? merged : v));
        showToast("Visit updated", "success");
      } else {
        const created = await createVisitMutation.mutateAsync({ ...form, ...scopeIds });
        const newVisit = visitFromApiRow(created);
        setPage(1);
        setVisits((p) => [newVisit, ...p]);
        showToast("Visit created successfully", "success");
      }
      setEditingVisit(null);
      setShowCreateVisit(false);
    } catch {
      showToast(editingVisit ? "Failed to update visit" : "Failed to create visit", "error");
    }
  };

  const handleDeleteVisit = async (visit: Visit) => {
    const confirmed = window.confirm(`Delete this visit for ${visit.site} on ${visit.date}? This cannot be undone.`);
    if (!confirmed) return;
    try {
      await deleteVisitMutation.mutateAsync(String(visit.id));
      setVisits((prev) => prev.filter((v) => String(v.id) !== String(visit.id)));
      setFindings((prev) => prev.filter((f) => String(f.visitId) !== String(visit.id)));
      void queryClient.refetchQueries({ queryKey: monitoringQueryKeys.dashboard() });
      showToast("Visit deleted", "success");
    } catch {
      showToast("Failed to delete visit", "error");
    }
  };

  const dashboardTotal = dashboardQuery.data?.total ?? visits.length;
  const dashboardSummary = dashboardQuery.data?.summary;
  const selectedStudyName = selectedStudyId
    ? (studies.find((s) => s.id === selectedStudyId)?.name || null)
    : null;
  const selectedSiteName = selectedSiteId
    ? (filteredSites.find((s) => s.site_id === selectedSiteId || s.id === selectedSiteId)?.name || null)
    : null;

  // Overdue count is computed server-side and stored in overdueCount state.
  const overdueIssues = overdueCount;
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);

  const parseVisitDate = (visit: Visit): Date | null => {
    if (visit.dateIso) {
      if (visit.dateIso.includes("T")) {
        const d = new Date(visit.dateIso);
        if (!Number.isNaN(d.getTime())) return d;
      } else {
        const iso = new Date(`${visit.dateIso}T00:00:00`);
        if (!Number.isNaN(iso.getTime())) return iso;
      }
    }
    const raw = String(visit.date || "").split("·")[0].trim();
    if (!raw || raw.toUpperCase() === "TBD") return null;
    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return null;
    parsed.setHours(0, 0, 0, 0);
    return parsed;
  };

  const upcomingByDate = visits.filter((v) => {
    if (!isActivePipelineVisitStatus(v.status)) return false;
    const dt = parseVisitDate(v);
    if (!dt) return false;
    const days = Math.floor((dt.getTime() - startOfToday.getTime()) / (1000 * 60 * 60 * 24));
    return days >= 0 && days <= 30;
  });
  const upcomingCount = upcomingByDate.length;
  const thisWeekCount = upcomingByDate.filter((v) => {
    const dt = parseVisitDate(v);
    if (!dt) return false;
    const days = Math.floor((dt.getTime() - startOfToday.getTime()) / (1000 * 60 * 60 * 24));
    return days >= 0 && days <= 6;
  }).length;
  const nextWeekCount = upcomingByDate.filter((v) => {
    const dt = parseVisitDate(v);
    if (!dt) return false;
    const days = Math.floor((dt.getTime() - startOfToday.getTime()) / (1000 * 60 * 60 * 24));
    return days >= 7 && days <= 13;
  }).length;
  const completedVisitsCount =
    dashboardSummary?.completed ??
    visits.filter((v) => isCountedAsCompletedVisit(v.status)).length;
  const completionRate =
    (dashboardSummary?.total_visits ?? dashboardTotal) > 0
      ? Math.round((completedVisitsCount / (dashboardSummary?.total_visits ?? dashboardTotal)) * 100)
      : 0;
  const completedInWindow = (startDayOffset: number, endDayOffset: number) =>
    visits.filter((v) => {
      if (!isCountedAsCompletedVisit(v.status)) return false;
      const dt = parseVisitDate(v);
      if (!dt) return false;
      const days = Math.floor((dt.getTime() - startOfToday.getTime()) / (1000 * 60 * 60 * 24));
      return days >= startDayOffset && days <= endDayOffset;
    }).length;
  const completedLast30Days = completedInWindow(-30, -1);
  const completedPrev30Days = completedInWindow(-60, -31);
  const completedDelta = completedLast30Days - completedPrev30Days;
  const completedDeltaLabel =
    completedDelta > 0
      ? `+${completedDelta} vs previous 30 days`
      : completedDelta < 0
        ? `${completedDelta} vs previous 30 days`
        : "No change vs previous 30 days";

  const archivedVisitIds = useMemo(
    () => new Set(visits.filter((v) => v.status === "Archived").map((v) => String(v.id))),
    [visits],
  );

  const findingsActive = useMemo(
    () => findings.filter((f) => !f.visitId || !archivedVisitIds.has(String(f.visitId))),
    [findings, archivedVisitIds],
  );

  const openFindingsDueThisWeek = findingsActive.filter((f) => {
    if (f.status !== "Open") return false;
    const dueRaw = String(f.dueDate || "").trim();
    if (!dueRaw || dueRaw.toUpperCase() === "TBD") return false;
    const monthDay = dueRaw.match(/^([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?$/);
    let due = monthDay
      ? new Date(`${monthDay[1]} ${monthDay[2]}, ${monthDay[3] || new Date().getFullYear()}`)
      : new Date(dueRaw);
    if (Number.isNaN(due.getTime())) return false;
    due.setHours(0, 0, 0, 0);
    const days = Math.floor((due.getTime() - startOfToday.getTime()) / (1000 * 60 * 60 * 24));
    return days >= 0 && days <= 6;
  }).length;

  if (loading) return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="skeleton sk-line" style={{ width: 200, height: 24, marginBottom: 8 }} />
          <div className="skeleton sk-line" style={{ width: 300, height: 14 }} />
        </div>
      </div>
      <div className="metrics-grid">
        {[1, 2, 3, 4].map(i => <div key={i} className="metric-card" style={{ minHeight: 100 }}><Skeleton lines={3} /></div>)}
      </div>

      <Skeleton lines={5} />
    </div>
  );

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <div className="page-title">Site Monitoring Dashboard</div>
          <div className="page-subtitle">Overview of all active monitoring activities · Last updated 2 min ago</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn
            variant="primary"
            testid="mon-create-visit-button"
            onClick={() => {
              if (!selectedStudyName || !selectedSiteName) {
                showToast("Select Study and Site from top bar first", "info");
                return;
              }
              setEditingVisit(null);
              setShowCreateVisit(true);
            }}
          >
            ＋ Create Visit
          </Btn>
        </div>
      </div>

      <div className="metrics-grid">
        <div className="metric-card red">
          <div className="metric-header">
            <div className="metric-icon-wrap">🚨</div>
            <span className="metric-trend trend-up">↑ {openFindingsDueThisWeek} due this week</span>
          </div>
          <div className="metric-value">{findingsActive.filter(f => f.status === "Open").length}</div>
          <div className="metric-label">Open Findings</div>
          <div className="metric-sub">
            {findingsActive.filter(f => f.severity === "Critical" && f.status === "Open").length} critical · {findingsActive.filter(f => f.severity === "Major" && f.status === "Open").length} major
          </div>
        </div>
        <div className="metric-card orange">
          <div className="metric-header">
            <div className="metric-icon-wrap">⏰</div>
            <span className="metric-trend trend-up">{overdueIssues} open past due date</span>
          </div>
          <div className="metric-value">{overdueIssues}</div>
          <div className="metric-label">Overdue Issues</div>
          <div className="metric-sub">Open findings with due date before today</div>
        </div>
        <div className="metric-card blue">
          <div className="metric-header">
            <div className="metric-icon-wrap">📅</div>
            <span className="metric-trend trend-neutral">{thisWeekCount} this week</span>
          </div>
          <div className="metric-value">{upcomingCount}</div>
          <div className="metric-label">Upcoming Visits</div>
          <div className="metric-sub">{thisWeekCount} this week · {nextWeekCount} next week</div>
        </div>
        <div className="metric-card green">
          <div className="metric-header">
            <div className="metric-icon-wrap">✅</div>
            <span className="metric-trend trend-down">↑ {completionRate}% rate</span>
          </div>
          <div className="metric-value">{completedVisitsCount}</div>
          <div className="metric-label">Completed Visits</div>
          <div className="metric-sub">{completedDeltaLabel}</div>
        </div>
      </div>

      <VisitsTable visits={visits} onRowClick={onVisitClick}
        scopeResetKey={visitsTableScopeKey}
        showPagination
        serverStatusFilter={tableStatusFilter}
        onServerStatusFilterChange={(status) => {
          setTableStatusFilter(status);
          setPage(1);
        }}
        serverPagination={{
          page,
          pageSize: DASHBOARD_PAGE_SIZE,
          total: dashboardTotal,
          onPageChange: setPage,
        }}
        onCreateVisit={() => { setEditingVisit(null); setShowCreateVisit(true); }}
        onEdit={(v) => { setEditingVisit(v); setShowCreateVisit(true); }}
        onDelete={(v) => void handleDeleteVisit(v)}
        onArchive={async (id, nextStatus) => {
          try {
            await updateVisitMutation.mutateAsync({
              visitId: String(id),
              payload: { status: nextStatus },
            });
            if (nextStatus === "Archived") {
              setVisits((p) => p.filter((v) => String(v.id) !== String(id)));
            }
            void queryClient.refetchQueries({ queryKey: monitoringQueryKeys.dashboard() });
            showToast(nextStatus === "Archived" ? "Visit archived" : "Visit unarchived", "success");
          } catch {
            showToast(nextStatus === "Archived" ? "Failed to archive visit" : "Failed to unarchive visit", "error");
          }
        }} />

      <CreateVisitModal
        open={showCreateVisit}
        onClose={() => { setShowCreateVisit(false); setEditingVisit(null); }}
        onSubmit={handleVisitModalSubmit}
        sites={siteNamesForModal}
        studies={studyNamesForModal}
        cras={studyTeamAssignees}
        craOptionsLoading={studyTeamAssigneesPending}
        initialVisit={editingVisit}
        lockedSite={selectedSiteName || undefined}
        lockedStudy={selectedStudyName || undefined}
      />
    </div>
  );
}
