// builder/mermaid.tsx
// Two pieces for the Mermaid-on-confirm feature:
//   1. bodyToMermaid(body)  — derive a Mermaid flowchart STRING from the VALIDATED
//      workflow JSON, so the diagram the user confirms is exactly what will run
//      (not a separate LLM rendering that could drift).
//   2. <MermaidView chart/> — lazy-load the `mermaid` lib (keeps it out of the main
//      bundle) and render the string to SVG. Pure client-side: no key, no env, no
//      backend. securityLevel "strict" since we inject SVG into the DOM.

import React from "react";
import type { WorkflowDefinitionBody } from "../types";

// Mermaid node ids must be simple tokens; map step ids -> safe ids deterministically.
function safeId(id: string, i: number): string {
  const s = (id || `n${i}`).replace(/[^A-Za-z0-9_]/g, "_");
  return /^[A-Za-z_]/.test(s) ? s : `n_${s}`;
}

// Mermaid label text inside quotes: drop the chars that break the parser.
function label(text: string): string {
  return (text || "").replace(/["{}|<>]/g, " ").replace(/\s+/g, " ").trim().slice(0, 60);
}

// Per-type node shape (so a decision looks like a diamond, a terminal like a pill…).
function node(id: string, name: string, type: string, module?: string | null): string {
  const text = module ? `${label(name)}<br/>[${label(module)}]` : label(name);
  switch (type) {
    case "decision":
      return `${id}{"${text}"}`;
    case "terminal":
      return `${id}(["${text}"])`;
    case "parallel":
      return `${id}[["${text}"]]`;
    case "ordered_signing":
    case "signature":
      return `${id}[/"${text}"/]`;
    case "broadcast":
      return `${id}[("${text}")]`;
    default: // form, approval
      return `${id}["${text}"]`;
  }
}

/** Build a Mermaid `flowchart TD` from a validated WorkflowDefinitionBody. */
export function bodyToMermaid(body: WorkflowDefinitionBody): string {
  const steps = body.steps ?? [];
  const idOf = new Map<string, string>();
  steps.forEach((s, i) => idOf.set(s.id, safeId(s.id, i)));

  const lines: string[] = ["flowchart TD"];
  steps.forEach((s) => {
    lines.push("  " + node(idOf.get(s.id)!, s.name, String(s.type), (s as any).module));
  });
  steps.forEach((s) => {
    const from = idOf.get(s.id)!;
    (s.transitions ?? []).forEach((t) => {
      const to = idOf.get(t.to);
      if (!to) return;
      const lbl = label(t.label || t.action || "");
      lines.push(lbl ? `  ${from} -->|${lbl}| ${to}` : `  ${from} --> ${to}`);
    });
  });
  // Mark the start step.
  const start = idOf.get(body.start_step);
  if (start) lines.push(`  style ${start} stroke:#4f46e5,stroke-width:2px`);
  return lines.join("\n");
}

let _mmSeq = 0;

/** Lazy-rendered Mermaid diagram. `chart` is a Mermaid source string. */
export function MermaidView({ chart }: { chart: string }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "default" });
        const id = `wf-mmd-${_mmSeq++}`;
        const { svg } = await mermaid.render(id, chart);
        if (alive && ref.current) {
          ref.current.innerHTML = svg;
          setError(null);
        }
      } catch {
        if (alive) setError("Could not render the diagram (the JSON below is the source of truth).");
      }
    })();
    return () => { alive = false; };
  }, [chart]);

  if (error) {
    return <div style={{ fontSize: 12, color: "#b91c1c", padding: "6px 0" }}>{error}</div>;
  }
  return <div ref={ref} style={{ overflowX: "auto", padding: "4px 0" }} />;
}
