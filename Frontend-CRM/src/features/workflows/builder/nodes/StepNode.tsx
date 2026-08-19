// builder/nodes/StepNode.tsx
// Custom React Flow node for a workflow step. Source/target handles let the user
// draw arrows (transitions). Colour-coded + icon per step type, with clear start /
// end markers and a one-line "who acts" summary so the canvas reads at a glance.

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { COLOR_BY_TYPE, ICON_BY_TYPE, LABEL_BY_TYPE } from "../palette";
import type { StepType, Assignee } from "../../types";

export interface StepNodeData {
  type: StepType;
  name: string;
  assignee?: Assignee | null;
  isStart?: boolean;
  [key: string]: unknown;
}

const handleStyle = {
  width: 10,
  height: 10,
  background: "#fff",
  border: "2px solid #94a3b8",
};

export function StepNode({ data, selected }: NodeProps) {
  const d = data as StepNodeData;
  const color = COLOR_BY_TYPE[d.type] ?? "#64748b";
  const isTerminal = d.type === "terminal";
  const signers = Array.isArray((d as any).signers) ? (d as any).signers : [];

  return (
    <div
      style={{
        border: `1.5px solid ${selected ? color : "#e2e8f0"}`,
        borderRadius: 12,
        background: "#fff",
        width: 200,
        boxShadow: selected
          ? `0 0 0 3px ${color}33, 0 6px 16px rgba(15,23,42,0.12)`
          : "0 1px 3px rgba(15,23,42,0.10)",
        overflow: "hidden",
        transition: "box-shadow 120ms ease, border-color 120ms ease",
      }}
    >
      {/* Incoming arrows land on top. The start step ALSO needs a target handle: a
          rework/reject loop legitimately points back to it (e.g. reject -> draft), and
          without a handle React Flow can't draw that edge. The START badge below marks
          it as the start; receiving edges does not change that. */}
      <Handle type="target" position={Position.Top} style={handleStyle} />

      {/* coloured header strip: icon + type label + start badge */}
      <div
        style={{
          background: color,
          color: "#fff",
          padding: "5px 10px",
          fontSize: 11,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.4,
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span style={{ fontSize: 13, lineHeight: 1 }}>{ICON_BY_TYPE[d.type] ?? "•"}</span>
        <span style={{ flex: 1 }}>{LABEL_BY_TYPE[d.type] ?? d.type}</span>
        {d.isStart && (
          <span
            style={{
              background: "rgba(255,255,255,0.25)",
              borderRadius: 999,
              padding: "1px 7px",
              fontSize: 9.5,
              letterSpacing: 0.5,
            }}
          >
            ● START
          </span>
        )}
      </div>

      {/* body: step name + who-acts summary */}
      <div style={{ padding: "9px 11px" }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "#0f172a", lineHeight: 1.25 }}>
          {d.name || "Untitled"}
        </div>
        {d.assignee?.value && (
          <div style={{ fontSize: 11, color: "#64748b", marginTop: 4, display: "flex", gap: 4, alignItems: "center" }}>
            <span>👤</span>
            <span>{d.assignee.type}: {d.assignee.value}</span>
          </div>
        )}
        {d.type === "ordered_signing" && (
          <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
            🖊️ {signers.length} signer{signers.length === 1 ? "" : "s"} (in order)
          </div>
        )}
        {isTerminal && (
          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>Workflow complete</div>
        )}
      </div>

      {/* outgoing arrows leave from bottom (terminal has none) */}
      {!isTerminal && <Handle type="source" position={Position.Bottom} style={handleStyle} />}
    </div>
  );
}
