import React from "react";
import type { ChecklistItem } from "../../types";

// ─── Avatar ───────────────────────────────────────────────────────────────────
export function AvatarComp({ initials, color, size = 26 }: { initials: string; color: string; size?: number }) {
  return (
    <div className={`avatar av-${color}`} style={{ width: size, height: size, fontSize: size * 0.42 }}>
      {initials}
    </div>
  );
}

export function AvatarStack({ initials, color, name }: { initials: string; color: string; name: string }) {
  return (
    <div className="avatar-stack">
      <AvatarComp initials={initials} color={color} />
      <span style={{ fontSize: 13 }}>{name}</span>
    </div>
  );
}

// ─── Badge ────────────────────────────────────────────────────────────────────
export function Badge({ children, color, dot = false }: { children: React.ReactNode; color: string; dot?: boolean }) {
  return (
    <span className={`badge ${color}`}>
      {dot && <span className="badge-dot" />}
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    Scheduled: "orange", "In Progress": "blue", Completed: "green", Closed: "green", "Post-Visit Action": "yellow",
    "Site Confirmed": "green", "Visit Confirmed": "purple", "Reschedule Requested": "orange", Cancelled: "red", "On Hold": "red", Open: "orange", "In Review": "blue",
    Resolved: "green", Final: "green", Draft: "orange", Active: "green",
  };
  return <Badge color={map[status] || "gray"} dot>{status}</Badge>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, string> = { "No Findings": "green", Critical: "red", Major: "orange", Minor: "yellow" };
  return <Badge color={map[severity] || "gray"}>{severity}</Badge>;
}

export function VisitTypeBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    "On-Site": "blue", Remote: "purple", Phone: "gray",
    "On-Site Monitoring": "blue", "Remote Monitoring": "purple", "Centralized Monitoring": "indigo",
    "On-Site Monitoring Visit": "blue", "Remote Monitoring Visit": "purple",
    "Site Initiation Visit": "indigo", "Initiation Visit": "indigo",
    "Site Qualification Visit": "teal",
    "Ad-Hoc Monitoring Visit": "red", "For-Cause Visit": "red", "For-Cause Monitoring Visit": "red",
    "Close-Out Visit": "gray", "Close-Out Monitoring Visit": "gray",
    "Routine Visit": "teal", "Routine Monitoring Visit": "teal",
    "Centralized Monitoring Visit": "indigo",
  };
  return <Badge color={map[type] || "gray"}>{type}</Badge>;
}

export function RiskBadge({ risk }: { risk: string }) {
  const map: Record<string, string> = { High: "red", Medium: "orange", Low: "yellow" };
  return <Badge color={map[risk] || "gray"}>{risk} Risk</Badge>;
}

// ─── Button ───────────────────────────────────────────────────────────────────
export function Btn({
  children, variant = "primary", size = "", onClick, style, disabled, title, testid,
}: {
  children: React.ReactNode; variant?: string; size?: string;
  onClick?: () => void; style?: React.CSSProperties; disabled?: boolean; title?: string; testid?: string;
}) {
  return (
    <button className={`btn btn-${variant}${size ? " btn-" + size : ""}`} onClick={onClick} style={style} disabled={disabled} title={title} data-testid={testid}>
      {children}
    </button>
  );
}

// ─── ActionBtn ────────────────────────────────────────────────────────────────
export function ActionBtn({ title, icon, onClick }: { title?: string; icon: string; onClick?: () => void }) {
  return (
    <button className="action-btn" title={title} onClick={e => { e.stopPropagation(); onClick?.(); }}>
      {icon}
    </button>
  );
}

// ─── ProgressBar ──────────────────────────────────────────────────────────────
export function ProgressBar({ value, color = "var(--green)" }: { value: number; color?: string }) {
  return (
    <div className="progress-bar-wrap">
      <div className="progress-bar-fill" style={{ width: `${value}%`, background: color }} />
    </div>
  );
}

// ─── AlertBanner ──────────────────────────────────────────────────────────────
export function AlertBanner({ type = "info", icon, children, action }: {
  type?: string; icon: string; children: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className={`alert-banner ${type}`}>
      <span>{icon}</span>
      <span style={{ flex: 1 }}>{children}</span>
      {action && <div style={{ marginLeft: "auto" }}>{action}</div>}
    </div>
  );
}

// ─── CheckItem ────────────────────────────────────────────────────────────────
export function CheckItem({ item, onToggle }: { item: ChecklistItem; onToggle: (id: number) => void }) {
  const tagClass = item.done ? "done-tag" : item.tagType === "required" ? "required-tag" : "optional-tag";
  const tagText  = item.done ? "Done"    : item.tagType === "required" ? "Required"     : "Optional";
  return (
    <div className={`check-item${item.done ? " done" : ""}`} onClick={() => onToggle(item.id)}>
      <input type="checkbox" checked={item.done} onChange={() => {}} />
      <span className="check-label">{item.text}</span>
      <span className={`check-tag ${tagClass}`}>{tagText}</span>
    </div>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────
export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton sk-line" style={{ width: i === lines - 1 ? "60%" : "100%" }} />
      ))}
    </div>
  );
}

// ─── EmptyState ───────────────────────────────────────────────────────────────
export function EmptyState({ icon, title, sub, action }: {
  icon: string; title: string; sub: string; action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <div className="empty-title">{title}</div>
      <div className="empty-sub">{sub}</div>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

// ─── Toggle ───────────────────────────────────────────────────────────────────
export function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span className="toggle-slider" />
    </label>
  );
}

// ─── Visit Workflow Stepper ──────────────────────────────────────────────────
export type WorkflowStep = {
  id: string;
  label: string;
};

export type WorkflowStepState = "done" | "active" | "upcoming";

export function VisitWorkflowStepper({
  steps,
  activeIndex,
  stepStates,
}: {
  steps: WorkflowStep[];
  activeIndex: number;
  stepStates?: WorkflowStepState[];
}) {
  return (
    <div className="vws-root" role="group" aria-label="Visit workflow">
      {steps.map((step, idx) => {
        const state: WorkflowStepState =
          stepStates?.[idx] ?? (idx < activeIndex ? "done" : idx === activeIndex ? "active" : "upcoming");
        const isDone = state === "done";
        const isActive = state === "active";
        return (
          <React.Fragment key={step.id}>
            <div className={`vws-item vws-${state}`} aria-current={isActive ? "step" : undefined}>
              <div className="vws-bubble-wrap">
                <div className="vws-bubble">
                  {isDone ? (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden>
                      <polyline points="2,7 6,11 12,3" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : (
                    <span className="vws-num">{idx + 1}</span>
                  )}
                </div>
                {isActive && <span className="vws-pulse" aria-hidden="true" />}
              </div>
              <span className="vws-label">{step.label}</span>
            </div>
            {idx < steps.length - 1 && (
              <div className={`vws-track${idx < activeIndex ? " vws-track-done" : ""}`} aria-hidden="true">
                <div className="vws-track-fill" />
              </div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
