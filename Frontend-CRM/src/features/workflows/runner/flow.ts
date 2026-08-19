// runner/flow.ts
// Pure, data-driven helpers that turn a workflow DEFINITION + INSTANCE into the
// shapes the runner UI needs (a stepper line, per-step state, branch/slot lists).
// No per-document-type knowledge — everything is derived from (body, instance).
// Kept side-effect-free so it can be unit-tested against ANY workflow shape.

import type { Step, WorkflowDefinitionBody, WorkflowInstance } from "../types";

/**
 * Flow order for the stepper line: a breadth-first walk from `start_step`
 * following each step's transitions in declared order. Back-edges (rework loops)
 * point at already-seen steps and are skipped, so loops don't duplicate nodes.
 * Any steps unreachable from start are appended in definition order (defensive).
 * Works for ANY shape and any number of steps.
 */
export function buildFlowOrder(body: WorkflowDefinitionBody): string[] {
  const byId = new Map(body.steps.map((s) => [s.id, s]));
  const order: string[] = [];
  const seen = new Set<string>();
  const queue: string[] = [];

  const start = body.start_step && byId.has(body.start_step) ? body.start_step : body.steps[0]?.id;
  if (start) queue.push(start);

  while (queue.length) {
    const id = queue.shift() as string;
    if (seen.has(id) || !byId.has(id)) continue;
    seen.add(id);
    order.push(id);
    for (const t of byId.get(id)!.transitions) {
      if (!seen.has(t.to)) queue.push(t.to);
    }
  }
  for (const s of body.steps) if (!seen.has(s.id)) order.push(s.id);
  return order;
}

/**
 * TOPOLOGICAL flow order for the stepper line: reverse-post-order DFS from
 * `start_step`. Unlike a BFS "first-reached" walk, this guarantees a CONVERGENCE
 * node (one a diamond reaches from several branches — e.g. a shared final VP
 * signature reached from both a CRO and a Site branch) is placed AFTER all of its
 * forward predecessors, instead of jumping ahead to where it was first reached.
 * Back-edges (rework loops) are naturally skipped (already-visited), so loops don't
 * duplicate or reorder nodes. Unreachable steps are appended in definition order.
 * Works for ANY shape; pure + side-effect-free.
 */
export function buildTopoOrder(body: WorkflowDefinitionBody): string[] {
  const byId = new Map(body.steps.map((s) => [s.id, s]));
  const start = body.start_step && byId.has(body.start_step) ? body.start_step : body.steps[0]?.id;
  const visited = new Set<string>();
  const post: string[] = [];
  const dfs = (id: string) => {
    if (!id || visited.has(id) || !byId.has(id)) return;
    visited.add(id);
    for (const t of byId.get(id)!.transitions) dfs(t.to);
    post.push(id); // pushed AFTER all descendants -> reverse gives forward topo order
  };
  if (start) dfs(start);
  for (const s of body.steps) if (!visited.has(s.id)) dfs(s.id);
  return post.reverse();
}

export type StepState = "done" | "current" | "upcoming";

/**
 * Per-step state derived from the ENGINE'S ACTUAL PROGRESS — not from a step's
 * position on the line. `visited` is the set of steps the instance has actually
 * entered (built from the audit trail's from/to steps). A step is:
 *   - "done"     if the instance completed, OR it's been visited (and isn't current),
 *                OR it's a decision whose chosen successor was entered (decisions
 *                auto-settle and aren't separately audited);
 *   - "current"  if it is the instance's current_step;
 *   - "upcoming" otherwise.
 * This is what stops a not-yet-reached convergence node (e.g. VP) from being shown
 * "done" just because it sorts before the current step.
 */
export function computeStepStates(
  body: WorkflowDefinitionBody,
  instance: WorkflowInstance,
  visited: Set<string>,
): Map<string, StepState> {
  const byId = new Map(body.steps.map((s) => [s.id, s]));
  const current = instance.current_step ?? "";
  const completed = instance.status === "completed";
  const out = new Map<string, StepState>();
  for (const s of body.steps) {
    let state: StepState;
    if (completed) state = "done";
    else if (s.id === current) state = "current";
    else if (visited.has(s.id)) state = "done";
    else if (s.type === "decision" && (byId.get(s.id)?.transitions ?? []).some((t) => visited.has(t.to)))
      state = "done";
    else state = "upcoming";
    out.set(s.id, state);
  }
  return out;
}

/**
 * Classify a step in the line relative to the instance's current step (by flow
 * order index). A completed instance marks everything done. This is a flow-order
 * visualization — exact branch/loop history lives in the audit trail.
 */
export function stepStateAt(index: number, currentIndex: number, instanceStatus: string): StepState {
  if (instanceStatus === "completed") return "done";
  if (currentIndex === -1) return "upcoming";
  if (index < currentIndex) return "done";
  if (index === currentIndex) return "current";
  return "upcoming";
}

/**
 * Steps to SHOW in the stepper, given how far the engine has progressed. Once a
 * decision has RESOLVED (the engine entered one of its outgoing branches), the steps
 * reachable ONLY through the branch(es) NOT taken are hidden; the taken path and any
 * shared CONVERGENCE steps stay visible. Before a decision resolves, all its branches
 * remain visible (nothing is hidden), so the user can still see the fork.
 *
 * General + pure: derived only from the definition's transitions + the audit-`visited`
 * set. No per-document-type or per-variable knowledge — works for any decision, any
 * number of branches, any workflow.
 *
 * Method:
 *  1. `onTakenPath(x)` — is x on the path the engine actually followed? A reached step
 *     is; a DECISION is if one of its successors is (decisions auto-settle and aren't
 *     separately audited, so we look THROUGH them). It only recurses via decisions, so
 *     a mere convergence step that the untaken branch also flows into is never mistaken
 *     for "taken".
 *  2. For each decision that has a taken branch AND an untaken branch, drop the untaken
 *     edges. Then keep every step still reachable from `start_step` over the remaining
 *     edges. A convergence step stays reachable via the taken branch (kept); a step only
 *     the untaken branch could reach becomes unreachable (hidden).
 *  3. Never hide a step the engine actually entered (safety).
 */
export function computeVisibleSteps(
  body: WorkflowDefinitionBody,
  instance: WorkflowInstance,
  visited: Set<string>,
): Set<string> {
  const byId = new Map(body.steps.map((s) => [s.id, s]));
  // The engine's actual progress: audited steps + the live current step (defensive,
  // in case the audit hasn't surfaced it yet).
  const reached = new Set(visited);
  if (instance.current_step) reached.add(instance.current_step);

  const onTakenPath = (id: string, stack: Set<string>): boolean => {
    if (reached.has(id)) return true;
    const s = byId.get(id);
    if (!s || s.type !== "decision" || stack.has(id)) return false;
    stack.add(id);
    const res = s.transitions.some((t) => onTakenPath(t.to, stack));
    stack.delete(id);
    return res;
  };

  // Pruned forward edges: drop untaken branches of RESOLVED decisions only.
  const outEdges = new Map<string, string[]>();
  for (const s of body.steps) {
    let targets = s.transitions.map((t) => t.to);
    if (s.type === "decision") {
      const takenTargets = s.transitions.filter((t) => onTakenPath(t.to, new Set())).map((t) => t.to);
      // Resolved (a branch was taken) AND a real fork (some branch not taken) → prune.
      if (takenTargets.length > 0 && takenTargets.length < s.transitions.length) {
        targets = takenTargets;
      }
    }
    outEdges.set(s.id, targets);
  }

  // Reachable from start over the pruned graph (BFS; back-edges are naturally bounded).
  const start = body.start_step && byId.has(body.start_step) ? body.start_step : body.steps[0]?.id;
  const visible = new Set<string>();
  const queue: string[] = start ? [start] : [];
  while (queue.length) {
    const id = queue.shift() as string;
    if (visible.has(id) || !byId.has(id)) continue;
    visible.add(id);
    for (const to of outEdges.get(id) ?? []) if (!visible.has(to)) queue.push(to);
  }
  // Safety: a step the engine actually entered is always shown.
  for (const id of reached) if (byId.has(id)) visible.add(id);
  return visible;
}

// --- Branch / slot / recipient lists for the fan-out step types --------------
export interface BranchItem {
  id: string;
  name: string;
}

/**
 * The sub-items a fan-out step exposes, read straight from step.config:
 *   parallel        -> config.branches    (reviewers acting in parallel)
 *   ordered_signing -> config.signers     (ordered signature slots)
 *   broadcast       -> config.recipients  (notified parties)
 * Returns null for step types that have no sub-items.
 */
export function stepItems(step: Step): BranchItem[] | null {
  const cfg = (step.config ?? {}) as Record<string, unknown>;
  const pick = (arr: unknown): BranchItem[] =>
    Array.isArray(arr)
      ? arr.map((b) => {
          const o = b as Record<string, unknown>;
          return { id: String(o.id), name: String(o.name ?? o.id) };
        })
      : [];
  if (step.type === "parallel") return pick(cfg.branches);
  if (step.type === "ordered_signing") return pick(cfg.signers);
  if (step.type === "broadcast") return pick(cfg.recipients);
  return null;
}

/**
 * The per-step branch/slot decisions the engine has recorded, from the reserved
 * context key `_branches[stepId] = { itemId: { decision, ... } }`. Empty when none.
 */
export function recordedBranches(
  instance: WorkflowInstance,
  stepId: string,
): Record<string, { decision?: string; actor?: string | null }> {
  const all = instance.context?.["_branches"] as
    | Record<string, Record<string, { decision?: string; actor?: string | null }>>
    | undefined;
  return all?.[stepId] ?? {};
}
