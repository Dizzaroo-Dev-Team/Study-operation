// runner/WorkflowStepper.tsx
// A VERTICAL step timeline rendered ENTIRELY from the workflow definition +
// instance: steps top-to-bottom with a connector rail, ✓ for done, a prominent
// highlighted CURRENT step, and dim upcoming steps. Decision (auto) steps render
// subtly since users never act on them. Branch-aware: once a decision resolves, the
// steps reachable only via the untaken branch are hidden (computeVisibleSteps).
// Zero per-doc-type code. (Display only — the order/state/visibility logic is
// unchanged; only the arrangement is vertical.)

import type { Step, WorkflowDefinitionBody, WorkflowInstance } from "../types";
import { buildTopoOrder, computeStepStates, computeVisibleSteps, stepStateAt, buildFlowOrder, type StepState } from "./flow";

// Short human tag per step type for the line (purely cosmetic).
const TYPE_TAG: Record<string, string> = {
  form: "form",
  approval: "review",
  signature: "sign",
  parallel: "parallel",
  ordered_signing: "signing",
  broadcast: "broadcast",
  decision: "auto",
  terminal: "end",
};

export function WorkflowStepper({
  body,
  instance,
  visited,
}: {
  body: WorkflowDefinitionBody;
  instance: WorkflowInstance;
  /** Steps the engine has actually entered (from the audit). When provided, step
   *  state reflects real progress; ordering is topological either way. */
  visited?: Set<string>;
}) {
  // Topological order so a convergence node renders AFTER all its predecessors
  // (not where a BFS first reached it). Fall back to BFS only if topo yields nothing.
  const topo = buildTopoOrder(body);
  void buildFlowOrder; // retained export for other callers / tests
  const byId = new Map(body.steps.map((s) => [s.id, s]));
  const states = visited ? computeStepStates(body, instance, visited) : null;
  // Branch-aware visibility: once a decision has resolved, hide the steps reachable
  // ONLY via the branch(es) not taken. Only active when `visited` (the audit set) is
  // provided — i.e. in the unified runner — so other callers are unaffected.
  const visible = visited ? computeVisibleSteps(body, instance, visited) : null;
  const order = visible ? topo.filter((id) => visible.has(id)) : topo;
  const currentIndex = order.indexOf(instance.current_step ?? "");

  return (
    <div
      style={{
        padding: "14px 16px 8px",
        border: "1px solid #e6eaf0",
        borderRadius: 12,
        background: "#fff",
        boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
        maxHeight: "calc(100vh - 150px)",
        overflowY: "auto",
      }}
    >
      <h4 style={{ margin: "0 0 12px", fontSize: 12, fontWeight: 700, letterSpacing: 0.4, textTransform: "uppercase", color: "#64748b" }}>
        Steps
      </h4>
      <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {order.map((id, i) => {
          const step = byId.get(id);
          if (!step) return null;
          const state = states ? (states.get(id) ?? "upcoming") : stepStateAt(i, currentIndex, instance.status);
          return <StepItem key={id} step={step} state={state} index={i} isLast={i === order.length - 1} />;
        })}
      </ol>
    </div>
  );
}

const PALETTE: Record<StepState, { bg: string; fg: string; ring: string }> = {
  done: { bg: "#ecfdf3", fg: "#15803d", ring: "#22c55e" },
  current: { bg: "#eef2ff", fg: "#3730a3", ring: "#4f46e5" },
  upcoming: { bg: "#f8fafc", fg: "#94a3b8", ring: "#e2e8f0" },
};

// One row of the vertical timeline: a node on the connector rail + the step label.
function StepItem({ step, state, index, isLast }: { step: Step; state: StepState; index: number; isLast: boolean }) {
  const subtle = step.type === "decision"; // auto steps: users never act here
  const c = PALETTE[state];
  const isCurrent = state === "current";
  const badgeBg = state === "upcoming" ? "#cbd5e1" : c.ring;
  return (
    <li
      title={`${step.name} · ${step.type}`}
      style={{ position: "relative", display: "flex", gap: 11, paddingBottom: isLast ? 2 : 14 }}
    >
      {/* connector rail running down to the next node */}
      {!isLast && (
        <span style={{ position: "absolute", left: 11, top: 24, bottom: 0, width: 2, background: state === "done" ? "#bbf7d0" : "#eef2f7" }} />
      )}
      {/* node: ✓ when done, the step number otherwise; current gets a ring */}
      <span
        style={{
          position: "relative", zIndex: 1, flexShrink: 0,
          width: 24, height: 24, borderRadius: 999,
          background: badgeBg, color: "#fff",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 700,
          border: subtle ? "2px dashed #fff" : "2px solid #fff",
          boxShadow: isCurrent ? `0 0 0 3px ${c.ring}33` : "0 0 0 1px #e6eaf0",
        }}
      >
        {state === "done" ? "✓" : index + 1}
      </span>
      {/* label — the CURRENT step is highlighted as a filled chip */}
      <span
        style={{
          flex: 1, minWidth: 0, alignSelf: "flex-start",
          padding: isCurrent ? "5px 10px" : "3px 0",
          borderRadius: 8,
          background: isCurrent ? c.bg : "transparent",
          border: `1px solid ${isCurrent ? `${c.ring}55` : "transparent"}`,
        }}
      >
        <span style={{ display: "block", fontSize: 13, fontWeight: isCurrent ? 700 : 600, lineHeight: 1.3, color: state === "upcoming" ? "#64748b" : c.fg, overflowWrap: "anywhere" }}>
          {step.name}
        </span>
        {/* Show the step's MODULE (what the runner actually invokes) when set, so
            two approval-typed steps using different modules (approval vs notify)
            don't both read "review". Falls back to the type tag when no module. */}
        <span style={{ display: "block", marginTop: 1, fontSize: 10, fontWeight: 600, letterSpacing: 0.3, textTransform: "uppercase", color: c.fg, opacity: 0.6 }}>
          {step.module ?? TYPE_TAG[step.type] ?? step.type}
        </span>
      </span>
    </li>
  );
}
