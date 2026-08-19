// runner/flow.test.ts
// Proves the runner UI is data-driven: the SAME pure helpers derive a correct
// stepper line + per-step state + branch lists for two completely different
// workflow shapes, with zero shape-specific code.

import { describe, it, expect } from "vitest";
import type { WorkflowDefinitionBody } from "../types";
import { buildFlowOrder, buildTopoOrder, computeStepStates, computeVisibleSteps, stepStateAt, stepItems, recordedBranches } from "./flow";

function inst(current: string, status: "active" | "completed" = "active") {
  return {
    id: 1, definition_key: "X", definition_version: 1, status,
    current_step: current, current_step_type: null, current_step_name: null,
    subject_ref: "x", created_at: "", updated_at: "", context: {},
  } as any;
}

// Shape A — the simple CDA: draft → review → sign → executed → closed.
const CDA: WorkflowDefinitionBody = {
  key: "CDA",
  name: "CDA",
  start_step: "draft",
  context_schema: [],
  steps: [
    { id: "draft", type: "form", name: "Draft", config: {}, transitions: [{ id: "s", to: "under_review", label: "Submit", action: "submit" }] },
    { id: "under_review", type: "approval", name: "Legal Review", config: {}, transitions: [
      { id: "a", to: "ready_for_signature", label: "Approve", action: "approve" },
      { id: "r", to: "draft", label: "Reject", action: "reject" }] },
    { id: "ready_for_signature", type: "approval", name: "Ready", config: {}, transitions: [{ id: "send", to: "sent_for_signature", label: "Send", action: "send" }] },
    { id: "sent_for_signature", type: "signature", name: "Signature", config: {}, transitions: [{ id: "sign", to: "executed", label: "Sign", action: "sign" }] },
    { id: "executed", type: "approval", name: "Executed", config: {}, transitions: [{ id: "c", to: "closed", label: "Close", action: "close" }] },
    { id: "closed", type: "terminal", name: "Closed", config: {}, transitions: [] },
  ],
};

// Shape B — a longer custom flow: draft → parallel review → ordered signing →
// broadcast → done. Different shape, different types, NO code changes.
const LONG: WorkflowDefinitionBody = {
  key: "DEMO_LONG",
  name: "Demo long",
  start_step: "draft",
  context_schema: [],
  steps: [
    { id: "draft", type: "form", name: "Draft", config: {}, transitions: [{ id: "s", to: "review", label: "Submit", action: "submit" }] },
    { id: "review", type: "parallel", name: "Parallel Review",
      config: { branches: [{ id: "legal", name: "Legal" }, { id: "financial", name: "Financial" }] },
      transitions: [{ id: "ok", to: "signing", label: "Both approved", action: "quorum_met" }, { id: "rwk", to: "draft", label: "Send back", action: "quorum_failed" }] },
    { id: "signing", type: "ordered_signing", name: "Ordered Signing",
      config: { signers: [{ id: "director", name: "Director" }, { id: "pi", name: "PI" }, { id: "vp", name: "VP" }] },
      transitions: [{ id: "as", to: "distribute", label: "All signed", action: "all_signed" }, { id: "dec", to: "draft", label: "Declined", action: "signing_declined" }] },
    { id: "distribute", type: "broadcast", name: "Distribute",
      config: { recipients: [{ id: "pi", name: "PI" }, { id: "crc", name: "CRC" }] },
      transitions: [{ id: "bd", to: "done", label: "Distributed", action: "broadcast_done" }] },
    { id: "done", type: "terminal", name: "Done", config: {}, transitions: [] },
  ],
};

describe("buildFlowOrder — different shapes produce different lines", () => {
  it("CDA line", () => {
    expect(buildFlowOrder(CDA)).toEqual([
      "draft", "under_review", "ready_for_signature", "sent_for_signature", "executed", "closed",
    ]);
  });
  it("LONG line", () => {
    expect(buildFlowOrder(LONG)).toEqual(["draft", "review", "signing", "distribute", "done"]);
  });
  it("loops do not duplicate nodes (reject→draft back-edge skipped)", () => {
    const order = buildFlowOrder(CDA);
    expect(order.filter((id) => id === "draft").length).toBe(1);
  });
});

describe("stepStateAt — completed / current / upcoming", () => {
  const order = buildFlowOrder(CDA);
  const ci = order.indexOf("ready_for_signature"); // current = index 2
  it("classifies relative to current", () => {
    expect(stepStateAt(0, ci, "active")).toBe("done");
    expect(stepStateAt(1, ci, "active")).toBe("done");
    expect(stepStateAt(2, ci, "active")).toBe("current");
    expect(stepStateAt(3, ci, "active")).toBe("upcoming");
  });
  it("completed instance marks everything done", () => {
    expect(stepStateAt(5, -1, "completed")).toBe("done");
  });
});

describe("stepItems — fan-out sub-items by type", () => {
  it("parallel → branches, ordered_signing → signers, broadcast → recipients", () => {
    const review = LONG.steps.find((s) => s.id === "review")!;
    const signing = LONG.steps.find((s) => s.id === "signing")!;
    const dist = LONG.steps.find((s) => s.id === "distribute")!;
    expect(stepItems(review)!.map((i) => i.id)).toEqual(["legal", "financial"]);
    expect(stepItems(signing)!.map((i) => i.id)).toEqual(["director", "pi", "vp"]);
    expect(stepItems(dist)!.map((i) => i.id)).toEqual(["pi", "crc"]);
    expect(stepItems(LONG.steps[0])).toBeNull(); // form has no sub-items
  });
});

// Shape C — a DIAMOND (branch + convergence): draft → gate → {CRO branch | Site
// branch}, both converging on a SHARED `vp` step → distribute → done. This is the
// CTA shape that exposed the stepper bug (vp reached by both branches).
const DIAMOND: WorkflowDefinitionBody = {
  key: "DIA", name: "Diamond", start_step: "draft", context_schema: [],
  steps: [
    { id: "draft", type: "form", name: "Draft", config: {}, transitions: [{ id: "s", to: "gate", label: "Submit", action: "submit" }] },
    { id: "gate", type: "decision", name: "CRO?", config: {}, transitions: [
      { id: "y", to: "cro_sign", label: "Yes", action: "auto" },
      { id: "n", to: "site_ordered", label: "No", action: "auto" }] },
    { id: "cro_sign", type: "ordered_signing", name: "CRO Sign", config: { signers: [{ id: "cro", name: "CRO" }] },
      transitions: [{ id: "a", to: "vp", label: "Signed", action: "all_signed" }] },
    { id: "site_ordered", type: "ordered_signing", name: "Director then PI", config: { signers: [{ id: "d", name: "Director" }, { id: "pi", name: "PI" }] },
      transitions: [{ id: "a", to: "site_parallel", label: "Signed", action: "all_signed" }] },
    { id: "site_parallel", type: "parallel", name: "Remaining", config: { branches: [{ id: "a", name: "A" }, { id: "b", name: "B" }] },
      transitions: [{ id: "q", to: "vp", label: "All", action: "quorum_met" }, { id: "f", to: "draft", label: "back", action: "quorum_failed" }] },
    { id: "vp", type: "ordered_signing", name: "VP Final", config: { signers: [{ id: "vp", name: "VP" }] },
      transitions: [{ id: "a", to: "distribute", label: "Signed", action: "all_signed" }] },
    { id: "distribute", type: "broadcast", name: "Distribute", config: { recipients: [{ id: "pi", name: "PI" }] },
      transitions: [{ id: "b", to: "done", label: "Done", action: "broadcast_done" }] },
    { id: "done", type: "terminal", name: "Done", config: {}, transitions: [] },
  ],
};

describe("buildTopoOrder — convergence node placed AFTER all predecessors", () => {
  it("VP (shared by both branches) sorts after BOTH branch tails, not where first reached", () => {
    const o = buildTopoOrder(DIAMOND);
    const i = (id: string) => o.indexOf(id);
    expect(i("vp")).toBeGreaterThan(i("cro_sign"));
    expect(i("vp")).toBeGreaterThan(i("site_ordered"));
    expect(i("vp")).toBeGreaterThan(i("site_parallel")); // the reported bug: VP must be AFTER remaining
    expect(i("distribute")).toBeGreaterThan(i("vp"));
    expect(i("done")).toBe(o.length - 1);
  });
});

describe("computeStepStates — done/current/upcoming from real engine progress", () => {
  it("a not-yet-reached convergence node is NOT shown done", () => {
    const instance = {
      id: 1, definition_key: "DIA", definition_version: 1, status: "active" as const,
      current_step: "site_parallel", current_step_type: "parallel" as const, current_step_name: "Remaining",
      subject_ref: "x", created_at: "", updated_at: "", context: {},
    };
    // visited = steps the audit shows the engine entered (gate auto-settled, not logged)
    const visited = new Set(["draft", "site_ordered", "site_parallel"]);
    const st = computeStepStates(DIAMOND, instance, visited);
    expect(st.get("site_ordered")).toBe("done");
    expect(st.get("site_parallel")).toBe("current");
    expect(st.get("vp")).toBe("upcoming");          // NOT done — never reached
    expect(st.get("distribute")).toBe("upcoming");
    expect(st.get("gate")).toBe("done");            // decision: a chosen successor was entered
    expect(st.get("cro_sign")).toBe("upcoming");    // CRO branch not taken
  });
  it("completed instance marks all done", () => {
    const inst = { id: 1, definition_key: "DIA", definition_version: 1, status: "completed" as const,
      current_step: null, subject_ref: "x", created_at: "", updated_at: "", context: {} } as any;
    const st = computeStepStates(DIAMOND, inst, new Set());
    expect([...st.values()].every((s) => s === "done")).toBe(true);
  });
});

// A SECOND, different decision: a 3-way branch on a `tier` variable converging on a
// shared `merge` step. Proves the visibility logic is general (not CRO/2-way specific).
const TIERS: WorkflowDefinitionBody = {
  key: "TIERS", name: "Tiers", start_step: "draft", context_schema: [],
  steps: [
    { id: "draft", type: "form", name: "Draft", config: {}, transitions: [{ id: "s", to: "tier_gate", label: "Submit", action: "submit" }] },
    { id: "tier_gate", type: "decision", name: "Tier?", config: {}, transitions: [
      { id: "a", to: "tierA", label: "A", action: "auto" },
      { id: "b", to: "tierB", label: "B", action: "auto" },
      { id: "c", to: "tierC", label: "C", action: "auto" }] },
    { id: "tierA", type: "approval", name: "Tier A", config: {}, transitions: [{ id: "m", to: "merge", label: "ok", action: "approve" }] },
    { id: "tierB", type: "approval", name: "Tier B", config: {}, transitions: [{ id: "m", to: "merge", label: "ok", action: "approve" }] },
    { id: "tierC", type: "approval", name: "Tier C", config: {}, transitions: [{ id: "m", to: "merge", label: "ok", action: "approve" }] },
    { id: "merge", type: "approval", name: "Merge", config: {}, transitions: [{ id: "d", to: "done", label: "done", action: "approve" }] },
    { id: "done", type: "terminal", name: "Done", config: {}, transitions: [] },
  ],
};

describe("computeVisibleSteps — hide steps only on the branch NOT taken", () => {
  it("BEFORE the decision resolves, BOTH branches stay visible", () => {
    const v = computeVisibleSteps(DIAMOND, inst("draft"), new Set(["draft"]));
    expect(v.has("cro_sign")).toBe(true);
    expect(v.has("site_ordered")).toBe(true);
    expect(v.has("vp")).toBe(true); // convergence always visible
  });

  it("CRO=Yes taken → the Site-only steps are hidden, CRO + convergence shown", () => {
    // engine settled onto cro_sign (gate auto-resolved, not separately audited)
    const v = computeVisibleSteps(DIAMOND, inst("cro_sign"), new Set(["draft", "cro_sign"]));
    expect(v.has("cro_sign")).toBe(true);
    expect(v.has("site_ordered")).toBe(false);   // hidden (untaken branch)
    expect(v.has("site_parallel")).toBe(false);  // hidden (untaken branch)
    expect(v.has("vp")).toBe(true);              // shared convergence — shown
    expect(v.has("distribute")).toBe(true);
    expect(v.has("done")).toBe(true);
    expect(v.has("gate")).toBe(true);            // the decision itself stays
  });

  it("CRO=No taken → the CRO-only step is hidden, Site path + convergence shown", () => {
    const v = computeVisibleSteps(DIAMOND, inst("site_parallel"), new Set(["draft", "site_ordered", "site_parallel"]));
    expect(v.has("cro_sign")).toBe(false);       // hidden (untaken branch)
    expect(v.has("site_ordered")).toBe(true);
    expect(v.has("site_parallel")).toBe(true);
    expect(v.has("vp")).toBe(true);              // convergence still visible (not yet reached)
    expect(v.has("distribute")).toBe(true);
    expect(v.has("done")).toBe(true);
  });

  it("convergence stays visible even after the path has reached past it (no leak)", () => {
    // far along the SITE path: vp/distribute reached. CRO branch must STILL be hidden,
    // even though it converges into the (now reached) vp step.
    const v = computeVisibleSteps(DIAMOND, inst("distribute"),
      new Set(["draft", "site_ordered", "site_parallel", "vp", "distribute"]));
    expect(v.has("cro_sign")).toBe(false);
    expect(v.has("vp")).toBe(true);
    expect(v.has("distribute")).toBe(true);
  });

  it("GENERAL: a 3-way decision hides the two branches not taken", () => {
    const v = computeVisibleSteps(TIERS, inst("tierB"), new Set(["draft", "tierB"]));
    expect(v.has("tierA")).toBe(false);
    expect(v.has("tierC")).toBe(false);
    expect(v.has("tierB")).toBe(true);
    expect(v.has("merge")).toBe(true);   // convergence
    expect(v.has("done")).toBe(true);
  });

  it("GENERAL: before the 3-way resolves, all three branches show", () => {
    const v = computeVisibleSteps(TIERS, inst("draft"), new Set(["draft"]));
    expect(v.has("tierA")).toBe(true);
    expect(v.has("tierB")).toBe(true);
    expect(v.has("tierC")).toBe(true);
  });
});

describe("recordedBranches — reads engine _branches from context", () => {
  it("returns recorded decisions for a step", () => {
    const instance = {
      id: 1, definition_key: "DEMO_LONG", definition_version: 1, status: "active" as const,
      current_step: "signing", current_step_type: "ordered_signing" as const, current_step_name: "Ordered Signing",
      subject_ref: "x", created_at: "", updated_at: "",
      context: { _branches: { signing: { director: { decision: "signed" } } } },
    };
    const rec = recordedBranches(instance, "signing");
    expect(rec.director?.decision).toBe("signed");
    expect(rec.pi).toBeUndefined();
  });
});
