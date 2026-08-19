// builder/serialize.ts
// Pure (canvas <-> definition) serializers, extracted from WorkflowBuilder so they can
// be unit-tested in isolation (no React Flow runtime). They MUST be a faithful
// round-trip: every step, transition (INCLUDING rework loops back to the start step,
// e.g. reject -> draft), assignee, module and config preserved — so "what you approve
// = what runs" holds even after the user edits on the canvas.

import { type Edge, type MarkerType, type Node } from "@xyflow/react";
import type { Clause, Condition, Step, StepType, Transition, WorkflowDefinitionBody } from "../types";
import { layoutGraph } from "./layout";

// MarkerType.ArrowClosed is the string "arrowclosed"; use the literal so this pure
// module never pulls in @xyflow/react at runtime (keeps it test-friendly).
const ARROW = { type: "arrowclosed" as MarkerType };

// ---- canvas -> definition JSON -------------------------------------------
export function buildCondition(clauses?: Clause[], mode: "all" | "any" = "all"): Condition | null {
  if (!clauses || clauses.length === 0) return null;
  const cleaned = clauses.filter((c) => c.field.trim());
  if (cleaned.length === 0) return null;
  return mode === "any" ? { any: cleaned } : { all: cleaned };
}

// Build a step's `config` from its node data, in the SAME shape the engine reads.
//  - form           -> { fields }
//  - ordered_signing-> { signers } (ordered [{id,name,assignee}], edited in the UI)
//  - parallel / broadcast / others -> preserve whatever config was loaded
//    (round-trips e.g. seeded CTA/CDA; their config editors are a separate task).
export function buildStepConfig(d: any): Record<string, unknown> {
  if (d.type === "form") return d.fields ? { fields: d.fields } : {};
  if (d.type === "ordered_signing") return { signers: d.signers ?? [] };
  return (d.config as Record<string, unknown>) ?? {};
}

export function toDefinition(
  nodes: Node[], edges: Edge[], meta: { key: string; name: string; description?: string },
  contextSchema: unknown[] = [],
): WorkflowDefinitionBody {
  const startNode = nodes.find((n) => (n.data as any).isStart) ?? nodes.find((n) => !edges.some((e) => e.target === n.id)) ?? nodes[0];

  const steps: Step[] = nodes.map((n) => {
    const d = n.data as any;
    const outgoing = edges.filter((e) => e.source === n.id);
    const transitions: Transition[] = outgoing.map((e) => {
      const ed = (e.data as any) ?? {};
      return {
        id: e.id,
        to: e.target,
        label: ed.label ?? "Next",
        action: ed.action ?? "next",
        condition: buildCondition(ed.clauses, ed.conditionMode),
        requires_comment: Boolean(ed.requires_comment),
      };
    });
    const step: Step = {
      id: n.id,
      type: d.type as StepType,
      name: d.name ?? "Untitled",
      config: buildStepConfig(d),
      transitions: d.type === "terminal" ? [] : transitions,
    };
    if (d.type !== "terminal" && d.type !== "decision" && d.assignee?.value) {
      step.assignee = d.assignee;
    }
    // Preserve the capability module (document_create/review/approval/signing/notify/
    // broadcast) so an AI-authored draft still runs on the real modules after a
    // canvas round-trip. The builder has no module picker yet, but it must not DROP a
    // module that the AI (or a loaded definition) set.
    if (d.module) (step as any).module = d.module;
    return step;
  });

  return {
    key: meta.key,
    name: meta.name,
    description: meta.description,
    start_step: startNode?.id ?? "",
    // PRESERVE the loaded context_schema (decision variables the generator declared,
    // e.g. is_cro_involved) instead of wiping it — otherwise the reachability of
    // condition-gated branches is silently lost on publish.
    context_schema: (contextSchema as WorkflowDefinitionBody["context_schema"]) ?? [],
    steps,
  };
}

// ---- definition JSON -> canvas -------------------------------------------
export function fromDefinition(body: WorkflowDefinitionBody): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = body.steps.map((s) => ({
    id: s.id,
    type: "step",
    // Position is a placeholder — layoutGraph() below replaces it with a tidy
    // top-down dagre layout so loaded/AI-generated charts don't end up scattered.
    position: { x: 0, y: 0 },
    data: {
      type: s.type,
      name: s.name,
      assignee: s.assignee ?? null,
      module: (s as any).module ?? null,
      isStart: s.id === body.start_step,
      fields: (s.config?.fields as any) ?? [],
      // ordered_signing editor reads this; preserved verbatim on round-trip.
      signers: (s.config?.signers as any) ?? [],
      // Preserve the full config for step kinds without a dedicated UI editor
      // (parallel/broadcast), so re-saving doesn't drop their branches/recipients.
      config: (s.config as any) ?? {},
    },
  }));

  const edges: Edge[] = [];
  body.steps.forEach((s) =>
    s.transitions.forEach((t) => {
      const cond = t.condition;
      const clauses = (cond?.all ?? cond?.any ?? []) as Clause[];
      edges.push({
        id: t.id,
        source: s.id,
        target: t.to,
        label: t.label,
        markerEnd: ARROW,
        data: {
          label: t.label,
          action: t.action,
          requires_comment: t.requires_comment,
          clauses,
          conditionMode: cond?.any ? "any" : "all",
        },
      });
    })
  );
  // Tidy top-down layout so the loaded graph reads as a clean flowchart.
  return { nodes: layoutGraph(nodes, edges), edges };
}
