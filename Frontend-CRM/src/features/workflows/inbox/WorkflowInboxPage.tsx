// inbox/WorkflowInboxPage.tsx
// The TASK INBOX: every open workflow work item addressed to me, across ALL
// instances (GET /workflows/tasks). Claim and reassign inline; clicking a task
// opens that instance's runner, which renders the task's step panel.
// Route: /workflows/inbox (see App.tsx). Styling matches the runner's clean
// card language (see runner/steps/common.tsx ui).

import React from "react";
import { useNavigate } from "react-router-dom";
import { workflowApi } from "../api";
import type { WorkflowTask } from "../types";

const card: React.CSSProperties = {
  background: "#fff", border: "1px solid #e6eaf0", borderRadius: 12,
  boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
};
const chip = (bg: string, fg: string): React.CSSProperties => ({
  fontSize: 11, fontWeight: 700, letterSpacing: 0.3, textTransform: "uppercase",
  background: bg, color: fg, borderRadius: 999, padding: "2px 10px",
});
const btn: React.CSSProperties = {
  padding: "6px 12px", borderRadius: 8, border: "1px solid #cbd5e1",
  background: "#fff", color: "#334155", cursor: "pointer", fontWeight: 600, fontSize: 13,
};

const STATUS_STYLE: Record<string, React.CSSProperties> = {
  open: chip("#eef2ff", "#4f46e5"),
  claimed: chip("#fef9c3", "#a16207"),
  completed: chip("#dcfce7", "#15803d"),
  cancelled: chip("#f1f5f9", "#64748b"),
  expired: chip("#fee2e2", "#b91c1c"),
};

function ReassignControl({ task, onDone }: { task: WorkflowTask; onDone: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [userId, setUserId] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");

  if (!open) {
    return (
      <button style={btn} onClick={(e) => { e.stopPropagation(); setOpen(true); }}>
        Reassign
      </button>
    );
  }
  const submit = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!userId.trim()) return;
    setBusy(true);
    setErr("");
    try {
      await workflowApi.reassignTask(task.id, userId.trim());
      setOpen(false);
      setUserId("");
      onDone();
    } catch (ex: unknown) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  };
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
      <input
        value={userId}
        onChange={(e) => setUserId(e.target.value)}
        placeholder="user id / email"
        style={{ border: "1px solid #cbd5e1", borderRadius: 8, padding: "5px 8px", fontSize: 13, width: 170 }}
      />
      <button style={{ ...btn, background: "#4f46e5", color: "#fff", border: "none", opacity: busy || !userId.trim() ? 0.5 : 1 }}
              disabled={busy || !userId.trim()} onClick={submit}>
        {busy ? "…" : "Move"}
      </button>
      <button style={btn} onClick={(e) => { e.stopPropagation(); setOpen(false); setErr(""); }}>✕</button>
      {err && <span style={{ color: "#b91c1c", fontSize: 12 }}>{err}</span>}
    </span>
  );
}

export default function WorkflowInboxPage() {
  const navigate = useNavigate();
  const [tasks, setTasks] = React.useState<WorkflowTask[] | null>(null);
  const [status, setStatus] = React.useState<"open" | "completed" | "cancelled">("open");
  const [error, setError] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<number | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      setTasks(await workflowApi.tasks(status));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setTasks([]);
    }
  }, [status]);

  React.useEffect(() => { void load(); }, [load]);

  const claim = async (t: WorkflowTask) => {
    setBusyId(t.id);
    try {
      await workflowApi.claimTask(t.id);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const openTask = (t: WorkflowTask) => navigate(`/workflows/instances/${t.instance_id}`);

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 24px",
                    borderBottom: "1px solid #e2e8f0", background: "#fff" }}
           data-testid="workflow-inbox-header">
        <strong style={{ color: "#4f46e5", fontSize: 15 }}>Workflow Tasks</strong>
        <span style={{ fontSize: 12, color: "#94a3b8" }}>my open steps across all instances</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          {(["open", "completed", "cancelled"] as const).map((s) => (
            <button key={s} onClick={() => setStatus(s)}
                    style={{ ...btn, background: status === s ? "#eef2ff" : "#fff",
                             borderColor: status === s ? "#c7d2fe" : "#cbd5e1",
                             color: status === s ? "#4f46e5" : "#334155", textTransform: "capitalize" }}>
              {s}
            </button>
          ))}
          <button style={btn} onClick={() => void load()}>Refresh</button>
          <button style={btn} onClick={() => navigate("/")}>← Back to CRM</button>
        </div>
      </div>

      <div style={{ maxWidth: 1080, margin: "24px auto", padding: "0 16px" }} data-testid="workflow-inbox-list">
        {error && (
          <div style={{ background: "#fef2f2", color: "#b91c1c", border: "1px solid #fecaca",
                        borderRadius: 10, padding: "10px 14px", marginBottom: 16, fontSize: 13 }}>
            {error}
          </div>
        )}

        {tasks === null ? (
          <p style={{ color: "#64748b" }}>Loading…</p>
        ) : tasks.length === 0 ? (
          <div style={{ ...card, padding: 32, textAlign: "center", color: "#64748b" }}>
            No {status} workflow tasks for you right now.
          </div>
        ) : (
          <div style={card}>
            {tasks.map((t, i) => (
              <div key={t.id}
                   onClick={() => openTask(t)}
                   style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px",
                            borderTop: i === 0 ? "none" : "1px solid #eef2f7", cursor: "pointer" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, color: "#0f172a", fontSize: 14 }}>{t.name}</div>
                  <div style={{ fontSize: 12, color: "#64748b", marginTop: 2, display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <span>{t.definition_key}</span>
                    {t.subject_ref && (
                      <span title={t.subject_ref}
                            style={{ fontFamily: "ui-monospace, Menlo, monospace", background: "#eef2f7",
                                     borderRadius: 6, padding: "0 6px", maxWidth: 200, overflow: "hidden",
                                     textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {t.subject_ref}
                      </span>
                    )}
                    <span>step: {t.step_id}{t.slot_id ? ` · ${t.slot_id}` : ""}</span>
                    {t.due_at && <span style={{ color: "#b45309" }}>due {new Date(t.due_at).toLocaleString()}</span>}
                    {t.claimed_by && <span>claimed by {t.claimed_by}</span>}
                  </div>
                </div>
                <span style={STATUS_STYLE[t.status] ?? STATUS_STYLE.open}>{t.status}</span>
                {t.status === "open" && (
                  <button style={{ ...btn, opacity: busyId === t.id ? 0.5 : 1 }} disabled={busyId === t.id}
                          onClick={(e) => { e.stopPropagation(); void claim(t); }}>
                    {busyId === t.id ? "…" : "Claim"}
                  </button>
                )}
                {(t.status === "open" || t.status === "claimed") && (
                  <ReassignControl task={t} onDone={() => void load()} />
                )}
                <span style={{ color: "#94a3b8", fontSize: 18 }}>›</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
