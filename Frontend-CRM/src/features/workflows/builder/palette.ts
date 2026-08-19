// builder/palette.ts
// The draggable step kinds shown in the builder's left rail. Mirrors the backend
// STEP_TYPE_CATALOG; can also be fetched live via workflowApi.stepTypes().

import type { StepType } from "../types";

export interface PaletteItem {
  type: StepType;
  label: string;
  color: string;
  icon: string;
  description: string;
}

export const PALETTE: PaletteItem[] = [
  { type: "form", label: "Form", color: "#6366f1", icon: "📝", description: "Collect / edit data" },
  { type: "approval", label: "Approval", color: "#10b981", icon: "✅", description: "Approve or reject" },
  { type: "signature", label: "Signature", color: "#f59e0b", icon: "✍️", description: "Sign the document" },
  { type: "decision", label: "Decision", color: "#8b5cf6", icon: "🔀", description: "Automatic branch" },
  { type: "parallel", label: "Parallel review", color: "#0ea5e9", icon: "👥", description: "Several reviewers at once; advances on quorum" },
  { type: "ordered_signing", label: "Ordered signing", color: "#e11d48", icon: "🖊️", description: "Signers sign one at a time, in order" },
  { type: "broadcast", label: "Broadcast", color: "#0d9488", icon: "📣", description: "Notify many; no action; auto-advances" },
  { type: "terminal", label: "End", color: "#64748b", icon: "🏁", description: "Final state" },
];

export const COLOR_BY_TYPE: Record<StepType, string> = Object.fromEntries(
  PALETTE.map((p) => [p.type, p.color])
) as Record<StepType, string>;

export const ICON_BY_TYPE: Record<StepType, string> = Object.fromEntries(
  PALETTE.map((p) => [p.type, p.icon])
) as Record<StepType, string>;

export const LABEL_BY_TYPE: Record<StepType, string> = Object.fromEntries(
  PALETTE.map((p) => [p.type, p.label])
) as Record<StepType, string>;
