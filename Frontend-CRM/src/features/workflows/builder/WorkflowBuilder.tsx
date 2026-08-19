// builder/WorkflowBuilder.tsx
// The drag-and-drop workflow builder. This is the feature the CEO asked for: a
// non-programmer draws boxes + arrows here, and Save writes the exact JSON the
// generic engine runs. No new code per document type — ever.
//
// Requires React Flow v12:  npm i @xyflow/react

import React from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  MarkerType,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { workflowApi } from "../api";
import { extractApiError } from "@/lib/api";
import type {
  ClarifyAnswer, ClarifyQuestion, StepType, WorkflowDefinitionBody,
} from "../types";
import { PALETTE, COLOR_BY_TYPE } from "./palette";
import { layoutGraph } from "./layout";
import { StepNode } from "./nodes/StepNode";
import { NodeConfigPanel } from "./NodeConfigPanel";
import { bodyToMermaid, MermaidView } from "./mermaid";
// Pure canvas <-> definition serializers (extracted + unit-tested in serialize.test.ts).
import { fromDefinition, toDefinition } from "./serialize";
import { PromptLibrary } from "./PromptLibrary";
import { ui } from "../runner/steps/common";

const nodeTypes = { step: StepNode };
let _seq = 0;
const uid = (p: string) => `${p}_${Date.now().toString(36)}_${_seq++}`;

// Confirm-screen step-table cells.
const thCell: React.CSSProperties = { padding: "4px 8px", fontWeight: 600, whiteSpace: "nowrap" };
const tdCell: React.CSSProperties = { padding: "4px 8px", verticalAlign: "top" };

// Floating canvas-toolbar button (Tidy / Fit).
const toolBtn: React.CSSProperties = {
  padding: "5px 10px", fontSize: 12, fontWeight: 600, color: "#334155",
  background: "#fff", border: "1px solid #cbd5e1", borderRadius: 8,
  cursor: "pointer", boxShadow: "0 1px 2px rgba(15,23,42,0.06)",
};

// DISPLAY ONLY — who REALLY acts on a step, for the confirm/steps table. Multi-actor
// steps keep their actors in `config` (signers/branches/parties), and the engine uses
// THOSE — not the step-level `assignee`, which on those steps is often an inert/owner
// value (e.g. "study_manager") that misleads. This formats the real actors; it never
// changes the definition, engine, or execution. Falls back to step.assignee when a
// step has no config actors (form/approval/decision).
function actorSummary(step: any): string {
  const cfg = step?.config ?? {};
  const fmt = (a: any): string | null =>
    a?.value ? (a.type && a.type !== "role" ? `${a.type}: ${a.value}` : String(a.value)) : null;

  if (step?.type === "parallel") {
    const branches = Array.isArray(cfg.branches) ? cfg.branches : [];
    if (branches.length) {
      const label = (b: any) => fmt(b.assignee) ?? b.name ?? b.id;
      const action = branches.filter((b: any) => (b.kind ?? "action") === "action").map(label);
      const notify = branches.filter((b: any) => b.kind === "notify").map(label);
      const parts: string[] = [];
      if (action.length) parts.push(action.join(", "));
      if (notify.length) parts.push(`notify: ${notify.join(", ")}`);
      if (parts.length) return parts.join(" · ");
    }
  }
  if (step?.type === "ordered_signing") {
    const signers = Array.isArray(cfg.signers) ? cfg.signers : [];
    if (signers.length) return signers.map((s: any) => fmt(s.assignee) ?? s.name ?? s.id).join(" → ");
  }
  if (step?.module === "discussion") {
    const parties = cfg.discussion?.parties;
    if (Array.isArray(parties) && parties.length) {
      return parties.map((p: any) => p.role ?? p.label).join(" ↔ ");
    }
  }
  if (step?.type === "broadcast") {
    const recips = Array.isArray(cfg.recipients) ? cfg.recipients : [];
    if (recips.length) return recips.map((r: any) => fmt(r.assignee) ?? r.name ?? r.id).join(", ");
  }
  if (step?.type === "terminal") return "—";
  // form / approval / decision (and anything without config actors): the step-level
  // assignee is the real actor — keep showing it (e.g. the owner / study_manager).
  return fmt(step?.assignee)
    ?? (step?.type === "form" || step?.type === "approval" || step?.type === "signature" ? "creator/owner" : "—");
}

// canvas <-> definition serializers (toDefinition / fromDefinition) live in
// ./serialize so they can be unit-tested without the React Flow runtime.

function BuilderInner({ initialKey, presetKey, cloneKey, cloneVersion, onPublished }: {
  initialKey?: string;                       // edit: load this published definition
  presetKey?: string;                        // create new: prefill+lock key, empty canvas
  cloneKey?: string;                         // clone: load steps from this def, blank key
  cloneVersion?: number;                      // clone a SPECIFIC version (else default)
  onPublished?: (key: string, version: number) => void;  // called after Save & publish
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [meta, setMeta] = React.useState<{ key: string; name: string; description?: string }>(
    { key: initialKey ?? presetKey ?? "", name: "" },
  );
  // The loaded definition's context_schema (decision variables). Preserved verbatim
  // through the canvas round-trip so publish doesn't drop it. The canvas itself has
  // no editor for it yet — but it must NOT be wiped.
  const contextSchemaRef = React.useRef<unknown[]>([]);
  // "What you approve = what runs": when the user approves an AI draft and does NOT
  // edit it on the canvas, we publish this EXACT approved body (the same artifact the
  // confirm Mermaid was rendered from) instead of re-serializing the canvas — so the
  // published workflow is byte-for-byte what was shown. Any genuine canvas edit clears
  // it (markEdited), and publish falls back to toDefinition(canvas). null = no pristine
  // approved draft (fresh canvas, or the user has edited).
  const approvedBodyRef = React.useRef<WorkflowDefinitionBody | null>(null);
  // Clear the pristine approved draft on a real structural edit, so publish serializes
  // the (now user-modified) canvas rather than the stale approved body.
  const markEdited = React.useCallback(() => { approvedBodyRef.current = null; }, []);
  // The authoring prompt to persist with the NEXT save. Set when an AI draft is
  // approved, or restored when loading/cloning a version that carried one — so the
  // prompt survives canvas edits (which clear approvedBodyRef) and republishing.
  const sourcePromptRef = React.useRef<string>("");
  const [selectedNode, setSelectedNode] = React.useState<Node | null>(null);
  const [selectedEdge, setSelectedEdge] = React.useState<Edge | null>(null);
  const [status, setStatus] = React.useState<string>("");
  const wrapper = React.useRef<HTMLDivElement>(null);
  const rf = useReactFlow();

  // Re-fit the viewport after nodes change programmatically (load / AI approve /
  // tidy). A short delay lets React Flow measure the freshly-mounted nodes first.
  // maxZoom caps the zoom-in so a 2-node graph doesn't blow up to giant boxes,
  // and (with minZoom on <ReactFlow>) a big graph never shrinks to unreadable.
  const fitSoon = React.useCallback(() => {
    window.setTimeout(() => rf.fitView({ padding: 0.2, maxZoom: 1, duration: 300 }), 60);
  }, [rf]);

  // "Tidy" — re-run the dagre layout on the CURRENT canvas (after manual drags
  // or hand-added steps) and re-fit. Pure reposition; never touches step data.
  const tidy = React.useCallback(() => {
    setNodes((nds) => layoutGraph(nds, edges));
    fitSoon();
  }, [edges, setNodes, fitSoon]);

  // --- LLM clarify → confirm → (approve loads to canvas → Save & publish = lock&run) ---
  const [aiDesc, setAiDesc] = React.useState("");
  const [aiMermaid, setAiMermaid] = React.useState("");   // optional pasted flowchart
  const [aiBusy, setAiBusy] = React.useState(false);
  const [aiError, setAiError] = React.useState<string | null>(null);
  const [aiPhase, setAiPhase] = React.useState<"idle" | "clarify" | "confirm">("idle");
  const [aiQuestions, setAiQuestions] = React.useState<ClarifyQuestion[]>([]);
  const [aiAnswers, setAiAnswers] = React.useState<Record<string, string>>({});
  const [aiDraft, setAiDraft] = React.useState<WorkflowDefinitionBody | null>(null);
  const [aiAssumptions, setAiAssumptions] = React.useState<string[]>([]);
  const [aiSummary, setAiSummary] = React.useState<string>("");
  const [aiClarifyMsg, setAiClarifyMsg] = React.useState<string | null>(null);
  // Iterative refine: the user's pending change request + the accumulating log of
  // applied requests. The current draft (aiDraft) is the compounding artifact — each
  // refine modifies it, so successive rounds build on the last instead of resetting.
  const [aiFeedback, setAiFeedback] = React.useState("");
  const [aiRefineLog, setAiRefineLog] = React.useState<string[]>([]);

  const resetAi = () => {
    setAiPhase("idle"); setAiQuestions([]); setAiAnswers({}); setAiDraft(null);
    setAiAssumptions([]); setAiSummary(""); setAiClarifyMsg(null);
    setAiFeedback(""); setAiRefineLog([]);
  };

  // STEP 1 — clarify. If the description leaves shape-changing things ambiguous, ask;
  // otherwise go straight to generating the draft.
  const handleStart = async () => {
    if (!aiDesc.trim() && !aiMermaid.trim()) return;
    setAiBusy(true); setAiError(null); resetAi();
    try {
      let questions: ClarifyQuestion[] = [];
      try {
        const c = await workflowApi.clarifyWorkflow(aiDesc.trim(), aiMermaid.trim() || undefined);
        questions = c.questions ?? [];
      } catch {
        // Clarify is gated to WORKFLOW_UNIFIED (403 when off). If it's unavailable,
        // degrade gracefully to a single-shot draft (the prior behavior) rather than
        // blocking — generate still validates + the user confirms on the canvas.
        questions = [];
      }
      if (questions.length) {
        setAiQuestions(questions);
        setAiAnswers(Object.fromEntries(questions.map((q) => [q.id, ""])));
        setAiPhase("clarify");
      } else {
        await runGenerate([]);
      }
    } finally {
      setAiBusy(false);
    }
  };

  // STEP 2 — generate the resolved draft + plain-English summary (honoring answers).
  const runGenerate = async (answers: ClarifyAnswer[]) => {
    setAiBusy(true); setAiError(null);
    try {
      const res = await workflowApi.generate(
        aiDesc.trim(), meta.key.trim() || undefined, meta.name.trim() || undefined, answers,
        aiMermaid.trim() || undefined,
      );
      if (res.needs_clarification) { setAiClarifyMsg(res.needs_clarification); setAiPhase("idle"); return; }
      if (res.body) {
        // Older backends may not stamp the prompt into the draft — do it here so
        // approve → publish always persists what the user typed.
        if (!res.body.source_prompt && aiDesc.trim()) res.body.source_prompt = aiDesc.trim();
        setAiDraft(res.body);
        setAiAssumptions(res.assumptions ?? []);
        setAiSummary(res.summary ?? "");
        setAiRefineLog([]); // a fresh generation starts a new refine history
        setAiPhase("confirm");
      }
    } catch (err: unknown) {
      setAiError(extractApiError(err, "Failed to generate the workflow."));
    } finally {
      setAiBusy(false);
    }
  };

  // REFINE — modify the EXISTING draft per the user's feedback WITHOUT restarting.
  // Sends the current draft (prior) + this round's feedback (+ the accumulated log
  // and original description/Mermaid for context); the model returns the full updated
  // definition, which replaces the draft and stays on the confirm screen so the user
  // can refine again (compounding) or approve.
  const runRefine = async () => {
    const fb = aiFeedback.trim();
    if (!fb || !aiDraft) return;
    setAiBusy(true); setAiError(null); setAiClarifyMsg(null);
    try {
      const res = await workflowApi.generate(
        aiDesc.trim(), meta.key.trim() || undefined, meta.name.trim() || undefined, [],
        aiMermaid.trim() || undefined, aiDraft, fb, aiRefineLog,
      );
      if (res.needs_clarification) { setAiClarifyMsg(res.needs_clarification); return; }
      if (res.body) {
        setAiDraft(res.body);
        setAiAssumptions(res.assumptions ?? []);
        setAiSummary(res.summary ?? "");
        setAiRefineLog((log) => [...log, fb]); // remember what we asked, for context + display
        setAiFeedback("");
        setAiPhase("confirm");
      }
    } catch (err: unknown) {
      setAiError(extractApiError(err, "Failed to refine the workflow."));
    } finally {
      setAiBusy(false);
    }
  };

  const submitAnswers = async () => {
    const answers: ClarifyAnswer[] = aiQuestions.map((q) => ({
      id: q.id, question: q.question, answer: aiAnswers[q.id] || "",
    }));
    await runGenerate(answers);
  };
  const allAnswered = aiQuestions.every((q) => (aiAnswers[q.id] || "").trim().length > 0);

  // STEP 3 — APPROVE: load the confirmed draft onto the canvas (modules preserved),
  // then the user clicks Save & publish to lock & run on the existing engine/modules.
  const approveDraft = () => {
    if (!aiDraft) return;
    const { nodes: n, edges: e } = fromDefinition(aiDraft);
    setNodes(n); setEdges(e);
    contextSchemaRef.current = (aiDraft.context_schema as unknown[]) ?? []; // keep declared decision vars
    // Remember the EXACT approved body so publish ships it verbatim unless the user
    // edits the canvas (markEdited clears this). Capture before resetAi() clears aiDraft.
    approvedBodyRef.current = aiDraft as WorkflowDefinitionBody;
    // Keep the authoring prompt for the save — even if the user then edits the
    // canvas (which clears approvedBodyRef), the published version still records it.
    sourcePromptRef.current = (aiDraft.source_prompt ?? aiDesc).trim();
    setMeta({ key: aiDraft.key, name: aiDraft.name });
    setSelectedNode(null); setSelectedEdge(null);
    resetAi();
    fitSoon();
    setStatus("AI draft approved — review on the canvas, then Save & publish to lock & run.");
  };

  // load existing definition for editing
  React.useEffect(() => {
    if (!initialKey) return;
    workflowApi.getDefinition(initialKey).then((v) => {
      const { nodes: n, edges: e } = fromDefinition(v.body);
      setNodes(n);
      setEdges(e);
      contextSchemaRef.current = (v.body.context_schema as unknown[]) ?? []; // keep declared decision vars
      approvedBodyRef.current = null; // editing an existing def — publish serializes the canvas
      // Restore the prompt this version was authored from, pre-filled in the
      // description box so the user can see/refine it instead of starting blank.
      const savedPrompt = (v.body.source_prompt ?? "").trim();
      sourcePromptRef.current = savedPrompt;
      if (savedPrompt) setAiDesc(savedPrompt);
      setMeta({ key: v.body.key, name: v.body.name, description: v.body.description });
      fitSoon();
    });
  }, [initialKey, setNodes, setEdges, fitSoon]);

  // clone an existing definition: load its steps/description as the starting canvas.
  // Target key: if presetKey is given (e.g. the agreement screen pins tpl:<id>), keep
  // it LOCKED and publish a new version under it; otherwise BLANK the key so the user
  // names a brand-new workflow (the source is untouched either way). cloneVersion picks
  // an exact version, else the default.
  React.useEffect(() => {
    if (!cloneKey) return;
    workflowApi.getDefinition(cloneKey, cloneVersion).then((v) => {
      const { nodes: n, edges: e } = fromDefinition(v.body);
      setNodes(n);
      setEdges(e);
      contextSchemaRef.current = (v.body.context_schema as unknown[]) ?? [];
      approvedBodyRef.current = null; // cloning — publish serializes the canvas under the target key
      // Same prompt restoration as editing: cloning a version from the history
      // browser brings its authoring prompt back into the description box.
      const savedPrompt = (v.body.source_prompt ?? "").trim();
      sourcePromptRef.current = savedPrompt;
      if (savedPrompt) setAiDesc(savedPrompt);
      setMeta({
        key: presetKey ?? "",
        name: presetKey ? v.body.name : `${v.body.name} (copy)`,
        description: v.body.description,
      });
      fitSoon();
    });
  }, [cloneKey, cloneVersion, presetKey, setNodes, setEdges, fitSoon]);

  const onConnect = React.useCallback(
    (c: Connection) => {
      markEdited();
      setEdges((eds) =>
        addEdge(
          {
            ...c,
            id: uid("t"),
            markerEnd: { type: MarkerType.ArrowClosed },
            data: { label: "Next", action: "next", clauses: [], conditionMode: "all" },
          },
          eds
        )
      );
    },
    [setEdges, markEdited]
  );

  const onDrop = React.useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const type = event.dataTransfer.getData("application/step-type") as StepType;
      if (!type || !wrapper.current) return;
      const bounds = wrapper.current.getBoundingClientRect();
      const position = { x: event.clientX - bounds.left - 80, y: event.clientY - bounds.top - 20 };
      markEdited();
      const id = uid(type);
      const node: Node = {
        id,
        type: "step",
        position,
        data: {
          type,
          name: defaultName(type),
          // Single-assignee steps get a role assignee; multi-actor / non-human
          // steps (parallel, ordered_signing, broadcast, decision, terminal) don't.
          assignee: ["terminal", "decision", "parallel", "ordered_signing", "broadcast"].includes(type)
            ? null
            : { type: "role", value: "" },
          fields: [],
          signers: [],
          config: {},
          isStart: nodes.length === 0,
        },
      };
      setNodes((nds) => nds.concat(node));
    },
    [nodes.length, setNodes, markEdited]
  );

  const patchNode = (id: string, patch: Record<string, unknown>) => {
    markEdited();
    setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)));
  };

  const patchEdge = (id: string, patch: Record<string, unknown>) => {
    markEdited();
    setEdges((eds) =>
      eds.map((e) => {
        if (e.id !== id) return e;
        const data = { ...(e.data ?? {}), ...patch };
        return { ...e, data, label: (data as any).label ?? e.label };
      })
    );
  };

  const deleteSelected = () => {
    markEdited();
    if (selectedNode) {
      setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
      setEdges((eds) => eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id));
      setSelectedNode(null);
    } else if (selectedEdge) {
      setEdges((eds) => eds.filter((e) => e.id !== selectedEdge.id));
      setSelectedEdge(null);
    }
  };

  const save = async (publish: boolean) => {
    if (!meta.key.trim() || !meta.name.trim()) {
      setStatus("Key and name are required");
      return;
    }
    // Governance: publishing makes this the org-wide default for the type.
    if (publish) {
      const ok = window.confirm(
        `This becomes the default workflow for all future ${meta.key.trim()} agreements.\n\n` +
        `Existing in-progress agreements are NOT affected — they stay on the version ` +
        `they started on. Publish as the new default?`,
      );
      if (!ok) {
        setStatus("Publish cancelled.");
        return;
      }
    }
    setStatus("Saving…");
    try {
      // "What you approve = what runs": if the user approved an AI draft and hasn't
      // edited the canvas, publish that EXACT approved body (overlaying only key/name,
      // which the inputs may have changed). Otherwise serialize the canvas. This makes
      // the published workflow identical to the confirm-screen Mermaid's source.
      const approved = approvedBodyRef.current;
      const body = approved
        ? { ...approved, key: meta.key.trim() || approved.key, name: meta.name.trim() || approved.name }
        : toDefinition(nodes, edges, meta, contextSchemaRef.current);
      // Persist the authoring prompt with this version (survives canvas edits —
      // the canvas serializer doesn't know about it). Approved AI bodies already
      // carry it; the ref covers the edited/cloned/hand-tweaked paths.
      if (!body.source_prompt && sourcePromptRef.current) body.source_prompt = sourcePromptRef.current;
      const errs = validate(body);
      if (errs.length) throw new Error(errs.join(" · "));
      const v = await workflowApi.saveDefinition(body, publish);
      setStatus(`Saved version ${v.version}${publish ? " (published — new default)" : ""} ✓`);
      // After publish, hand control back so the sandbox can start THIS agreement's
      // instance on the freshly published version and open the runner.
      if (publish && onPublished) onPublished(meta.key.trim(), v.version);
    } catch (e: unknown) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  };

  const sourceTypeOfEdge = selectedEdge
    ? (nodes.find((n) => n.id === selectedEdge.source)?.data as any)?.type as StepType | undefined
    : undefined;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 600 }}>
      {/* ── AI clarify → confirm authoring bar ─────────────────────────── */}
      <div style={{ borderBottom: "1px solid #e2e8f0", padding: 12, background: "#f8fafc", maxHeight: "46vh", overflowY: "auto" }}>
        <label style={{ ...ui.label, marginBottom: 6 }}>Describe your workflow</label>
        {aiPhase === "idle" && <PromptLibrary onPick={setAiDesc} />}
        <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
          <textarea
            value={aiDesc}
            onChange={(e) => setAiDesc(e.target.value)}
            placeholder="e.g. Review by one legal reviewer, then one signer signs; reviewer can send back for edits."
            style={{ ...ui.textarea, minHeight: 52, flex: 1 }}
          />
          <button
            style={{
              ...ui.btnPrimary,
              // Match the real enabled state (description OR a pasted Mermaid), so the
              // button doesn't LOOK disabled when only the Mermaid field has content.
              opacity: aiBusy || (!aiDesc.trim() && !aiMermaid.trim()) ? 0.5 : 1,
              whiteSpace: "nowrap",
            }}
            onClick={handleStart}
            disabled={aiBusy || (!aiDesc.trim() && !aiMermaid.trim())}
          >
            {aiBusy ? "Working…" : aiPhase === "idle" ? "✨ Generate with AI" : "✨ Start over"}
          </button>
        </div>

        {/* Optional: paste a Mermaid flowchart — the LLM reads the intended shape from
            it (decision/parallel/ordered signing/broadcast). No new service; the
            diagram on the confirm screen is rendered client-side from the result. */}
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "#475569", fontWeight: 600 }}>
            …or paste a Mermaid flowchart (optional)
          </summary>
          <textarea
            value={aiMermaid}
            onChange={(e) => setAiMermaid(e.target.value)}
            placeholder={"flowchart TD\n  A[Draft] --> B[Legal Review]\n  B -->|Approve| C[/Director Signs/]\n  C --> D[/PI Signs/]\n  D --> E[[Remaining sign]]\n  E --> F[(Distribute copy)]"}
            spellCheck={false}
            style={{ ...ui.textarea, minHeight: 96, marginTop: 6, fontFamily: "monospace", fontSize: 12 }}
          />
        </details>

        {aiClarifyMsg && (
          <div style={{ marginTop: 8, padding: "8px 10px", background: "#fef9c3", border: "1px solid #fde047", borderRadius: 8, fontSize: 13 }}>
            <strong>Need a bit more detail:</strong> {aiClarifyMsg}
          </div>
        )}
        {aiError && (
          <div style={{ marginTop: 8, padding: "8px 10px", background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, fontSize: 13, color: "#b91c1c" }}>
            {aiError}
          </div>
        )}

        {/* STEP 1 — clarifying questions (only the genuinely-ambiguous ones) */}
        {aiPhase === "clarify" && (
          <div style={{ marginTop: 10, padding: 12, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10 }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>A few questions before I draft it</div>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 10 }}>
              These change how the workflow behaves. Pick an option or type your own.
            </div>
            {aiQuestions.map((q) => (
              <div key={q.id} style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>{q.question}</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
                  {q.options.map((opt) => {
                    const active = aiAnswers[q.id] === opt;
                    return (
                      <button
                        key={opt}
                        onClick={() => setAiAnswers((m) => ({ ...m, [q.id]: opt }))}
                        style={{
                          padding: "5px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, cursor: "pointer",
                          border: `1px solid ${active ? "#4f46e5" : "#cbd5e1"}`,
                          background: active ? "#eef2ff" : "#fff", color: active ? "#3730a3" : "#334155",
                        }}
                      >
                        {opt}
                      </button>
                    );
                  })}
                </div>
                <input
                  style={{ ...ui.input, marginBottom: 0 }}
                  placeholder="…or type a specific answer"
                  value={aiAnswers[q.id] || ""}
                  onChange={(e) => setAiAnswers((m) => ({ ...m, [q.id]: e.target.value }))}
                />
              </div>
            ))}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                style={{ ...ui.btnPrimary, opacity: aiBusy || !allAnswered ? 0.5 : 1 }}
                disabled={aiBusy || !allAnswered}
                onClick={submitAnswers}
              >
                {aiBusy ? "Drafting…" : "Continue →"}
              </button>
              <button style={ui.btnSecondary ?? { ...ui.btnPrimary, background: "#64748b" }} onClick={resetAi}>Cancel</button>
            </div>
          </div>
        )}

        {/* STEP 2 — confirm: plain-English summary + the full resolved step list */}
        {aiPhase === "confirm" && aiDraft && (
          <div style={{ marginTop: 10, padding: 12, background: "#fff", border: "1px solid #c7d2fe", borderRadius: 10 }}>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Confirm this workflow</div>
            {aiSummary && (
              <div style={{ fontSize: 13, lineHeight: 1.5, color: "#0f172a", background: "#eef2ff",
                            border: "1px solid #c7d2fe", borderRadius: 8, padding: "8px 10px", marginBottom: 10 }}>
                {aiSummary}
              </div>
            )}
            {/* Interpreted flow rendered as Mermaid FROM the validated JSON, so it's
                exactly what will run. */}
            <div style={{ fontSize: 12, fontWeight: 700, color: "#475569", margin: "2px 0 4px" }}>Interpreted flow</div>
            <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, marginBottom: 10, background: "#fbfdff" }}>
              <MermaidView chart={bodyToMermaid(aiDraft)} />
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "#64748b" }}>
                    <th style={thCell}>#</th><th style={thCell}>Step</th><th style={thCell}>Type</th>
                    <th style={thCell}>Module</th><th style={thCell}>Who acts</th>
                  </tr>
                </thead>
                <tbody>
                  {aiDraft.steps.map((s, i) => (
                    <tr key={s.id} style={{ borderTop: "1px solid #f1f5f9" }}>
                      <td style={tdCell}>{i + 1}</td>
                      <td style={{ ...tdCell, fontWeight: 600 }}>{s.name}</td>
                      <td style={tdCell}>{s.type}</td>
                      <td style={tdCell}>{(s as any).module ?? "—"}</td>
                      {/* Real actors from config (signers/branches/parties), not the
                          inert step-level assignee — display only. */}
                      <td style={tdCell}>{actorSummary(s)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {aiAssumptions.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#475569" }}>
                <strong>Assumptions:</strong>
                <ul style={{ margin: "4px 0 0 18px" }}>{aiAssumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
              </div>
            )}
            {/* Changes applied so far this session — shows refinements compound. */}
            {aiRefineLog.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#475569" }}>
                <strong>Changes applied:</strong>
                <ol style={{ margin: "4px 0 0 18px" }}>{aiRefineLog.map((f, i) => <li key={i}>{f}</li>)}</ol>
              </div>
            )}

            {/* ── Request changes / refine (iterative — does NOT reset to step 1) ── */}
            <div style={{ marginTop: 12, padding: 10, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8 }}>
              <label style={{ ...ui.label, marginBottom: 6 }}>Request changes / refine this workflow</label>
              <textarea
                value={aiFeedback}
                onChange={(e) => setAiFeedback(e.target.value)}
                placeholder='e.g. "Add a financial reviewer in parallel with legal", "VP signs before distribution", "make the two reviews parallel"'
                style={{ ...ui.textarea, minHeight: 52 }}
                disabled={aiBusy}
                onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void runRefine(); }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center" }}>
                <button
                  style={{ ...ui.btnPrimary, opacity: aiBusy || !aiFeedback.trim() ? 0.5 : 1 }}
                  onClick={() => void runRefine()}
                  disabled={aiBusy || !aiFeedback.trim()}
                >
                  {aiBusy ? "Refining…" : "↻ Apply changes"}
                </button>
                <span style={{ fontSize: 12, color: "#64748b" }}>
                  Updates this workflow with your change — keeps everything else. Refine as many times as you like.
                </span>
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center", flexWrap: "wrap" }}>
              <button style={{ ...ui.btnPrimary, background: "#16a34a" }} onClick={approveDraft} disabled={aiBusy}>
                Approve &amp; load to canvas
              </button>
              {/* Explicit discard — go back to the description to author a fresh one. */}
              <button
                style={ui.btnSecondary ?? { ...ui.btnPrimary, background: "#64748b" }}
                onClick={() => { if (window.confirm("Discard this workflow and start a new description from scratch?")) resetAi(); }}
                disabled={aiBusy}
              >
                Start over
              </button>
              <span style={{ fontSize: 12, color: "#64748b" }}>
                Approve loads it onto the canvas — review, then <strong>Save &amp; publish</strong> to lock &amp; run.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ── builder (palette + canvas + inspector) ─────────────────────── */}
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
      {/* palette */}
      <div style={{ width: 184, borderRight: "1px solid #e2e8f0", padding: 12, overflowY: "auto", background: "#fafbfc" }}>
        <h4 style={{ margin: "0 0 4px", fontSize: 13, color: "#334155" }}>Steps</h4>
        <p style={{ fontSize: 11, color: "#94a3b8", margin: "0 0 10px" }}>Drag a step onto the canvas.</p>
        {PALETTE.map((p) => (
          <div
            key={p.type}
            draggable
            onDragStart={(e) => e.dataTransfer.setData("application/step-type", p.type)}
            onDragEnd={(e) => { (e.currentTarget as HTMLDivElement).style.boxShadow = "none"; }}
            title={p.description}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              border: `1px solid ${p.color}`,
              borderLeft: `4px solid ${p.color}`,
              borderRadius: 8, padding: "7px 9px", marginBottom: 7,
              cursor: "grab", background: "#fff",
              boxShadow: "0 1px 2px rgba(15,23,42,0.05)",
            }}
          >
            <span style={{ fontSize: 15, lineHeight: 1 }}>{p.icon}</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, color: p.color, lineHeight: 1.1 }}>{p.label}</div>
              <div style={{ fontSize: 10.5, color: "#94a3b8", lineHeight: 1.2, marginTop: 1 }}>{p.description}</div>
            </div>
          </div>
        ))}
        <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 10, lineHeight: 1.4 }}>
          Then drag from a box's dot to another box to draw an arrow.
        </p>
      </div>

      {/* canvas */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", gap: 8, padding: 10, borderBottom: "1px solid #e2e8f0", alignItems: "center" }}>
          <input style={{ ...ui.input, marginBottom: 0, width: 120 }} placeholder="KEY (e.g. NDA)" value={meta.key} onChange={(e) => setMeta((m) => ({ ...m, key: e.target.value.toUpperCase() }))} disabled={Boolean(initialKey || presetKey)} />
          <input style={{ ...ui.input, marginBottom: 0, flex: 1 }} placeholder="Workflow name" value={meta.name} onChange={(e) => setMeta((m) => ({ ...m, name: e.target.value }))} />
          <button style={ui.btnPrimary} onClick={() => save(false)}>Save draft</button>
          <button style={{ ...ui.btnPrimary, background: "#16a34a" }} onClick={() => save(true)}>Save & publish</button>
          <span style={{ fontSize: 12, color: status.includes("✓") ? "#16a34a" : "#dc2626" }}>{status}</span>
        </div>

        <div ref={wrapper} style={{ flex: 1 }} onDrop={onDrop} onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, n) => { setSelectedNode(n); setSelectedEdge(null); }}
            onEdgeClick={(_, e) => { setSelectedEdge(e); setSelectedNode(null); }}
            onPaneClick={() => { setSelectedNode(null); setSelectedEdge(null); }}
            defaultEdgeOptions={{ markerEnd: { type: MarkerType.ArrowClosed }, style: { strokeWidth: 1.5, stroke: "#94a3b8" } }}
            // Cap zoom so a tiny graph never balloons and a big one never shrinks
            // to unreadable — this is the fix for "the flowchart becomes small".
            minZoom={0.4}
            maxZoom={1.75}
            fitView
            fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
            proOptions={{ hideAttribution: true }}
            style={{ background: "#f8fafc" }}
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#dbe3ec" />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              nodeStrokeWidth={2}
              nodeColor={(n) => COLOR_BY_TYPE[(n.data as any)?.type as StepType] ?? "#cbd5e1"}
              style={{ border: "1px solid #e2e8f0", borderRadius: 8 }}
            />
            {/* Floating toolbar: tidy the layout / re-fit the view at any time. */}
            <Panel position="top-right">
              <div style={{ display: "flex", gap: 6 }}>
                <button onClick={tidy} style={toolBtn} title="Auto-arrange the steps top-to-bottom">⤵ Tidy</button>
                <button onClick={fitSoon} style={toolBtn} title="Fit the whole flow in view">⤢ Fit</button>
              </div>
            </Panel>
          </ReactFlow>
        </div>
      </div>

      {/* inspector */}
      <NodeConfigPanel
        selectedNode={selectedNode}
        selectedEdge={selectedEdge}
        sourceType={sourceTypeOfEdge}
        onChangeNode={patchNode}
        onChangeEdge={patchEdge}
        onDelete={deleteSelected}
      />
      </div>
    </div>
  );
}

function defaultName(type: StepType): string {
  return {
    form: "New Form", approval: "New Approval", signature: "New Signature",
    decision: "Decision", parallel: "Parallel Review",
    ordered_signing: "Ordered Signing", broadcast: "Broadcast", terminal: "End",
    split: "Parallel Split", join: "Join", job: "Automated Step",
    wait_message: "Wait for Event", wait_condition: "Wait for Condition", call: "Sub-workflow",
  }[type];
}

// Lightweight client-side checks mirroring the backend validators.
function validate(body: WorkflowDefinitionBody): string[] {
  const errs: string[] = [];
  if (body.steps.length === 0) errs.push("Add at least one step");
  if (!body.steps.some((s) => s.type === "terminal")) errs.push("Add an End step");
  if (!body.start_step) errs.push("Mark a start step");
  const ids = new Set(body.steps.map((s) => s.id));
  body.steps.forEach((s) => s.transitions.forEach((t) => { if (!ids.has(t.to)) errs.push(`Arrow from ${s.name} points nowhere`); }));
  return errs;
}

export function WorkflowBuilder({ definitionKey, presetKey, cloneKey, cloneVersion, onPublished }: {
  definitionKey?: string;                                  // edit existing (loads it)
  presetKey?: string;                                      // create new (prefill+lock key)
  cloneKey?: string;                                       // clone existing (load steps, blank key)
  cloneVersion?: number;                                   // clone a SPECIFIC version (else default)
  onPublished?: (key: string, version: number) => void;    // after Save & publish
}) {
  return (
    <ReactFlowProvider>
      <BuilderInner initialKey={definitionKey} presetKey={presetKey}
                    cloneKey={cloneKey} cloneVersion={cloneVersion} onPublished={onPublished} />
    </ReactFlowProvider>
  );
}
