import { useState, useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { monitoringQueryKeys, useNotifications } from "@/lib/queries/useMonitoring";
import { useStudySite } from "../../contexts/StudySiteContext";
import globalStyles from "./styles/globalStyles";
import { Topbar } from "./components/layout/Topbar";
import { NotifPanel } from "./components/layout/NotifPanel";
import { DashboardView } from "./components/views/DashboardView";
import { VisitDetailView } from "./components/views/visit-detail/VisitDetailView";
import { useToast, ToastContainer } from "./components/ui/Toast";
import type { Visit, BreadcrumbItem } from "./types";
import { visitMatchesWorkspace } from "./utils/visitWorkspace";

// ── localStorage persistence ──────────────────────────────────────────────
const MON_STATE_KEY = "dizzaroo_mon_visit_state";

interface SavedMonState { visit: Visit; activeTab: number }

function readMonState(): SavedMonState | null {
  try {
    const raw = localStorage.getItem(MON_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SavedMonState;
    return parsed?.visit?.id ? parsed : null;
  } catch { return null; }
}

function writeMonState(visit: Visit | null, activeTab: number): void {
  try {
    if (!visit) { localStorage.removeItem(MON_STATE_KEY); return; }
    localStorage.setItem(MON_STATE_KEY, JSON.stringify({ visit, activeTab }));
  } catch { /* ignore */ }
}

function clearMonState(): void {
  try { localStorage.removeItem(MON_STATE_KEY); } catch { /* ignore */ }
}

export default function App() {
  type MonChromeView = "dashboard" | "detail";
  const queryClient = useQueryClient();
  const { selectedStudyId, selectedSiteId, filteredSites, studies, loading: studySiteLoading } = useStudySite();
  const savedMonStateRef = useRef(readMonState());

  const [currentView, setCurrentView] = useState<MonChromeView>("dashboard");
  const [selectedVisit, setSelectedVisit] = useState<Visit | null>(null);
  const [restoredTab, setRestoredTab] = useState(0);
  const [restoreChecked, setRestoreChecked] = useState(false);
  /** When non-null, visit was opened from the dashboard — start on Pre-Visit (2) instead of Overview. */
  const [detailTabFromOpen, setDetailTabFromOpen] = useState<number | null>(null);
  /** Bumps each time a visit is opened so VisitDetailView remounts and applies the new initialTab. */
  const [detailSessionKey, setDetailSessionKey] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifCount, setNotifCount] = useState(0);
  const { toasts, showToast, removeToast } = useToast();
  const notificationsQuery = useNotifications();

  useEffect(() => {
    if (notificationsQuery.data != null) {
      setNotifCount(notificationsQuery.data.unread_count);
    }
  }, [notificationsQuery.data]);

  const goDashboard = useCallback(() => {
    setCurrentView("dashboard");
    setSelectedVisit(null);
    setDetailTabFromOpen(null);
    writeMonState(null, 0);
    void queryClient.invalidateQueries({ queryKey: monitoringQueryKeys.dashboard() });
    void queryClient.refetchQueries({ queryKey: monitoringQueryKeys.dashboard() });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [queryClient]);

  /** Pre-Visit tab index (must match VisitDetailView tab bar). */
  const DEFAULT_TAB_ON_OPEN_VISIT = 2;

  const openVisit = useCallback((visit: Visit) => {
    if (!visit.siteId?.trim() || !visit.studyId?.trim()) {
      showToast("This visit is missing site/study identifiers and cannot be opened", "error");
      return;
    }
    setSelectedVisit(visit);
    setCurrentView("detail");
    setDetailTabFromOpen(DEFAULT_TAB_ON_OPEN_VISIT);
    setDetailSessionKey((k) => k + 1);
    writeMonState(visit, DEFAULT_TAB_ON_OPEN_VISIT);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [showToast]);

  const handleTabChange = useCallback((tab: number) => {
    writeMonState(selectedVisit, tab);
  }, [selectedVisit]);

  // Restore visit detail from localStorage only after study/site context is ready and IDs match.
  useEffect(() => {
    if (studySiteLoading) return;
    if (!selectedStudyId || !selectedSiteId) return;
    if (restoreChecked) return;
    setRestoreChecked(true);

    const saved = savedMonStateRef.current;
    if (!saved?.visit?.id) return;

    if (visitMatchesWorkspace(saved.visit, selectedStudyId, selectedSiteId, filteredSites, studies)) {
      setSelectedVisit(saved.visit);
      setRestoredTab(saved.activeTab);
      setCurrentView("detail");
      setDetailSessionKey((k) => k + 1);
    } else {
      clearMonState();
    }
  }, [
    studySiteLoading,
    selectedStudyId,
    selectedSiteId,
    restoreChecked,
    filteredSites,
    studies,
  ]);

  // When the global site/study changes, leave visit detail if it belongs to another workspace.
  useEffect(() => {
    if (studySiteLoading) return;
    if (currentView !== "detail" || !selectedVisit) return;
    if (!visitMatchesWorkspace(selectedVisit, selectedStudyId, selectedSiteId, filteredSites, studies)) {
      goDashboard();
    }
  }, [
    studySiteLoading,
    currentView,
    selectedVisit,
    selectedSiteId,
    selectedStudyId,
    filteredSites,
    studies,
    goDashboard,
  ]);

  const workspaceReady = !studySiteLoading && Boolean(selectedStudyId && selectedSiteId);
  const canShowVisitDetail =
    currentView === "detail" &&
    selectedVisit != null &&
    workspaceReady &&
    visitMatchesWorkspace(selectedVisit, selectedStudyId, selectedSiteId, filteredSites, studies);

  const getBreadcrumb = (): BreadcrumbItem[] => {
    const base: BreadcrumbItem = { label: "Monitoring", view: "dashboard" };
    if (!canShowVisitDetail) return [base, { label: "Dashboard" }];
    return [base, { label: "Dashboard", view: "dashboard" }, { label: selectedVisit?.site || "Visit" }];
  };

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: globalStyles }} />
      <div className="mon-app">
        <div className="mon-content">
          <Topbar
            breadcrumb={getBreadcrumb()}
            onNavigate={(view: string) => {
              if (view === "dashboard") goDashboard();
            }}
            onNotifToggle={() => setNotifOpen((p) => !p)}
            notifOpen={notifOpen}
            unreadCount={notifCount}
          />

          <main className="mon-main">
            {canShowVisitDetail ? (
              <VisitDetailView
                key={detailSessionKey}
                visit={selectedVisit}
                onBack={goDashboard}
                showToast={showToast}
                initialTab={detailTabFromOpen ?? restoredTab}
                onTabChange={handleTabChange}
              />
            ) : (
              <DashboardView
                showToast={showToast}
                onVisitClick={openVisit}
              />
            )}
          </main>
        </div>
        <NotifPanel
          open={notifOpen}
          onClose={() => setNotifOpen(false)}
          onMarkAll={() => showToast("All notifications marked as read", "success")}
          onUnreadChange={(count) => setNotifCount(count)}
        />
      </div>
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </>
  );
}
