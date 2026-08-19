import { VisitTypeBadge, AvatarComp, Skeleton, EmptyState } from "../../ui";
import { useVisitWorkflow } from "../../../context/VisitWorkflowContext";

function dateOnlyFromDisplay(raw?: string): string {
  const value = String(raw || "").trim();
  if (!value) return "";
  return value.split("·", 1)[0].trim();
}

function utcDateMsFromIso(raw?: string): number | null {
  const value = String(raw || "").trim();
  if (!value) return null;
  const datePart = value.slice(0, 10);
  const match = datePart.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const timestamp = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(timestamp) ? null : timestamp;
}

function formatDurationDays(days?: number | null): string {
  if (days == null || !Number.isFinite(days) || days <= 0) return "";
  const normalized = Number.isInteger(days) ? String(days) : String(Number(days.toFixed(2)));
  return `${normalized} ${Number(normalized) === 1 ? "day" : "days"}`;
}

function durationDaysFromDates(startIso?: string, endIso?: string): string {
  const start = utcDateMsFromIso(startIso);
  const end = utcDateMsFromIso(endIso || startIso);
  if (start == null || end == null || end < start) return "";
  const days = Math.round((end - start) / 86_400_000) + 1;
  return formatDurationDays(days);
}

function displayOrDash(value?: string | null): string {
  const trimmed = String(value ?? "").trim();
  return trimmed || "—";
}

export function OverviewTab() {
  const { overview, overviewLoading } = useVisitWorkflow();
  const activityItems = overview?.recentActivity ?? [];
  const visitDetails = overview?.visitDetails;
  const siteContact = overview?.siteContact;
  const startDate = dateOnlyFromDisplay(visitDetails?.visitDate) || "TBD";
  const endDate = dateOnlyFromDisplay(visitDetails?.endDate || visitDetails?.visitDate) || "TBD";
  const durationDays =
    formatDurationDays(visitDetails?.estimatedDurationDays) ||
    durationDaysFromDates(visitDetails?.visitDateIso, visitDetails?.endDateIso) ||
    "TBD";

  return (
    <div className="fade-in">
      {overviewLoading ? (
        <div style={{ marginBottom: 16 }}>
          <Skeleton />
        </div>
      ) : null}

      <div className="overview-grid">
        <div className="info-card">
          <div className="info-card-title">Visit Details</div>
          <div className="info-rows">
            {[
              ["Visit Type", visitDetails?.visitType
                ? <VisitTypeBadge type={visitDetails.visitType} />
                : "—"],
              ["Start Date", startDate],
              ["End Date", endDate],
              ["Duration", durationDays],
              ["Protocol", displayOrDash(visitDetails?.protocol)],
              ["Sponsor", displayOrDash(visitDetails?.sponsor)],
            ].map(([k, v], i) => (
              <div key={i} className="info-row">
                <span className="info-key">{k}</span>
                <span className="info-val">{v}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="info-card">
          <div className="info-card-title">Site Contact Information</div>
          <div className="info-rows">
            {[
              ["Principal Investigator", displayOrDash(siteContact?.principalInvestigator)],
              ["PI Email", displayOrDash(siteContact?.piEmail)],
              ["Study Coordinator", displayOrDash(siteContact?.studyCoordinator)],
              ["Coordinator Email", displayOrDash(siteContact?.coordinatorEmail)],
              ["Coordinator Phone", displayOrDash(siteContact?.coordinatorPhone)],
              ["Site Address", displayOrDash(siteContact?.siteAddress)],
              ["IRB Approval", displayOrDash(siteContact?.irbApproval)],
            ].map(([k, v], i) => (
              <div key={i} className="info-row">
                <span className="info-key">{k}</span>
                <span className="info-val">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="info-card" style={{ marginTop: 16 }}>
        <div className="info-card-title">Recent Activity</div>
        {activityItems.length === 0 ? (
          <EmptyState icon="📋" title="No recent activity" sub="Activity for this visit will appear here." />
        ) : (
          <div className="activity-list">
            {activityItems.map((item, i) => (
              <div key={i} className="activity-item">
                <AvatarComp initials={item.initials} color={item.color} />
                <div className="activity-body">
                  <div className="activity-text">{item.text}</div>
                  <div className="activity-time">{item.time}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
