// runner/approvalModule.tsx
// Module "approval": a generic approve/reject step. Renders the engine's available
// transitions (approve / reject / send-back) and advances on the REAL chosen action
// via ctx.onComplete — never a fake advance. Replaces bespoke per-type approvals
// (the old ones stay as fallback). Reuses the engine's approval step + ModuleActions.

import React from "react";
import { registerStepModule, ModuleActions, ownsAgreement, type StepModuleContext } from "./modules";
import { DocumentViewer } from "./DocumentViewer";

const card: React.CSSProperties = { border: "1px solid #e6eaf0", borderRadius: 12, padding: 20, background: "#fff", maxWidth: "100%", margin: "12px 0", boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)" };

// An approval step is, by definition, an approve / reject / send-back checkpoint.
// We filter the step's available actions to exactly those standard verbs so the
// panel stays a clean approve/reject/send-back UI even if a definition declares
// extra transitions — the real approve/reject/send-back stay wired unchanged.
const APPROVAL_VERBS = new Set(["approve", "reject", "send_back"]);

function ApprovalModulePanel({ ctx }: { ctx: StepModuleContext }) {
  const approvalActions = ctx.actions.filter((a) => APPROVAL_VERBS.has(a.action));
  return (
    <div style={card}>
      <h3 style={{ marginTop: 0, marginBottom: 4, fontSize: 16, fontWeight: 700, color: "#0f172a" }}>{ctx.step.name}</h3>
      {ctx.step.description && <p style={{ color: "#64748b", marginTop: 0, fontSize: 13, lineHeight: 1.5 }}>{ctx.step.description}</p>}
      {/* Owner checkpoint: show the current/latest document so the owner sees what
          they're approving (e.g. the doc as it came back). */}
      <DocumentViewer subjectRef={ctx.subjectRef} instanceId={ctx.instance.id} stepId={ctx.step.id}
                      canEdit={false} refreshKey={ctx.instance.updated_at} height="60vh" />
      <p style={{ color: "#475569" }}>Review and choose an action.</p>
      {/* Only the standard approve/reject/send-back verbs — never stray transitions. */}
      <ModuleActions ctx={{ ...ctx, actions: approvalActions }} />
    </div>
  );
}

registerStepModule({
  key: "approval",
  // Default: creator-owns (owner's approval). The engine still gates the actual
  // transition via available_actions, so this is the module-level convenience gate.
  canAct: (ctx) => ownsAgreement(ctx.subjectRef),
  render: (ctx) => <ApprovalModulePanel ctx={ctx} />,
});
