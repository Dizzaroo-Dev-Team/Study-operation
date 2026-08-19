import { useEffect, useMemo, useState } from "react";
import { Btn, ActionBtn, EmptyState, AvatarStack, StatusBadge, VisitTypeBadge } from "../ui";
import type { Visit } from "../../types";

/** Pass from parent when table data is scoped by top-bar study/site — clears toolbar filters on change. */
export function tableScopeResetKey(studyId?: string | null, siteId?: string | null): string {
  return `${studyId ?? ""}:${siteId ?? ""}`;
}

// ─── VisitsTable ──────────────────────────────────────────────────────────────
export function VisitsTable({ visits, onRowClick, siteOptions, studyOptions, onCreateVisit, onArchive, onEdit, onDelete, showPagination = true, serverPagination, serverStatusFilter, onServerStatusFilterChange, scopeResetKey }: {
  visits: Visit[]; onRowClick: (v: Visit) => void;
  siteOptions?: string[];
  studyOptions?: string[];
  onCreateVisit?: () => void; onArchive?: (id: number | string, nextStatus: string) => void;
  onEdit?: (v: Visit) => void;
  onDelete?: (v: Visit) => void;
  showPagination?: boolean;
  serverPagination?: {
    page: number;
    pageSize: number;
    total: number;
    onPageChange: (page: number) => void;
  };
  /** When server-paginated, status filter is applied via API (parent passes these). */
  serverStatusFilter?: string;
  onServerStatusFilterChange?: (status: string) => void;
  scopeResetKey?: string;
}) {
  const clientScoped = !serverPagination;
  const [visitSearch, setVisitSearch] = useState("");
  const [siteFilter, setSiteFilter] = useState("All Sites");
  const [studyFilter, setStudyFilter] = useState("All Studies");
  const [localStatusFilter, setLocalStatusFilter] = useState("All Statuses");
  const statusFilter = serverPagination && serverStatusFilter !== undefined
    ? serverStatusFilter
    : localStatusFilter;
  const setStatusFilter = serverPagination && onServerStatusFilterChange
    ? onServerStatusFilterChange
    : setLocalStatusFilter;

  useEffect(() => {
    if (scopeResetKey == null) return;
    setVisitSearch("");
    if (clientScoped) {
      setSiteFilter("All Sites");
      setStudyFilter("All Studies");
      setLocalStatusFilter("All Statuses");
    }
  }, [scopeResetKey, clientScoped]);

  const filtered = useMemo(() => {
    const q = visitSearch.trim().toLowerCase();
    return visits.filter(v => {
      if (serverPagination) {
        // Site/study/status scope comes from the API when server-paginated.
        if (!q) return true;
        const hay = [
          v.id, v.site, v.study, v.cra?.name, v.type, v.status, v.date, v.dateIso,
        ].filter(Boolean).join(" ").toLowerCase();
        return hay.includes(q);
      }
      if (siteFilter !== "All Sites" && v.site !== siteFilter) return false;
      if (studyFilter !== "All Studies" && v.study !== studyFilter) return false;
      if (statusFilter !== "All Statuses") {
        if (v.status !== statusFilter) return false;
      } else if (v.status === "Archived") {
        return false;
      }
      if (!q) return true;
      const hay = [
        v.id, v.site, v.study, v.cra?.name, v.type, v.status, v.date, v.dateIso,
      ].filter(Boolean).join(" ").toLowerCase();
      return hay.includes(q);
    });
  }, [visits, visitSearch, siteFilter, studyFilter, statusFilter, serverPagination]);

  const findingsText = (v: Visit) => {
    if (v.findings === null) return <span style={{ fontSize: 13, color: "var(--text-muted)" }}>—</span>;
    if (v.findings === 0) return <span style={{ fontSize: 13, color: "var(--text-muted)" }}>0 open</span>;
    return <span style={{ fontSize: 13, color: `var(--${v.findingsColor})`, fontWeight: 500 }}>{v.findings} open</span>;
  };

  return (
    <div className="table-card">
      <div className="table-toolbar">
        <div className="filter-group">
          <div className="table-toolbar-search">
            <span style={{ color: "var(--text-muted)" }} aria-hidden>🔍</span>
            <input
              type="search"
              placeholder="Search visits..."
              value={visitSearch}
              onChange={e => setVisitSearch(e.target.value)}
              aria-label="Search visits"
            />
          </div>
          {clientScoped && (
            <>
              <select className="filter-select" value={siteFilter} onChange={e => setSiteFilter(e.target.value)}>
                <option>All Sites</option>
                {(siteOptions ?? Array.from(new Set(visits.map(v => v.site))).sort()).map(s => <option key={s}>{s}</option>)}
              </select>
              <select className="filter-select" value={studyFilter} onChange={e => setStudyFilter(e.target.value)}>
                <option>All Studies</option>
                {(studyOptions ?? Array.from(new Set(visits.map(v => v.study))).sort()).map(s => <option key={s}>{s}</option>)}
              </select>
            </>
          )}
          <select className="filter-select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            <option>All Statuses</option><option>Scheduled</option><option>Site Confirmed</option>
            <option>Post-Visit Action</option><option>Closed</option><option>Cancelled</option><option>Archived</option>
          </select>
        </div>
        <Btn variant="primary" size="sm" onClick={onCreateVisit}>＋ Create Visit</Btn>
      </div>
      {filtered.length === 0
        ? <EmptyState icon="📅" title="No visits found" sub="Try different search terms, filters, or create a new visit" />
        : <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr><th>Visit Date</th><th>Site Name</th><th>Study</th><th>Assign CRA</th><th>Visit Type</th><th>Status</th><th>Findings</th><th style={{ width: 132 }}>Actions</th></tr>
            </thead>
            <tbody>
              {filtered.map(v => (
                <tr key={v.id} onClick={() => onRowClick(v)}>
                  <td className="td-primary">{v.date}</td>
                  <td className="td-primary td-site-name" title={v.site}>{v.site}</td>
                  <td className="td-secondary">{v.study}</td>
                  <td><AvatarStack initials={v.cra.initials} color={v.cra.color} name={v.cra.name} /></td>
                  <td><VisitTypeBadge type={v.type} /></td>
                  <td><StatusBadge status={v.status} /></td>
                  <td>{findingsText(v)}</td>
                  <td>
                    <div className="action-btns">
                      <ActionBtn icon="👁" title="View" onClick={() => onRowClick(v)} />
                      {v.status?.toLowerCase() !== "closed" && v.status?.toLowerCase() !== "archived" && (
                        <ActionBtn icon="✏️" title="Edit" onClick={() => onEdit?.(v)} />
                      )}
                      {onArchive && (v.status?.toLowerCase() === "closed" || v.status?.toLowerCase() === "archived") && (
                        <ActionBtn
                          icon="🗃"
                          title={v.status === "Archived" ? "Unarchive" : "Archive"}
                          onClick={() => onArchive(v.id, v.status === "Archived" ? "Scheduled" : "Archived")}
                        />
                      )}
                      {onDelete && (
                        <ActionBtn icon="X" title="Delete" onClick={() => onDelete(v)} />
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>}
      <div className="table-footer">
        <span className="table-info">
          {serverPagination
            ? `Showing ${filtered.length} of ${serverPagination.total} visits (page ${serverPagination.page})`
            : `Showing ${filtered.length} of ${visits.length} visits`}
        </span>
        {showPagination && serverPagination && (() => {
          const totalPages = Math.max(1, Math.ceil(serverPagination.total / serverPagination.pageSize));
          const page = serverPagination.page;
          return (
            // Right margin keeps pagination clear of the floating Orbit AI button
            <div className="pagination" style={{ marginRight: 96 }}>
              <button
                type="button"
                className="page-btn"
                disabled={page <= 1}
                onClick={() => serverPagination.onPageChange(page - 1)}
              >
                ‹
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const p = i + 1;
                return (
                  <button
                    key={p}
                    type="button"
                    className={`page-btn${p === page ? " active" : ""}`}
                    onClick={() => serverPagination.onPageChange(p)}
                  >
                    {p}
                  </button>
                );
              })}
              <button
                type="button"
                className="page-btn"
                disabled={page >= totalPages}
                onClick={() => serverPagination.onPageChange(page + 1)}
              >
                ›
              </button>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
