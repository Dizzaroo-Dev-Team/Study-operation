// builder/serialize.test.ts
// Guards "what you approve = what runs": the canvas round-trip
// fromDefinition -> toDefinition MUST preserve every transition — including a rework
// loop back to the START step (reject/send_back -> draft), the requires_comment flag,
// step modules, assignees and signer config. (Before the start-step target-handle fix
// the reject back-edge was invisible on the canvas; this proves it still round-trips.)

import { describe, it, expect } from "vitest";
import type { WorkflowDefinitionBody } from "../types";
import { fromDefinition, toDefinition } from "./serialize";

// draft(start) -> review -> signing -> end, with review's send_back looping BACK to the
// start step (draft) and carrying requires_comment. `module` isn't in the Step type
// (read via `as any` in the app), so cast the fixture.
const REVIEW_SIGN = {
  key: "REVIEW_SIGN",
  name: "Review then Sign",
  start_step: "draft",
  context_schema: [],
  steps: [
    {
      id: "draft", type: "form", name: "Create Document", module: "document_create",
      assignee: { type: "context", value: "owner_user_id" }, config: {},
      transitions: [{ id: "t_submit", to: "review", label: "Send for review", action: "submit" }],
    },
    {
      id: "review", type: "approval", name: "Legal Review", module: "review",
      assignee: { type: "role", value: "legal" }, config: {},
      transitions: [
        { id: "t_ok", to: "signing", label: "Approve", action: "approve" },
        // The rework loop back to the START step, with a mandatory comment.
        { id: "t_back", to: "draft", label: "Send back", action: "send_back", requires_comment: true },
      ],
    },
    {
      id: "signing", type: "ordered_signing", name: "Signature", module: "signing",
      config: { signers: [{ id: "signer", name: "Authorized Signer", assignee: { type: "role", value: "sponsor" } }] },
      transitions: [{ id: "t_signed", to: "end", label: "All signed", action: "all_signed" }],
    },
    { id: "end", type: "terminal", name: "Done", config: {}, transitions: [] },
  ],
} as unknown as WorkflowDefinitionBody;

// Canonical "from|action|to|requires_comment" set for every transition in a body.
function edgeKeys(body: WorkflowDefinitionBody): Set<string> {
  const out = new Set<string>();
  body.steps.forEach((s) =>
    (s.transitions ?? []).forEach((t: any) =>
      out.add(`${s.id}|${t.action}|${t.to}|${Boolean(t.requires_comment)}`),
    ),
  );
  return out;
}

describe("builder serialize round-trip", () => {
  const { nodes, edges } = fromDefinition(REVIEW_SIGN);
  const out = toDefinition(
    nodes, edges, { key: REVIEW_SIGN.key, name: REVIEW_SIGN.name },
    REVIEW_SIGN.context_schema as unknown[],
  );

  it("preserves the start step even though a loop points back into it", () => {
    expect(out.start_step).toBe("draft");
  });

  it("preserves EVERY transition, including the reject->draft back-loop", () => {
    expect(edgeKeys(out)).toEqual(edgeKeys(REVIEW_SIGN));
  });

  it("keeps the send_back -> draft rework loop with requires_comment", () => {
    const review = out.steps.find((s) => s.id === "review")!;
    const back = (review.transitions as any[]).find((t) => t.action === "send_back");
    expect(back).toBeTruthy();
    expect(back.to).toBe("draft"); // loops back to the START step
    expect(back.requires_comment).toBe(true);
  });

  it("does not drop the edge into the start step (draft has an incoming transition)", () => {
    const intoDraft = out.steps.flatMap((s) => (s.transitions as any[]) ?? []).filter((t) => t.to === "draft");
    expect(intoDraft.length).toBe(1);
    expect(intoDraft[0].action).toBe("send_back");
  });

  it("preserves step modules", () => {
    const mod = (id: string) => (out.steps.find((s) => s.id === id) as any).module;
    expect(mod("draft")).toBe("document_create");
    expect(mod("review")).toBe("review");
    expect(mod("signing")).toBe("signing");
  });

  it("preserves assignees and ordered-signing signer config", () => {
    const review = out.steps.find((s) => s.id === "review")! as any;
    expect(review.assignee).toEqual({ type: "role", value: "legal" });
    const signing = out.steps.find((s) => s.id === "signing")! as any;
    expect(signing.config.signers).toEqual([
      { id: "signer", name: "Authorized Signer", assignee: { type: "role", value: "sponsor" } },
    ]);
  });
});
