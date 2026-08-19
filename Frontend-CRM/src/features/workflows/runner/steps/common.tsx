// runner/steps/common.tsx
// Shared contract for every generic step component, plus tiny styled primitives
// so the steps stay consistent without pulling in a design-system dependency.

import React from "react";
import type { AvailableAction, Step, WorkflowInstance } from "../../types";

export interface StepProps {
  step: Step;
  instance: WorkflowInstance;
  actions: AvailableAction[];
  busy: boolean;
  // payload = form data / signature meta merged into context on the backend
  onAct: (transitionId: string, payload?: Record<string, unknown>, comment?: string) => void;
  // When true (engine drives CDA/CTA), document/review steps may mount the real
  // OnlyOffice editor for the instance's subject_ref agreement instead of the
  // placeholder. Fail-safe undefined/false → placeholder (sandbox unchanged).
  embedDocs?: boolean;
  // DEV-only: the backend WORKFLOW_DEV_SWEEP flag is on. Enables the dev controls
  // that have no place in prod — the manual sweep trigger (job/timer panels) and
  // the wait_message test-event-deliver button. Prod uses the Celery beat → false.
  devSweep?: boolean;
  // Re-pull the runner's state (instance + actions + audit) without a page
  // reload. V2 panels (job / wait_message / call) call this when server-side
  // progress lands (a job completes, a message arrives, children finish).
  onReload?: () => void | Promise<void>;
}

export function ActionButtons({
  actions,
  busy,
  onAct,
  payload,
}: {
  actions: AvailableAction[];
  busy: boolean;
  onAct: StepProps["onAct"];
  payload?: Record<string, unknown>;
}) {
  const [comment, setComment] = React.useState("");
  const needsComment = actions.some((a) => a.requires_comment);

  return (
    <div style={{ marginTop: 16 }}>
      {needsComment && (
        <textarea
          placeholder="Comment (required for some actions)…"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          style={ui.textarea}
        />
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
        {actions.map((a) => (
          <button
            key={a.transition_id}
            disabled={busy || (a.requires_comment && !comment.trim())}
            onClick={() => onAct(a.transition_id, payload, comment.trim() || undefined)}
            style={a.action === "reject" ? ui.btnDanger : ui.btnPrimary}
          >
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export const ui: Record<string, React.CSSProperties> = {
  card: {
    border: "1px solid #e6eaf0",
    borderRadius: 12,
    padding: 24,
    background: "#fff",
    maxWidth: 560,
    boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
  },
  label: { display: "block", fontSize: 13, fontWeight: 600, color: "#334155", marginBottom: 6 },
  input: {
    width: "100%",
    padding: "9px 11px",
    border: "1px solid #cbd5e1",
    borderRadius: 8,
    fontSize: 14,
    marginBottom: 12,
    boxSizing: "border-box",
    color: "#0f172a",
  },
  textarea: {
    width: "100%",
    minHeight: 64,
    padding: "9px 11px",
    border: "1px solid #cbd5e1",
    borderRadius: 8,
    fontSize: 14,
    boxSizing: "border-box",
    color: "#0f172a",
    lineHeight: 1.5,
  },
  btnPrimary: {
    padding: "9px 16px",
    background: "#4f46e5",
    color: "#fff",
    border: "none",
    borderRadius: 8,
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
    boxShadow: "0 1px 2px rgba(79,70,229,0.18)",
  },
  btnDanger: {
    padding: "9px 16px",
    background: "#fff",
    color: "#dc2626",
    border: "1px solid #fca5a5",
    borderRadius: 8,
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
  },
  badge: {
    display: "inline-block",
    padding: "3px 11px",
    borderRadius: 999,
    fontSize: 11.5,
    fontWeight: 700,
    letterSpacing: 0.3,
  },
};
