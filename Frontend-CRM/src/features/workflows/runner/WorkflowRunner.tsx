// runner/WorkflowRunner.tsx
// Drives a single running instance. It is completely document-agnostic: it asks
// the backend for the current step + available actions and renders the matching
// generic component. CTA, CDA, and any future type all run through this one view.

import React from "react";
import { workflowApi } from "../api";
import type { AuditEntry, AvailableAction, DefinitionVersion, Step, WorkflowInstance, WorkflowTimerRow } from "../types";
import { StepRenderer } from "./steps";
import { ui } from "./steps/common";
import { TimerChip } from "./steps/v2";
import { stepItems } from "./flow";
import "./runner.css"; // visual-only: hover/focus/disabled states scoped to .wf-runner
import { WorkflowStepper } from "./WorkflowStepper";
import { getStepModule, StepModuleHost } from "./modules";
import { DocumentViewer } from "./DocumentViewer";
import "./signingModule"; // side-effect: registers the "signing" capability module
import "./reviewModule"; // side-effect: registers the "review" capability module
import "./documentCreateModule"; // registers "document_create"
import "./approvalModule"; // registers "approval"
import "./notifyModule"; // registers "notify"
import "./broadcastModule"; // registers "broadcast"
import "./decisionModule"; // registers "decision" (ask-the-owner branch)
import "./discussionModule"; // registers "discussion" (tracked two-party exchange)

export function WorkflowRunner({ instanceId }: { instanceId: number }) {
  const [instance, setInstance] = React.useState<WorkflowInstance | null>(null);
  const [def, setDef] = React.useState<DefinitionVersion | null>(null);
  const [actions, setActions] = React.useState<AvailableAction[]>([]);
  const [audit, setAudit] = React.useState<AuditEntry[]>([]);
  // Armed boundary timers for this instance (the "fires in N min" chips).
  const [timers, setTimers] = React.useState<WorkflowTimerRow[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  // Layout-only: collapse the right-hand History rail to give the document/panel the
  // full width. Purely presentational (controls CSS); no effect on data or behavior.
  const [historyOpen, setHistoryOpen] = React.useState(true);
  // Document embeds (OnlyOffice) are part of the unified platform — always on. They
  // still only mount for a real agreement (canEmbed also checks the subject_ref).
  const embedDocs = true;
  // Dev-only controls (manual sweep trigger + test-event-deliver). Gated on the
  // backend WORKFLOW_DEV_SWEEP flag (prod uses the Celery beat → false).
  const [devSweep, setDevSweep] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    workflowApi
      .config()
      .then((c) => { if (alive) setDevSweep(Boolean(c?.dev_sweep)); })
      .catch(() => { /* leave false → prod beat owns sweeps */ });
    return () => { alive = false; };
  }, []);

  const load = React.useCallback(async () => {
    setError(null);
    const inst = await workflowApi.getInstance(instanceId);
    setInstance(inst);
    const [acts, aud, definition, activity] = await Promise.all([
      inst.status === "active" ? workflowApi.getActions(instanceId) : Promise.resolve([]),
      workflowApi.getAudit(instanceId),
      def ?? workflowApi.getDefinition(inst.definition_key, inst.definition_version),
      inst.status === "active"
        ? workflowApi.getActivity(instanceId).catch(() => null)
        : Promise.resolve(null),
    ]);
    setActions(acts);
    setAudit(aud);
    setDef(definition);
    setTimers(activity?.timers ?? []);
  }, [instanceId, def]);

  React.useEffect(() => {
    load().catch((e) => setError(String(e.message ?? e)));
  }, [load]);

  // Dev stacks run no celery beat: when an armed timer comes due, trigger the
  // (WORKFLOW_UNIFIED-gated) sweep so the escalation visibly fires, then reload.
  // Production runs the beat schedule; the catch keeps this harmless there.
  React.useEffect(() => {
    if (!devSweep || !instance || instance.status !== "active") return;
    const pending = timers.filter((t) => t.status === "pending");
    if (!pending.length) return;
    const tick = window.setInterval(async () => {
      const due = pending.some((t) => new Date(t.fire_at).getTime() <= Date.now());
      if (!due) return;
      try { await workflowApi.runSweeps(); } catch { /* beat's job in prod */ }
      await load().catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(tick);
  }, [devSweep, instance, timers, load]);

  // Auto-refresh: surface server-side workflow advances made by OTHER participants
  // (a reviewer approving / a signer completing on a separate session) without the
  // user clicking "Refresh Everything". Fully data-driven — no hardcoding on document
  // or workflow type, so it benefits every workflow.
  //   • Polls load() every 20s while the instance is active and the tab is visible.
  //   • Pauses while the tab is hidden; fires an eager refresh on window focus and on
  //     visibilitychange (tab returns to foreground).
  //   • The `running` guard avoids overlapping in-flight fetches; the interval and both
  //     listeners are always cleared on unmount.
  React.useEffect(() => {
    if (!instance || instance.status !== "active") return;
    const POLL_MS = 20_000;
    let running = false;
    const refresh = () => {
      if (running || document.hidden) return;
      running = true;
      load().catch(() => undefined).finally(() => { running = false; });
    };
    const timer = window.setInterval(refresh, POLL_MS);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [instance, load]);

  const handleAct = async (transitionId: string, payload?: Record<string, unknown>, comment?: string) => {
    setBusy(true);
    setError(null);
    try {
      await workflowApi.act(instanceId, transitionId, payload ?? {}, comment);
      await load();
    } catch (e: unknown) {
      // Prefer the backend's reason (e.g. "A comment is required for this action")
      // over axios's opaque "Request failed with status code 409".
      const detail = (e as any)?.response?.data?.detail;
      setError(typeof detail === "string" && detail ? detail : (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  // Steps the engine has ACTUALLY entered — from the audit trail's from/to steps.
  // Drives the stepper's done/current state (real progress, not line position).
  const visitedSteps = React.useMemo(() => {
    const v = new Set<string>();
    for (const e of audit) {
      if (e.from_step) v.add(e.from_step);
      if (e.to_step) v.add(e.to_step);
    }
    return v;
  }, [audit]);

  // If the initial load failed (instance or definition fetch), SURFACE the error
  // instead of sitting on "Loading…" forever — setInstance can run before a failing
  // getDefinition, leaving `def` null with the error otherwise never shown (the error
  // UI below sits past this guard).
  if (error && (!instance || !def)) {
    return (
      <div style={{ padding: 24, color: "#b91c1c" }}>
        Couldn’t load this workflow: {error}
        <button onClick={() => load().catch((e) => setError(String(e?.message ?? e)))}
                style={{ marginLeft: 12, padding: "4px 10px", border: "1px solid #fecaca", borderRadius: 8, background: "#fff", color: "#b91c1c", cursor: "pointer" }}>
          Retry
        </button>
      </div>
    );
  }
  if (!instance || !def) return <div style={{ padding: 24, color: "#64748b" }}>Loading…</div>;

  // ── ALL open steps, not just current_step ─────────────────────────────────
  // In token/gateway mode the engine parks MULTIPLE tokens at once and exposes
  // them in context["_tokens"]; the actions list is already the union across
  // them. Legacy single-token instances have no _tokens, so this reduces to
  // exactly [current_step] and nothing changes for existing flows.
  const tokenSteps = Array.isArray((instance.context as Record<string, unknown>)?._tokens)
    ? ((instance.context as Record<string, unknown>)._tokens as { step: string }[])
        .map((t) => t.step)
    : [];
  const openStepIds = tokenSteps.length
    ? Array.from(new Set(tokenSteps))
    : instance.current_step
      ? [instance.current_step]
      : [];
  const openSteps = openStepIds
    .map((sid) => def.body.steps.find((s) => s.id === sid))
    .filter((s): s is Step => Boolean(s));
  const step = openSteps[0];
  const multi = openSteps.length > 1;

  // Which of the (union) actions belong to one specific open step: vote tokens
  // ("<branch>:<verb>" / "<slot>:<verb>") match their macro step's items; the
  // decide token matches a parked decision; ordinary ids match the step's own
  // transition list.
  const actionsForStep = (s: Step): AvailableAction[] => {
    if (!multi) return actions;
    if (s.type === "parallel" || s.type === "ordered_signing") {
      const ids = new Set((stepItems(s) ?? []).map((it) => it.id));
      return actions.filter((a) => {
        const i = a.transition_id.lastIndexOf(":");
        return i > 0 && ids.has(a.transition_id.slice(0, i));
      });
    }
    if (s.type === "decision") return actions.filter((a) => a.transition_id === "__decide__");
    const tids = new Set(s.transitions.map((t) => t.id));
    return actions.filter((a) => tids.has(a.transition_id));
  };

  const statusColor =
    instance.status === "completed" ? "#16a34a" : instance.status === "cancelled" ? "#dc2626" : "#2563eb";

  // Pending boundary timer for one step (the armed indicator). The FIRED case
  // already shows in History — only armed/pending is chipped here.
  const pendingTimerFor = (stepId: string) =>
    timers.find((t) => t.step_id === stepId && t.status === "pending");

  // One panel per open step (registered module, or the generic fallback).
  const renderPanel = (s: Step) => {
    const moduleKey = s.module ?? (s.type === "decision" ? "decision" : undefined);
    const mod = getStepModule(moduleKey);
    const stepActions = actionsForStep(s);
    const armed = pendingTimerFor(s.id);
    const timerBar = armed ? (
      <div style={{ marginBottom: 10 }}>
        <TimerChip fireAt={armed.fire_at} />
      </div>
    ) : null;
    const panel = mod ? (
      <StepModuleHost
        mod={mod}
        ctx={{
          instance,
          step: s,
          actions: stepActions,
          contextSchema: def.body.context_schema ?? [],
          subjectRef: instance.subject_ref,
          busy,
          embedDocs,
          devSweep,
          onComplete: handleAct,
          onReload: load,
        }}
      />
    ) : (
      <>
        {s.module && (
          <div style={{ background: "#fffbeb", color: "#92400e", border: "1px solid #fde68a", borderRadius: 8, padding: "8px 12px", marginBottom: 12, fontSize: 13 }}>
            Module “{s.module}” is not registered yet — showing the generic step.
          </div>
        )}
        <StepRenderer
          step={s}
          instance={instance}
          actions={stepActions}
          busy={busy}
          onAct={handleAct}
          embedDocs={embedDocs}
          devSweep={devSweep}
          onReload={load}
        />
      </>
    );
    return (
      <React.Fragment key={s.id}>
        {timerBar}
        {panel}
      </React.Fragment>
    );
  };

  // Single open step → exactly the old layout. Multiple → one labelled panel
  // per parallel track, all actionable at the same time (the join still waits).
  const activePanel = multi ? (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ background: "#eff6ff", color: "#1d4ed8", border: "1px solid #bfdbfe", borderRadius: 10, padding: "8px 12px", fontSize: 13, fontWeight: 600 }}>
        {openSteps.length} parallel tracks are open — each can be completed independently.
      </div>
      {openSteps.map((s) => (
        <section key={s.id} style={{ border: "1px solid #dbe3ee", borderRadius: 14, padding: 12, background: "#fcfdff" }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", color: "#64748b", margin: "2px 4px 10px" }}>
            Track · {s.name}
          </div>
          {renderPanel(s)}
        </section>
      ))}
    </div>
  ) : step ? (
    renderPanel(step)
  ) : null;

  return (
    <div className="wf-runner" style={{ padding: 20, background: "#f8fafc", minHeight: "100%" }}>
      {/* ── ONE compact header row: title · subject · status ───────────────── */}
      <header style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#0f172a", letterSpacing: "-0.01em" }}>
          {def.body.name}
        </h2>
        {instance.subject_ref && (
          <span
            title={instance.subject_ref}
            style={{
              fontSize: 11.5, color: "#475569", background: "#eef2f7", border: "1px solid #e2e8f0",
              borderRadius: 6, padding: "2px 8px", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}
          >
            {instance.subject_ref}
          </span>
        )}
        <span
          style={{
            ...ui.badge, background: `${statusColor}14`, color: statusColor,
            border: `1px solid ${statusColor}33`, display: "inline-flex", alignItems: "center", gap: 6,
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: 999, background: statusColor, display: "inline-block" }} />
          {instance.status.toUpperCase()}
        </span>
        {step && (
          <span style={{ marginLeft: "auto", fontSize: 12, color: "#64748b" }}>
            {multi ? "Open steps: " : "Current step: "}
            <strong style={{ color: "#334155", fontWeight: 600 }}>
              {openSteps.map((s) => s.name).join(" · ")}
            </strong>
          </span>
        )}
      </header>

      {error && (
        <div style={{ background: "#fef2f2", color: "#b91c1c", padding: "10px 14px", borderRadius: 10, marginBottom: 16, border: "1px solid #fecaca", fontSize: 13, fontWeight: 500 }}>
          {error}
        </div>
      )}

      {/* ── Three regions: vertical timeline · wide main · collapsible history ── */}
      <div className={`wf-grid${historyOpen ? "" : " wf-history-collapsed"}`}>
        {/* LEFT — vertical step timeline (branch-aware hiding applies inside) */}
        <aside className="wf-timeline">
          <WorkflowStepper body={def.body} instance={instance} visited={visitedSteps} />
        </aside>

        {/* MAIN — the active step's panel + embedded document (the widest column) */}
        <main className="wf-main" style={{ minWidth: 0 }}>
          {activePanel}

          {/* End state: always show the FINAL/latest signed artifact at a terminal
              step or on completion (terminal steps carry no module). */}
          {(step?.type === "terminal" || instance.status === "completed") && (
            <DocumentViewer
              subjectRef={instance.subject_ref}
              instanceId={instance.id}
              stepId={`final-${step?.id ?? "end"}`}
              canEdit={false}
              refreshKey={instance.updated_at}
              height="68vh"
            />
          )}

          {instance.status === "active" && actions.length === 0 && step?.type !== "terminal" && (
            <p style={{ color: "#64748b", marginTop: 16, fontSize: 13, background: "#fff", border: "1px solid #e6eaf0", borderRadius: 10, padding: "10px 14px" }}>
              Waiting on another role to act — you don’t have an available action on this step.
            </p>
          )}
        </main>

        {/* RIGHT — History (collapsible to give the document full width) */}
        <aside className="wf-history-col">
          {historyOpen ? (
            <div
              style={{
                background: "#fff", border: "1px solid #e6eaf0", borderRadius: 12, padding: 16,
                boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
                maxHeight: "calc(100vh - 120px)", overflowY: "auto",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", marginBottom: 14 }}>
                <h4 style={{ margin: 0, fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", color: "#64748b" }}>
                  History
                </h4>
                <button
                  onClick={() => setHistoryOpen(false)}
                  title="Collapse history"
                  style={{ marginLeft: "auto", border: "1px solid #e2e8f0", background: "#fff", color: "#64748b", borderRadius: 8, padding: "2px 8px", fontSize: 13, cursor: "pointer", lineHeight: 1.4 }}
                >
                  ⟩
                </button>
              </div>
              {audit.length === 0 ? (
                <p style={{ fontSize: 13, color: "#94a3b8", margin: 0 }}>No activity yet.</p>
              ) : (
                <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {audit.map((e, i) => {
                    const isSystem = !e.actor;
                    const dot = e.action === "reject" || e.action === "declined" || e.action === "signing_declined"
                      ? "#dc2626"
                      : isSystem ? "#94a3b8" : "#4f46e5";
                    return (
                      <li key={e.id} style={{ position: "relative", paddingLeft: 18, paddingBottom: i === audit.length - 1 ? 0 : 16 }}>
                        {i !== audit.length - 1 && (
                          <span style={{ position: "absolute", left: 4, top: 14, bottom: 0, width: 2, background: "#eef2f7" }} />
                        )}
                        <span style={{ position: "absolute", left: 0, top: 4, width: 10, height: 10, borderRadius: 999, background: dot, border: "2px solid #fff", boxShadow: "0 0 0 1px #e6eaf0" }} />
                        <div style={{ fontSize: 13, fontWeight: 600, color: "#0f172a", textTransform: "capitalize" }}>
                          {e.action.replace(/_/g, " ")}
                        </div>
                        <div style={{ fontSize: 12, color: "#64748b", marginTop: 1 }}>
                          <span style={{ fontWeight: 600, color: isSystem ? "#94a3b8" : "#475569" }}>{e.actor ?? "system"}</span>
                          {" · "}{e.from_step ?? "—"} → {e.to_step ?? "—"}
                        </div>
                        {e.comment && (
                          <div style={{ fontSize: 12, color: "#475569", fontStyle: "italic", marginTop: 4, background: "#f8fafc", border: "1px solid #eef2f7", borderRadius: 8, padding: "6px 8px" }}>
                            “{e.comment}”
                          </div>
                        )}
                        <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 3 }}>{new Date(e.created_at).toLocaleString()}</div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>
          ) : (
            <button
              onClick={() => setHistoryOpen(true)}
              title="Show history"
              style={{
                width: "100%", background: "#fff", border: "1px solid #e6eaf0", borderRadius: 12,
                padding: "10px 6px", cursor: "pointer", color: "#64748b", fontSize: 11, fontWeight: 700,
                letterSpacing: 0.4, textTransform: "uppercase", writingMode: "vertical-rl",
                boxShadow: "0 1px 2px rgba(16,24,40,0.04)",
              }}
            >
              ⟨ History
            </button>
          )}
        </aside>
      </div>
    </div>
  );
}
