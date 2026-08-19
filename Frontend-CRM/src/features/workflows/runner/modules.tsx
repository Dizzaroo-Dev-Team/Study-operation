// runner/modules.tsx
// THE MODULE LAYER (skeleton). One contract every capability module implements, a
// registry the runner looks up by `step.module`, and the creator-owns permission
// primitive. No real modules are registered yet — the registry is EMPTY, so the
// runner falls back to its generic step rendering and nothing changes. Adding a
// real module later is ONE call: registerStepModule({ key: "signing", render, canAct }).
//
// Architecture invariants this preserves:
//   * The engine stays the pure state machine (order, rework, audit, advance). It
//     NEVER calls a module.
//   * A module renders the real UI, calls the REAL underlying service, and reports
//     COMPLETION by calling ctx.onComplete(transitionId) — the existing engine
//     advance path — ONLY on real completion (never a bare button).
//   * The runner reads step.module, looks it up here, and renders/invokes via the
//     contract; unknown/unset module -> generic fallback.

import React from "react";
import { workflowApi } from "../api";
import type { AvailableAction, ContextVariable, Step, WorkflowInstance } from "../types";

// What every module receives to do its job.
export interface StepModuleContext {
  instance: WorkflowInstance;
  step: Step;
  /** Engine transitions available to the current user on this step. */
  actions: AvailableAction[];
  /** The workflow's declared decision/form variables (definition.context_schema).
   *  The decision module reads a variable's type/label/options from here to render
   *  the right question + inputs. Empty array when the definition declares none. */
  contextSchema: ContextVariable[];
  /** The domain subject — the agreement id (instance.subject_ref). */
  subjectRef: string | null;
  busy: boolean;
  /** Whether real embeds (OnlyOffice / signing) are enabled for this run. */
  embedDocs: boolean;
  /** DEV-only (backend WORKFLOW_DEV_SWEEP): enables the manual sweep trigger and
   *  the wait_message test-event-deliver button. Prod uses the Celery beat → false. */
  devSweep: boolean;
  /** Advance the engine. Call ONLY after the underlying real action completes
   *  (this is the existing engine-advance path, workflowApi.act under the hood). */
  onComplete: (transitionId: string, payload?: Record<string, unknown>, comment?: string) => void;
  /** Re-pull the parent runner's state (instance + available actions + audit) WITHOUT
   *  a page reload. Modules' "Refresh" buttons call this so the stepper updates and —
   *  because a server-side change bumps instance.updated_at — the embedded document
   *  view remounts to the latest version. */
  onReload?: () => void | Promise<void>;
}

// The one interface every capability module implements.
export interface StepModule {
  /** Registry key — matches step.module (e.g. "signing", "review", "approval"). */
  key: string;
  /** Render the real UI for this step. The UI calls the real service and reports
   *  completion via ctx.onComplete. Most modules implement this. */
  render: (ctx: StepModuleContext) => React.ReactNode;
  /** Who-can-act gate. Default convention: creator-owns-send (see ownsAgreement).
   *  Modules use this to enable/disable their send/receive controls. */
  canAct?: (ctx: StepModuleContext) => boolean | Promise<boolean>;
  /** Optional headless action for no-UI capabilities (e.g. notify/broadcast):
   *  the runner may invoke this directly; it calls the real service then onComplete. */
  invoke?: (ctx: StepModuleContext) => Promise<void>;
}

// ── Registry ────────────────────────────────────────────────────────────────
// Intentionally EMPTY for now. The runner falls back to generic rendering for any
// step whose module is unset or not registered, so nothing breaks.
const MODULE_REGISTRY: Record<string, StepModule> = {};

/** Register a capability module. One call = one new wired capability. */
export function registerStepModule(mod: StepModule): void {
  MODULE_REGISTRY[mod.key] = mod;
}
/** Look up the module for a step (undefined -> runner uses generic fallback). */
export function getStepModule(key?: string | null): StepModule | undefined {
  return key ? MODULE_REGISTRY[key] : undefined;
}
/** Registered module keys (for diagnostics / dev tooling). */
export function listStepModules(): string[] {
  return Object.keys(MODULE_REGISTRY);
}

// ── Host: render a registered module via the contract ─────────────────────────
export function StepModuleHost({ mod, ctx }: { mod: StepModule; ctx: StepModuleContext }) {
  return <>{mod.render(ctx)}</>;
}

// Shared action row: render the engine's available transitions as buttons that call
// ctx.onComplete (the real engine-advance path). Modules use this so a step can
// advance after the module's real work — never a bare advance with no engine action.
export function ModuleActions({ ctx }: { ctx: StepModuleContext }) {
  // A transition authored with requires_comment (e.g. reject / send_back) MUST carry a
  // comment, or the engine rejects the action with 409 "A comment is required for this
  // action". Collect one and pass it through onComplete (which forwards it to the act
  // endpoint). Without this, clicking such an action always fails.
  const [comment, setComment] = React.useState("");
  if (!ctx.actions.length) {
    return <p style={{ color: "#94a3b8", marginTop: 12, fontSize: 13 }}>No action available on this step for you.</p>;
  }
  const needsComment = ctx.actions.some((a) => a.requires_comment);
  return (
    <div style={{ marginTop: 14 }}>
      {needsComment && (
        <textarea
          placeholder="Comment (required for reject / send-back)…"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          style={{
            width: "100%", minHeight: 64, padding: "9px 11px", border: "1px solid #cbd5e1",
            borderRadius: 8, fontSize: 14, boxSizing: "border-box", color: "#0f172a",
            lineHeight: 1.5, marginBottom: 8,
          }}
        />
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {ctx.actions.map((a) => {
          const negative = a.action === "reject" || a.action === "send_back";
          return (
            <button
              key={a.transition_id}
              disabled={ctx.busy || (a.requires_comment && !comment.trim())}
              onClick={() => ctx.onComplete(a.transition_id, undefined, comment.trim() || undefined)}
              style={{
                padding: "9px 16px",
                background: negative ? "#fff" : "#4f46e5",
                color: negative ? "#dc2626" : "#fff",
                border: negative ? "1px solid #fca5a5" : "none",
                borderRadius: 8, fontWeight: 600, fontSize: 14, cursor: "pointer",
                boxShadow: negative ? "none" : "0 1px 2px rgba(79,70,229,0.18)",
              }}
            >
              {a.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Permission primitive: creator-owns-send ───────────────────────────────────
// "Is the current user the creator/owner of this agreement?" Reuses the existing
// Agreement.created_by via GET /workflows/permits/owner. Modules call this to gate
// send/receive actions. Fail-safe FALSE (default-deny) on error / missing subject.
export async function ownsAgreement(subjectRef: string | null): Promise<boolean> {
  if (!subjectRef) return false;
  try {
    const r = await workflowApi.checkOwner(subjectRef);
    return Boolean(r?.is_owner);
  } catch {
    return false;
  }
}
