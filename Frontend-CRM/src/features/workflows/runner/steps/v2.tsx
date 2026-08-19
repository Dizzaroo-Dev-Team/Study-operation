// runner/steps/v2.tsx
// Panels for the V2 step kinds: job (automated step), wait_message (external
// event), call (sub-workflow children) — plus the armed-timer chip. These make
// engine-side progress VISIBLE: panels poll the read models and, because dev
// stacks run no celery beat, trigger the dev sweep endpoint (gated to
// WORKFLOW_UNIFIED server-side) so pending jobs and due timers actually run.

import React from "react";
import { workflowApi } from "../../api";
import type {
  ChildInstance,
  InstanceActivity,
  Step,
  WorkflowJobRow,
} from "../../types";
import { StepProps, ui } from "./common";

const pill = (bg: string, fg: string): React.CSSProperties => ({
  fontSize: 11, fontWeight: 700, letterSpacing: 0.3, textTransform: "uppercase",
  background: bg, color: fg, borderRadius: 999, padding: "2px 10px",
});
const JOB_PILL: Record<string, React.CSSProperties> = {
  pending: pill("#fef9c3", "#a16207"),
  running: pill("#dbeafe", "#1d4ed8"),
  completed: pill("#dcfce7", "#15803d"),
  failed: pill("#fee2e2", "#b91c1c"),
  cancelled: pill("#f1f5f9", "#64748b"),
};
const smallBtn: React.CSSProperties = {
  padding: "6px 12px", borderRadius: 8, border: "1px solid #cbd5e1",
  background: "#fff", color: "#334155", cursor: "pointer", fontWeight: 600, fontSize: 13,
};

function Shell({ step, children }: { step: Step; children: React.ReactNode }) {
  return (
    <div style={ui.card}>
      <h3 style={{ marginTop: 0 }}>{step.name}</h3>
      {step.description && <p style={{ color: "#64748b", marginTop: 0 }}>{step.description}</p>}
      {children}
    </div>
  );
}

// Poll the instance's activity read model while `active`. In dev (sweep=true)
// each poll first runs the engine sweeps so pending work visibly executes.
function useActivity(instanceId: number, active: boolean, sweep: boolean,
                     intervalMs = 3000): [InstanceActivity | null, () => Promise<void>] {
  const [activity, setActivity] = React.useState<InstanceActivity | null>(null);
  const refresh = React.useCallback(async () => {
    if (sweep) {
      try { await workflowApi.runSweeps(); } catch { /* prod: beat does this */ }
    }
    try { setActivity(await workflowApi.getActivity(instanceId)); } catch { /* transient */ }
  }, [instanceId, sweep]);
  React.useEffect(() => {
    if (!active) return;
    void refresh();
    const t = window.setInterval(() => void refresh(), intervalMs);
    return () => window.clearInterval(t);
  }, [active, refresh, intervalMs]);
  return [activity, refresh];
}

// ---- JOB (automated step) ---------------------------------------------------
export function JobStep({ step, instance, devSweep, onReload }: StepProps) {
  const cfg = (step.config?.job ?? {}) as { kind?: string; max_attempts?: number };
  const active = instance.status === "active";
  const [activity, refresh] = useActivity(instance.id, active, Boolean(devSweep));
  const [retrying, setRetrying] = React.useState(false);

  const jobs = (activity?.jobs ?? []).filter((j) => j.step_id === step.id);
  const job: WorkflowJobRow | undefined = jobs[jobs.length - 1];

  // When the job finishes server-side, the instance has moved on — reload the
  // runner so the next step appears (this panel will unmount).
  const doneRef = React.useRef(false);
  React.useEffect(() => {
    if (job && (job.status === "completed") && !doneRef.current) {
      doneRef.current = true;
      void onReload?.();
    }
  }, [job, onReload]);

  const retry = async () => {
    if (!job) return;
    setRetrying(true);
    try {
      await workflowApi.retryJob(instance.id, job.id);
      await refresh();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <Shell step={step}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: "#475569" }}>
          Automated step — job kind <strong style={{ fontFamily: "ui-monospace, Menlo, monospace" }}>{cfg.kind ?? job?.kind ?? "?"}</strong>
        </span>
        {job ? (
          <span style={JOB_PILL[job.status] ?? JOB_PILL.pending}>{job.status}</span>
        ) : (
          <span style={JOB_PILL.pending}>queued</span>
        )}
        {job && (
          <span style={{ fontSize: 12, color: "#64748b" }}>
            attempt {job.attempts}/{job.max_attempts}
          </span>
        )}
      </div>
      {(job?.status === "pending" || job?.status === "running" || !job) && active && (
        <p style={{ color: "#64748b", fontSize: 13, margin: "10px 0 0" }}>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 999,
                         background: "#2563eb", marginRight: 8, animation: "wfPulse 1.2s infinite" }} />
          Running automatically — this panel updates itself.
        </p>
      )}
      {job?.error && (
        <div style={{ marginTop: 10, background: "#fef2f2", border: "1px solid #fecaca",
                      borderRadius: 8, padding: "8px 10px", color: "#b91c1c", fontSize: 13 }}>
          Last error: {job.error}
        </div>
      )}
      {/* DEGRADED completion: the job finished, but the real work couldn't run on
          this host (e.g. no PDF backend). Surface it instead of a silent "completed". */}
      {job?.status === "completed" && (job.result as { generated?: boolean } | null)?.generated === false && (
        <div style={{ marginTop: 10, background: "#fffbeb", border: "1px solid #fde68a",
                      borderRadius: 8, padding: "8px 10px", color: "#92400e", fontSize: 13 }}>
          ⚠ PDF generation is unavailable on this host — the step completed but no document was produced.
          {(job.result as { reason?: string })?.reason ? ` (${(job.result as { reason?: string }).reason})` : ""}
        </div>
      )}
      {/* Real artifact produced + durably persisted: offer a link. */}
      {job?.status === "completed" && (job.result as { generated?: boolean } | null)?.generated === true &&
        typeof (job.result as { document_url?: unknown })?.document_url === "string" && (
        <div style={{ marginTop: 10, background: "#f0fdf4", border: "1px solid #bbf7d0",
                      borderRadius: 8, padding: "8px 10px", color: "#15803d", fontSize: 13 }}>
          ✓ Document generated.{" "}
          <a href={(job.result as { document_url: string }).document_url} target="_blank"
             rel="noopener noreferrer" style={{ color: "#15803d", fontWeight: 600 }}>
            Open document ↗
          </a>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
        <button style={smallBtn} onClick={() => void refresh()}>Refresh</button>
        {job?.status === "failed" && (
          <button style={{ ...smallBtn, background: "#4f46e5", color: "#fff", border: "none",
                           opacity: retrying ? 0.5 : 1 }}
                  disabled={retrying} onClick={() => void retry()}>
            {retrying ? "Retrying…" : "Retry job"}
          </button>
        )}
      </div>
      <style>{`@keyframes wfPulse { 0%,100% { opacity: 1 } 50% { opacity: .3 } }`}</style>
    </Shell>
  );
}

// ---- ARMED TIMER CHIP --------------------------------------------------------
// Rendered by the runner next to any open step that has a pending timer.
// Counts down locally; when it crosses zero in dev, the runner's poll/sweep
// makes it actually fire (History then shows the fired row — not duplicated here).
export function TimerChip({ fireAt }: { fireAt: string }) {
  const [, force] = React.useReducer((n: number) => n + 1, 0);
  React.useEffect(() => {
    const t = window.setInterval(force, 1000);
    return () => window.clearInterval(t);
  }, []);
  const ms = new Date(fireAt).getTime() - Date.now();
  const overdue = ms <= 0;
  const mins = Math.floor(Math.abs(ms) / 60000);
  const secs = Math.floor((Math.abs(ms) % 60000) / 1000);
  return (
    <span
      title={`Timer fires at ${new Date(fireAt).toLocaleString()}`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600,
        color: overdue ? "#b91c1c" : "#b45309", background: overdue ? "#fee2e2" : "#fef3c7",
        border: `1px solid ${overdue ? "#fecaca" : "#fde68a"}`, borderRadius: 999, padding: "3px 10px",
      }}
    >
      ⏱ {overdue ? "firing…" : `escalates in ${mins}:${String(secs).padStart(2, "0")}`}
    </span>
  );
}

// ---- WAIT_MESSAGE (external event) -------------------------------------------
export function WaitMessageStep({ step, instance, devSweep, onReload }: StepProps) {
  const cfg = (step.config?.message ?? {}) as { name?: string };
  const name = cfg.name ?? "(unnamed event)";
  const [sending, setSending] = React.useState(false);
  const [note, setNote] = React.useState("");

  const deliver = async () => {
    if (!instance.subject_ref) return;
    setSending(true);
    setNote("");
    try {
      const r = await workflowApi.postEvent(name, instance.subject_ref, { test: true });
      setNote(r.delivered > 0 ? "Event delivered." : "Nothing was waiting for this event.");
      if (r.delivered > 0) void onReload?.();
    } catch (e: unknown) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <Shell step={step}>
      <p style={{ color: "#475569", margin: 0, fontSize: 14 }}>
        Waiting for the external event{" "}
        <strong style={{ fontFamily: "ui-monospace, Menlo, monospace" }}>{name}</strong>.
      </p>
      <p style={{ color: "#64748b", fontSize: 12.5, margin: "6px 0 0" }}>
        Correlation key:{" "}
        {instance.subject_ref ? (
          <code style={{ background: "#eef2f7", borderRadius: 6, padding: "1px 6px" }}>{instance.subject_ref}</code>
        ) : (
          <em>none — this instance has no subject_ref, so no event can reach it</em>
        )}
      </p>
      {Boolean(devSweep) && (
        <div style={{ marginTop: 14 }}>
          <button style={{ ...smallBtn, opacity: sending || !instance.subject_ref ? 0.5 : 1 }}
                  disabled={sending || !instance.subject_ref} onClick={() => void deliver()}>
            {sending ? "Delivering…" : "Deliver test event (dev)"}
          </button>
          {note && <span style={{ marginLeft: 10, fontSize: 12.5, color: "#475569" }}>{note}</span>}
        </div>
      )}
    </Shell>
  );
}

// ---- WAIT_CONDITION (hold until a registered condition is true) --------------
export function WaitConditionStep({ step, devSweep, onReload }: StepProps) {
  const cfg = (step.config?.wait ?? {}) as { condition?: string; message?: string };
  const condition = cfg.condition ?? "(unnamed condition)";
  const message = cfg.message || `Waiting until "${condition}" is satisfied.`;
  const [checking, setChecking] = React.useState(false);
  const [note, setNote] = React.useState("");

  // The workflow auto-continues on the sweep when the condition flips true; this just
  // lets a dev force a re-check now instead of waiting for the next sweep tick.
  const recheck = async () => {
    setChecking(true);
    setNote("");
    try {
      await workflowApi.runSweeps();
      setNote("Re-checked.");
      void onReload?.();
    } catch (e: unknown) {
      setNote(e instanceof Error ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  };

  return (
    <Shell step={step}>
      <p style={{ color: "#475569", margin: 0, fontSize: 14 }}>⏳ {message}</p>
      <p style={{ color: "#64748b", fontSize: 12.5, margin: "6px 0 0" }}>
        Holding until condition{" "}
        <strong style={{ fontFamily: "ui-monospace, Menlo, monospace" }}>{condition}</strong>{" "}
        is satisfied — the workflow continues automatically when it does (re-checked on the schedule).
      </p>
      {Boolean(devSweep) && (
        <div style={{ marginTop: 14 }}>
          <button style={{ ...smallBtn, opacity: checking ? 0.5 : 1 }}
                  disabled={checking} onClick={() => void recheck()}>
            {checking ? "Checking…" : "Check now (dev)"}
          </button>
          {note && <span style={{ marginLeft: 10, fontSize: 12.5, color: "#475569" }}>{note}</span>}
        </div>
      )}
    </Shell>
  );
}

// ---- CALL (sub-workflow children) --------------------------------------------
const CHILD_PILL: Record<string, React.CSSProperties> = {
  active: pill("#dbeafe", "#1d4ed8"),
  completed: pill("#dcfce7", "#15803d"),
  cancelled: pill("#f1f5f9", "#64748b"),
};

export function CallStep({ step, instance, onReload }: StepProps) {
  const [children, setChildren] = React.useState<ChildInstance[] | null>(null);
  const active = instance.status === "active";

  const refresh = React.useCallback(async () => {
    try { setChildren(await workflowApi.getChildren(instance.id)); } catch { /* transient */ }
  }, [instance.id]);
  React.useEffect(() => {
    void refresh();
    if (!active) return;
    const t = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(t);
  }, [refresh, active]);

  const mine = (children ?? []).filter((c) => !c.parent_step_id || c.parent_step_id === step.id);
  const calls = (instance.context as Record<string, unknown>)?._calls as
    | Record<string, { expected?: number; done?: Record<string, unknown> }> | undefined;
  const expected = Number(calls?.[step.id]?.expected ?? mine.length);
  const doneCount = Object.keys(calls?.[step.id]?.done ?? {}).length;

  // When enough children completed, the parent advances server-side — reload.
  const movedRef = React.useRef(false);
  React.useEffect(() => {
    const completed = mine.filter((c) => c.status === "completed").length;
    if (active && completed > doneCount && !movedRef.current) {
      movedRef.current = true;
      void onReload?.();
    }
  }, [mine, doneCount, active, onReload]);

  return (
    <Shell step={step}>
      <p style={{ color: "#475569", margin: 0, fontSize: 14 }}>
        Waiting for sub-workflows — {doneCount} of {expected} complete.
      </p>
      {children === null ? (
        <p style={{ color: "#94a3b8", fontSize: 13 }}>Loading children…</p>
      ) : mine.length === 0 ? (
        <p style={{ color: "#94a3b8", fontSize: 13 }}>No child workflows yet.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "10px 0 0" }}>
          {mine.map((c) => (
            <li key={c.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0",
                                    borderTop: "1px solid #f1f5f9" }}>
              <a href={`/workflows/instances/${c.id}`} target="_blank" rel="noopener noreferrer"
                 style={{ color: "#4f46e5", fontWeight: 600, fontSize: 13.5, textDecoration: "none" }}>
                {c.definition_key} #{c.id} ↗
              </a>
              <span style={{ flex: 1, fontSize: 12.5, color: "#64748b" }}>
                {c.current_step ? `at ${c.current_step}` : ""}
              </span>
              <span style={CHILD_PILL[c.status] ?? CHILD_PILL.active}>{c.status}</span>
            </li>
          ))}
        </ul>
      )}
      <button style={{ ...smallBtn, marginTop: 12 }} onClick={() => void refresh()}>Refresh</button>
    </Shell>
  );
}
