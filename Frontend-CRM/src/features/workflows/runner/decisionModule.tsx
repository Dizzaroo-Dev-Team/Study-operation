// runner/decisionModule.tsx
// Module "decision": when the engine PARKS at a decision step (its branch variable
// isn't set yet), ASK the owner the question and route on the answer — instead of
// the engine silently taking the default branch (which left the other branch
// unreachable from the UI).
//
// GENERAL for ANY decision variable in ANY workflow. Nothing here is CRO/IRB/budget-
// specific: the question, the variable, and the options are all DERIVED from the
// step's own definition —
//   * the variable      = the field(s) the step's transition conditions read,
//   * the question text  = that variable's context_schema label (else the step name),
//   * the input/options  = the variable's declared type (boolean -> Yes/No,
//                          select -> its options, number/text/date -> an input),
//                          with the Yes/No / branch labels taken from the transitions.
//
// On submit it sends DECIDE_TOKEN ("__decide__") + { <field>: <value> } as the
// payload; the backend engine merges the value into context and routes via its
// existing condition logic (_next_auto), so the engine stays the state machine.

import React from "react";
import {
  registerStepModule, ownsAgreement, type StepModuleContext,
} from "./modules";
import type { Clause, Condition, ContextVariable, Transition } from "../types";

// Must match engine.DECIDE_TOKEN.
const DECIDE_TOKEN = "__decide__";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const card: React.CSSProperties = { border: "1px solid #e2e8f0", borderRadius: 12, padding: 20, background: "#fff", maxWidth: "100%" };
const optBtn: React.CSSProperties = {
  padding: "10px 18px", borderRadius: 10, fontSize: 14, fontWeight: 600,
  border: "1px solid #c7d2fe", background: "#eef2ff", color: "#3730a3", cursor: "pointer",
};

// ── Derivation helpers (pure) ────────────────────────────────────────────────
// Collect the field names a condition tree reads (mirrors the backend's
// referenced_fields). Presence ops (exists/not_exists) are skipped — those branch
// on absence and aren't a value to ask for.
function fieldsOfCondition(cond?: Condition | Clause | null): string[] {
  if (!cond) return [];
  const c = cond as Clause;
  if (typeof (c as any).field === "string") {
    return c.op === "exists" || c.op === "not_exists" ? [] : [c.field];
  }
  const group = cond as Condition;
  const out: string[] = [];
  for (const node of [...(group.all ?? []), ...(group.any ?? [])]) out.push(...fieldsOfCondition(node));
  return out;
}

// The single decision variable this step branches on (the first field referenced
// by its conditional transitions). Returns null for a pure pass-through decision.
function decisionField(transitions: Transition[]): string | null {
  for (const t of transitions) {
    if (t.action === "auto" && t.condition) {
      const f = fieldsOfCondition(t.condition);
      if (f.length) return f[0];
    }
  }
  return null;
}

type Option = { label: string; value: unknown };

// The first clause that reads `field` directly on a transition's condition (so we
// can label Yes/No from the transition that tests is_true / is_false / eq).
function directClause(t: Transition, field: string): Clause | null {
  const cond = t.condition;
  if (!cond) return null;
  const nodes = [...((cond as Condition).all ?? []), ...((cond as Condition).any ?? [])];
  for (const n of nodes) {
    const c = n as Clause;
    if (typeof c.field === "string" && c.field === field) return c;
  }
  return null;
}

// Build the answer options from the variable's declared TYPE plus the transition
// labels. Fully general; falls back to inferring from the operators when the
// variable isn't declared in context_schema.
function buildOptions(field: string, transitions: Transition[], variable?: ContextVariable): Option[] {
  const conditional = transitions.filter((t) => t.action === "auto" && t.condition);
  const fallback = transitions.find((t) => t.action === "auto" && !t.condition);

  // SELECT — one button per declared option (value routes via `eq`).
  if (variable?.type === "select" && variable.options?.length) {
    return variable.options.map((o) => ({ label: o, value: o }));
  }

  // Infer whether this is a boolean decision: from the declared type, or from any
  // transition clause using is_true / is_false on the field.
  const isBoolean =
    variable?.type === "boolean" ||
    conditional.some((t) => {
      const c = directClause(t, field);
      return c?.op === "is_true" || c?.op === "is_false";
    });

  if (isBoolean) {
    // Label the Yes/No buttons from the matching transitions when possible.
    const trueT = conditional.find((t) => directClause(t, field)?.op === "is_true");
    const falseT =
      conditional.find((t) => directClause(t, field)?.op === "is_false") ?? fallback;
    return [
      { label: trueT?.label || "Yes", value: true },
      { label: falseT?.label || "No", value: false },
    ];
  }

  // eq-enumerated decision with no declared select options: one button per eq value.
  const eqOpts: Option[] = [];
  for (const t of conditional) {
    const c = directClause(t, field);
    if (c?.op === "eq" && c.value !== undefined && c.value !== null) {
      eqOpts.push({ label: t.label || String(c.value), value: c.value });
    }
  }
  if (eqOpts.length) return eqOpts;

  // number / text / date (and comparison decisions like budget > 50k) -> free input.
  return [];
}

function DecisionPanel({ ctx }: { ctx: StepModuleContext }) {
  const { step, contextSchema, subjectRef } = ctx;
  const field = decisionField(step.transitions);
  const variable = field ? contextSchema.find((v) => v.key === field) : undefined;
  const options = field ? buildOptions(field, step.transitions, variable) : [];
  const question = variable?.label || step.name || "Make a decision";

  // The engine offers a synthetic "decide" action only to the decision-maker.
  const canDecideEngine = ctx.actions.some((a) => a.action === "decide");
  const hasAssignee = Boolean(step.assignee?.value);
  const isSandbox = !subjectRef || !UUID_RE.test(subjectRef);

  // Creator-owns by default: when the step has no explicit assignee and this is a
  // real agreement, only the owner decides. With an assignee, the engine already
  // gated it. Sandbox (no agreement) is open for dev walkthroughs.
  const [isOwner, setIsOwner] = React.useState(false);
  React.useEffect(() => {
    if (!isSandbox && subjectRef) ownsAgreement(subjectRef).then(setIsOwner);
  }, [subjectRef, isSandbox]);

  const canDecide = canDecideEngine && (hasAssignee || isOwner || isSandbox);

  // Free-input (number/text/date) state.
  const inputType = variable?.type === "number" ? "number" : variable?.type === "date" ? "date" : "text";
  const [raw, setRaw] = React.useState("");

  const submit = (value: unknown) => {
    if (!field) return;
    ctx.onComplete(DECIDE_TOKEN, { [field]: value });
  };
  const submitInput = () => {
    if (raw.trim() === "") return;
    submit(variable?.type === "number" ? Number(raw) : raw);
  };

  return (
    <div style={card}>
      <h3 style={{ marginTop: 0 }}>{step.name}</h3>
      {step.description && <p style={{ color: "#64748b", marginTop: 0 }}>{step.description}</p>}

      <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 10, padding: 16, marginTop: 8 }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: "#0f172a", marginBottom: 12 }}>{question}</div>

        {!field ? (
          <p style={{ color: "#94a3b8", fontSize: 13 }}>
            This decision has no input to collect — it routes automatically.
          </p>
        ) : !canDecide ? (
          <p style={{ color: "#94a3b8", fontSize: 13 }}>
            {canDecideEngine
              ? "Only the owner can answer this decision."
              : "Waiting — you don’t make this decision."}
          </p>
        ) : options.length > 0 ? (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {options.map((o, i) => (
              <button key={i} style={optBtn} disabled={ctx.busy} onClick={() => submit(o.value)}>
                {o.label}
              </button>
            ))}
          </div>
        ) : (
          // Free-value decision (e.g. "budget over 50k?" branches on a number) — the
          // owner enters the value and the engine routes it through its conditions.
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <input
              type={inputType}
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              placeholder={`Enter ${(variable?.label || field).toLowerCase()}`}
              style={{ padding: "8px 10px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, minWidth: 220 }}
            />
            <button style={optBtn} disabled={ctx.busy || raw.trim() === ""} onClick={submitInput}>
              Continue
            </button>
          </div>
        )}
      </div>

      <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 10 }}>
        Your answer sets <code>{field ?? "—"}</code> and the workflow continues on the matching branch.
      </p>
    </div>
  );
}

registerStepModule({
  key: "decision",
  // Default gate: creator-owns (the engine additionally enforces an explicit
  // assignee, if the step sets one).
  canAct: (ctx) => ownsAgreement(ctx.subjectRef),
  render: (ctx) => <DecisionPanel ctx={ctx} />,
});
