import { useEffect, useMemo, useState } from "react";
import { useStudySite } from "../../../../../contexts/StudySiteContext";
import { assigneeBadgeFromName } from "../../../utils/studyTeamAssignees";
import { useSiteProfile } from "@/lib/queries/useSiteProfile";
import { Btn, EmptyState, SeverityBadge, StatusBadge, ActionBtn } from "../../ui";
import { AddFindingModal, type FindingFormValues } from "../../modals";
import type { Finding } from "../../../types";
import { findingIdForDisplay } from "../../../services/monitorService";
import { canonicalFindingCategory, categoryMatchesFilter, FINDING_CATEGORIES } from "../../../constants/findingCategories";
import { buildFindingMutationPayload, getFindingActionItems } from "../../../utils/findingActionItems";
import {
  FindingAssigneesCell,
  FindingCorrectiveActionsCell,
  FindingDueDatesCell,
} from "../../findings/FindingActionItemsCell";
import {
  useAddVisitFinding,
  useDeleteVisitFinding,
  useResolveVisitFinding,
  useUpdateVisitFinding,
  useVisitFindings,
} from "@/lib/queries/useMonitoring";
import { extractApiErrorMessage, logMonitoringError } from "../../../utils/apiError";

function normalizeFindingStatus(status: string | null | undefined): string {
  return String(status || "").trim().toLowerCase();
}

function isResolvedFinding(finding: Pick<Finding, "status">): boolean {
  return normalizeFindingStatus(finding.status) === "resolved";
}

function isArchivedFinding(finding: Pick<Finding, "status">): boolean {
  return normalizeFindingStatus(finding.status) === "archived";
}

function isOpenFinding(finding: Pick<Finding, "status">): boolean {
  return !isResolvedFinding(finding) && !isArchivedFinding(finding);
}

function statusMatchesFilter(status: string, filter: string): boolean {
  return normalizeFindingStatus(status) === normalizeFindingStatus(filter);
}

function displayFindingStatus(status: string): string {
  const normalized = normalizeFindingStatus(status);
  const labels: Record<string, string> = {
    open: "Open",
    "in review": "In Review",
    resolved: "Resolved",
    archived: "Archived",
  };
  return labels[normalized] || status;
}

export function VisitFindingsTab({ visitId, showToast, onOpenFindingsCountChange, isVisitClosed = false, assignedCraName }: {
  visitId: string;
  /** Visit's study hint from API (may be Postgres id or protocol code — not always IAM resource id). */
  studyId?: string | null;
  showToast: (msg: string, type?: string) => void;
  onOpenFindingsCountChange?: (count: number) => void;
  isVisitClosed?: boolean;
  /** CRA assigned to this visit when it was created — always offered as a Responsible Person option. */
  assignedCraName?: string | null;
  assignedCraEmail?: string | null;
}) {
  const { selectedSiteId } = useStudySite();
  // "Responsible Person" is scoped to this site's Site Profile — only the
  // named contacts actually saved there (PI, Sub Investigator, CRC, Site
  // Head) are offered, not the whole study's IAM team — plus the CRA that
  // was assigned to this specific visit when it was created.
  const siteProfileQuery = useSiteProfile(selectedSiteId);
  const studyTeamAssigneeOptions = useMemo(() => {
    const profile = siteProfileQuery.data;
    const candidates: { name?: string | null; role: string }[] = [
      { name: assignedCraName, role: "CRA" },
      { name: profile?.pi_name, role: "PI" },
      { name: profile?.sub_investigator_name, role: "Sub-I" },
      { name: profile?.site_coordinator_name, role: "CRC" },
      { name: profile?.site_head_name, role: "Site Head" },
    ];
    const seen = new Set<string>();
    const options: { name: string; role: string; label: string }[] = [];
    for (const c of candidates) {
      const name = c.name?.trim();
      if (!name || seen.has(name)) continue;
      seen.add(name);
      options.push({ name, role: c.role, label: `${name} (${c.role})` });
    }
    return options;
  }, [siteProfileQuery.data, assignedCraName]);
  const studyTeamAssignees = useMemo(() => studyTeamAssigneeOptions.map((o) => o.name), [studyTeamAssigneeOptions]);
  const studyTeamAssigneesPending = Boolean(selectedSiteId) && siteProfileQuery.isLoading;
  const findingsQuery = useVisitFindings(visitId);
  const addFindingMutation = useAddVisitFinding(visitId);
  const updateFindingMutation = useUpdateVisitFinding(visitId);
  const resolveFindingMutation = useResolveVisitFinding(visitId);
  const deleteFindingMutation = useDeleteVisitFinding(visitId);
  const findings = findingsQuery.data ?? [];
  const [findingSearch, setFindingSearch] = useState("");
  const [catFilter, setCatFilter] = useState("All Categories");
  const [sevFilter, setSevFilter] = useState("All Severities");
  const [statFilter, setStatFilter] = useState("All Statuses");
  const [showAdd, setShowAdd] = useState(false);
  const [editingFinding, setEditingFinding] = useState<Finding | null>(null);

  useEffect(() => {
    setFindingSearch("");
    setCatFilter("All Categories");
    setSevFilter("All Severities");
    setStatFilter("All Statuses");
    setEditingFinding(null);
  }, [visitId]);

  useEffect(() => {
    if (findingsQuery.isError) {
      showToast("Failed to load findings", "error");
    }
  }, [findingsQuery.isError, showToast]);

  const findingCounts = useMemo(() => ({
    open: findings.filter(isOpenFinding).length,
    resolved: findings.filter(isResolvedFinding).length,
  }), [findings]);

  const displayedFindings = useMemo(() => {
    const q = findingSearch.trim().toLowerCase();
    return findings.filter((f) => {
      if (!categoryMatchesFilter(f.category, catFilter)) return false;
      if (sevFilter !== "All Severities" && f.severity !== sevFilter) return false;
      if (statFilter === "All Statuses") {
        if (isArchivedFinding(f)) return false;
      } else if (!statusMatchesFilter(f.status, statFilter)) {
        return false;
      }
      if (!q) return true;
      const hay = [
        f.id,
        findingIdForDisplay(f.id, visitId),
        canonicalFindingCategory(f.category),
        f.subjectId,
        f.reference,
        f.description,
        f.severity,
        f.status,
        f.assignee?.name,
        f.dueDate,
        f.resolution,
        ...getFindingActionItems(f).flatMap((item) => [
          item.assignee?.name,
          item.dueDate,
          item.resolution,
        ]),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [findings, findingSearch, visitId, catFilter, sevFilter, statFilter]);

  useEffect(() => {
    onOpenFindingsCountChange?.(findingCounts.open);
  }, [findingCounts.open, onOpenFindingsCountChange]);

  const handleAdd = async (form: FindingFormValues) => {
    setEditingFinding(null);
    setShowAdd(false);

    try {
      await addFindingMutation.mutateAsync(buildFindingMutationPayload(form, assigneeBadgeFromName));
      showToast("Finding added successfully", "success");
    } catch {
      showToast("Failed to add finding", "error");
    }
  };

  const handleEdit = (form: FindingFormValues) => {
    if (!editingFinding) return;
    updateFindingMutation
      .mutateAsync({
        findingId: editingFinding.id,
        payload: {
          ...buildFindingMutationPayload(form, assigneeBadgeFromName),
          status: editingFinding.status,
        },
      })
      .then(() => {
        showToast("Finding updated", "success");
      })
      .catch((err) => {
        logMonitoringError("updateVisitFinding", err);
        showToast(extractApiErrorMessage(err, "Failed to update finding"), "error");
      })
      .finally(() => {
        setEditingFinding(null);
        setShowAdd(false);
      });
  };

  return (
    <div className="fade-in">
      <div className="table-toolbar" style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--radius) var(--radius) 0 0", borderBottom: "none" }}>
        <div className="filter-group" style={{ alignItems: "center" }}>
          <div className="table-toolbar-search">
            <span style={{ color: "var(--text-muted)" }} aria-hidden>🔍</span>
            <input
              type="search"
              placeholder="Search findings..."
              value={findingSearch}
              onChange={(e) => setFindingSearch(e.target.value)}
              aria-label="Search findings for this visit"
            />
          </div>
          <select className="filter-select" value={catFilter} onChange={(e) => setCatFilter(e.target.value)} aria-label="Filter by category">
            <option>All Categories</option>
            {FINDING_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <select className="filter-select" value={sevFilter} onChange={(e) => setSevFilter(e.target.value)} aria-label="Filter by severity">
            <option>All Severities</option>
            <option>No Findings</option>
            <option>Critical</option>
            <option>Major</option>
            <option>Minor</option>
          </select>
          <select className="filter-select" value={statFilter} onChange={(e) => setStatFilter(e.target.value)} aria-label="Filter by status">
            <option>All Statuses</option>
            <option>Open</option>
            <option>In Review</option>
            <option>Resolved</option>
            <option>Archived</option>
          </select>
        </div>
        <div className="table-toolbar-actions">
          {!isVisitClosed && (
            <Btn variant="primary" size="sm" onClick={() => setShowAdd(true)}>＋ Add Finding</Btn>
          )}
        </div>
      </div>

      <div className="table-card" style={{ borderRadius: "0 0 var(--radius) var(--radius)" }}>
        {findingsQuery.isPending
          ? <EmptyState icon="⏳" title="Loading findings…" sub="" />
          : findings.length === 0
          ? <EmptyState icon="✅" title="No findings" sub="Great! No findings have been logged for this visit." />
          : displayedFindings.length === 0
            ? <EmptyState icon="🔍" title="No matching findings" sub="Try different search terms or filters. With Status set to All Statuses, archived findings are hidden—choose Archived in the status dropdown to view them." />
            : <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr><th>ID</th><th>Category</th><th>Subject ID</th><th>Finding</th><th>Severity</th><th>Status</th><th>Responsible Person</th><th>Due Date</th><th>Action</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {displayedFindings.map(f => (
                  <tr key={f.id}>
                    <td><span style={{ fontFamily: "DM Mono,monospace", fontSize: 12, color: "var(--text-muted)" }} title={f.id}>{findingIdForDisplay(f.id, visitId)}</span></td>
                    <td className="td-secondary">{canonicalFindingCategory(f.category)}</td>
                    <td className="td-secondary" style={{ fontSize: 12.5 }} title={f.subjectId || ""}>
                      {(f.subjectId || "").trim() || "—"}
                    </td>
                    <td><div className="td-primary" style={{ maxWidth: 220 }}>{f.description}</div></td>
                    <td><SeverityBadge severity={f.severity} /></td>
                    <td><StatusBadge status={displayFindingStatus(f.status)} /></td>
                    <td><FindingAssigneesCell finding={f} /></td>
                    <td><FindingDueDatesCell finding={f} /></td>
                    <td><FindingCorrectiveActionsCell finding={f} /></td>
                    <td>
                      {isVisitClosed ? (
                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>—</span>
                      ) : (
                        <div className="action-btns" style={{ pointerEvents: isVisitClosed ? "none" : "auto" }}>
                          {!isVisitClosed && (
                            <ActionBtn icon="✏️" title="Edit" onClick={() => { setEditingFinding(f); setShowAdd(true); }} />
                          )}
                          {isOpenFinding(f) && (
                            <ActionBtn icon="✓" title="Resolve"
                              onClick={() => {
                                if (isVisitClosed) return;
                                resolveFindingMutation.mutate(f.id, {
                                  onSuccess: () => showToast("Marked as resolved", "success"),
                                  onError: () => showToast("Failed to resolve finding", "error"),
                                });
                              }} />
                          )}
                          <ActionBtn
                            icon="🗑️"
                            title="Delete"
                            onClick={() => {
                              if (isVisitClosed) return;
                              if (!window.confirm("Delete this finding? This action cannot be undone.")) return;
                              deleteFindingMutation.mutate(f.id, {
                                onSuccess: () => showToast("Finding deleted", "success"),
                                onError: () => showToast("Failed to delete finding", "error"),
                              });
                            }}
                          />
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}
        <div className="table-footer">
          <span className="table-info">
            {displayedFindings.length === findings.length
              ? `${findings.length} findings | `
              : `${displayedFindings.length} of ${findings.length} findings shown | `}
            {findingCounts.open} open | {findingCounts.resolved} resolved
          </span>
        </div>
      </div>

      {!isVisitClosed && (
        <AddFindingModal
          open={showAdd}
          onClose={() => { setShowAdd(false); setEditingFinding(null); }}
          onSubmit={editingFinding ? handleEdit : handleAdd}
          initialFinding={editingFinding}
          assignees={studyTeamAssignees}
          assigneeOptions={studyTeamAssigneeOptions}
          assigneesLoading={studyTeamAssigneesPending}
        />
      )}
    </div>
  );
}
