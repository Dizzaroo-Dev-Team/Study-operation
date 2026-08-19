// runner/steps/index.tsx
// The reusable step components. The engine names a step type; StepRenderer picks
// the matching component. Everything is driven by (step, instance, actions) — no
// per-document branches. Steps that will later embed a real tool (doc viewer,
// signing panel) leave a clearly-labeled SEAM; the action buttons work regardless.

import React from "react";
import OnlyOfficeEditor from "@/components/OnlyOfficeEditor";
import { api, extractApiError } from "@/lib/api";
import type { FormField, Step, WorkflowInstance } from "../../types";
import { stepItems, recordedBranches } from "../flow";
import { ActionButtons, StepProps, ui } from "./common";
import { CallStep, JobStep, WaitConditionStep, WaitMessageStep } from "./v2";

// (The legacy CTA-specific resend-links helper — hardcoded "pi"/"designated" signer
// roles + an agreementType === "CTA" gate — was removed. In the unified path,
// signing steps are rendered by the generic signing module, not this fallback.)

// A subject_ref that is a real agreement is a UUID. Sandbox demo instances start
// with no subject_ref, so this is false and they fall back to the placeholder.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const looksLikeAgreementId = (s: string | null | undefined): s is string => !!s && UUID_RE.test(s);

// A clearly-labeled placeholder where a real tool will mount later (OnlyOffice /
// OTP signing). Intentionally inert — the action buttons below it still work.
function EmbedSlot({ label }: { label: string }) {
  return (
    <div
      style={{
        border: "1px dashed #cbd5e1",
        borderRadius: 8,
        padding: "20px 16px",
        margin: "12px 0",
        background: "#f8fafc",
        color: "#94a3b8",
        fontSize: 13,
        fontWeight: 600,
        textAlign: "center",
      }}
    >
      {label}
    </div>
  );
}

// Generic branch / slot / recipient list for the fan-out step types. Reads the
// items from step.config and the recorded decisions from instance context, so it
// shows "who still needs to act" for ANY parallel/ordered_signing/broadcast step.
function BranchList({
  step,
  instance,
  ordered,
}: {
  step: Step;
  instance: WorkflowInstance;
  ordered: boolean;
}) {
  const items = stepItems(step) ?? [];
  const recorded = recordedBranches(instance, step.id);
  const firstPending = items.findIndex((it) => !recorded[it.id]);

  return (
    <ul style={{ listStyle: "none", padding: 0, margin: "8px 0 0" }}>
      {items.map((it, idx) => {
        const done = Boolean(recorded[it.id]);
        const isCurrent = ordered && !done && idx === firstPending;
        const decision = recorded[it.id]?.decision;
        const mark = done ? "✓" : isCurrent ? "→" : "•";
        const color = done ? "#16a34a" : isCurrent ? "#4f46e5" : "#cbd5e1";
        return (
          <li key={it.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 0" }}>
            <span style={{ width: 18, textAlign: "center", color, fontWeight: 700 }}>{mark}</span>
            <span style={{ flex: 1, fontSize: 14, color: "#334155" }}>
              {ordered ? `${idx + 1}. ` : ""}
              {it.name}
            </span>
            <span style={{ fontSize: 12, color: done ? "#16a34a" : isCurrent ? "#4f46e5" : "#94a3b8" }}>
              {done ? decision ?? "done" : isCurrent ? "awaiting" : "pending"}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// Launch into the EXISTING public signing page (which enforces the per-signer
// emailed token + OTP itself — we pass only the agreement id, never a token).
// This reuses the real signing pipeline by routing to it; it does NOT embed a
// sign-on-behalf form and calls NO signing endpoint from the runner. (The legacy
// CTA-specific page routing was removed with the CDA/CTA bridges.)
function signingPageUrl(agreementId: string): string {
  return `/agreement/sign/${agreementId}`;
}

function SigningLaunch({ instance }: { instance: WorkflowInstance }) {
  const url = signingPageUrl(instance.subject_ref as string);
  return (
    <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 16, margin: "12px 0", background: "#fff" }}>
      <p style={{ margin: 0, color: "#334155", fontWeight: 600 }}>Secure signing</p>
      <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 13 }}>
        Signing runs through the existing secure OTP flow. Each signer completes it via the link
        emailed to them; this opens the same signing page (it asks for the secure link / OTP there).
      </p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        style={{ ...ui.btnPrimary, display: "inline-block", textDecoration: "none", marginTop: 12 }}
      >
        Open signing page ↗
      </a>
    </div>
  );
}

function StepShell({ step, children, wide }: { step: Step; children?: React.ReactNode; wide?: boolean }) {
  // `wide` drops the 560px max-width cap so an embedded document editor fills the
  // available column instead of being squeezed into the form-width card.
  return (
    <div style={wide ? { ...ui.card, maxWidth: "100%" } : ui.card}>
      <h3 style={{ marginTop: 0 }}>{step.name}</h3>
      {step.description && <p style={{ color: "#64748b", marginTop: 0 }}>{step.description}</p>}
      {children}
    </div>
  );
}

// ---- FORM ----------------------------------------------------------------
export function FormStep({ step, instance, actions, busy, onAct }: StepProps) {
  const fields: FormField[] = (step.config.fields as FormField[]) ?? [];
  const [values, setValues] = React.useState<Record<string, unknown>>(() => {
    const seed: Record<string, unknown> = {};
    fields.forEach((f) => (seed[f.key] = instance.context[f.key] ?? ""));
    return seed;
  });
  const set = (k: string, v: unknown) => setValues((s) => ({ ...s, [k]: v }));

  return (
    <StepShell step={step}>
      {fields.map((f) => (
        <div key={f.key}>
          <label style={ui.label}>
            {f.label} {f.required && <span style={{ color: "#dc2626" }}>*</span>}
          </label>
          {f.type === "boolean" ? (
            <input
              type="checkbox"
              checked={Boolean(values[f.key])}
              onChange={(e) => set(f.key, e.target.checked)}
              style={{ marginBottom: 12 }}
            />
          ) : f.type === "select" ? (
            <select value={String(values[f.key] ?? "")} onChange={(e) => set(f.key, e.target.value)} style={ui.input}>
              <option value="">—</option>
              {(f.options ?? []).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
              value={String(values[f.key] ?? "")}
              onChange={(e) => set(f.key, f.type === "number" ? Number(e.target.value) : e.target.value)}
              style={ui.input}
            />
          )}
        </div>
      ))}
      <ActionButtons actions={actions} busy={busy} onAct={onAct} payload={values} />
    </StepShell>
  );
}

// ---- APPROVAL (document review) ------------------------------------------
export function ApprovalStep({ step, instance, actions, busy, onAct, embedDocs }: StepProps) {
  // Reuse the EXISTING OnlyOffice editor + config endpoint for the linked
  // agreement (view/review mode). Only when the flag is on AND the instance is
  // tied to a real agreement (UUID subject_ref); otherwise the labeled placeholder.
  const canEmbed = Boolean(embedDocs) && looksLikeAgreementId(instance.subject_ref);
  const agreementId = instance.subject_ref as string;

  // Part 1 — ensure the working document EXISTS before mounting OnlyOffice (else
  // onlyoffice-config 404s "No document found"). Reuse the EXISTING
  // create-from-template service; idempotent via 400 tolerance ("already has a
  // document"). Show "preparing…" while it runs; a clear message if it can't.
  const [docState, setDocState] = React.useState<"idle" | "preparing" | "ready" | "failed">("idle");
  const [docErr, setDocErr] = React.useState("");
  React.useEffect(() => {
    if (!canEmbed) { setDocState("idle"); return; }
    let alive = true;
    setDocState("preparing");
    setDocErr("");
    (async () => {
      try {
        const templateId = (instance.context?.["template_id"] as string) || "";
        const fd = new FormData();
        if (templateId) fd.append("template_id", templateId);
        await api.post(`/agreements/${agreementId}/create-from-template`, fd);
        if (alive) setDocState("ready");
      } catch (e: any) {
        // 400 = the agreement already has a document → it's ready to view.
        if (alive) {
          if (e?.response?.status === 400) setDocState("ready");
          else { setDocErr(extractApiError(e, "Could not prepare the document.")); setDocState("failed"); }
        }
      }
    })();
    return () => { alive = false; };
  }, [canEmbed, agreementId, instance.context]);

  return (
    <StepShell step={step} wide={canEmbed}>
      {canEmbed ? (
        docState === "ready" ? (
          <div style={{ width: "100%", height: "72vh", minHeight: 520, border: "1px solid #e2e8f0", borderRadius: 8, overflow: "hidden", margin: "12px 0" }}>
            {/* SAME component + default config endpoint (agreements/{id}/onlyoffice-config). */}
            <OnlyOfficeEditor
              agreementId={agreementId}
              canEdit={false}
              editorContainerId={`oo-runner-${instance.id}-${step.id}`}
            />
          </div>
        ) : docState === "failed" ? (
          <div style={{ ...ui.card, maxWidth: "100%", color: "#b91c1c", background: "#fef2f2", borderColor: "#fecaca" }}>
            Could not prepare the document for review. {docErr}
          </div>
        ) : (
          <EmbedSlot label="Preparing document…" />
        )
      ) : (
        <EmbedSlot label="[ Document viewer mounts here ]" />
      )}
      <p style={{ color: "#475569" }}>Review the document and choose an action.</p>
      {/* Sending for review is the review module's job (module="review"); a plain
          approval step here only takes the approve/reject/send-back action. */}
      <ActionButtons actions={actions} busy={busy} onAct={onAct} />
    </StepShell>
  );
}

// ---- SIGNATURE -----------------------------------------------------------
// Type fallback only (the normalizer rewrites authored signature steps to
// ordered_signing + the signing module). Signing ALWAYS runs through the secure
// OTP flow — there is no in-app "type your name" path.
export function SignatureStep({ step, instance, actions, busy, onAct, embedDocs }: StepProps) {
  const canEmbed = Boolean(embedDocs) && looksLikeAgreementId(instance.subject_ref);
  if (canEmbed) {
    return (
      <StepShell step={step}>
        <SigningLaunch instance={instance} />
        <ActionButtons actions={actions} busy={busy} onAct={onAct} />
      </StepShell>
    );
  }
  // No real agreement (sandbox/demo): signing requires the secure OTP flow, which
  // needs the live agreement — so there is nothing to sign here.
  return (
    <StepShell step={step}>
      <EmbedSlot label="[ Signing runs through the secure OTP flow once the agreement exists ]" />
      <p style={{ color: "#94a3b8", fontSize: 13, marginTop: 8 }}>
        Signing is completed via the secure link emailed to each signer (OTP + name + intent).
      </p>
    </StepShell>
  );
}

// ---- PARALLEL (fan-out review) -------------------------------------------
export function ParallelStep({ step, instance, actions, busy, onAct }: StepProps) {
  const items = stepItems(step) ?? [];
  const recorded = recordedBranches(instance, step.id);
  const doneCount = items.filter((it) => recorded[it.id]).length;
  return (
    <StepShell step={step}>
      <p style={{ color: "#475569", margin: 0 }}>
        {doneCount} of {items.length} branches complete — who still needs to act:
      </p>
      <BranchList step={step} instance={instance} ordered={false} />
      <ActionButtons actions={actions} busy={busy} onAct={onAct} />
    </StepShell>
  );
}

// ---- ORDERED SIGNING -----------------------------------------------------
export function OrderedSigningStep({ step, instance, actions, busy, onAct, embedDocs }: StepProps) {
  // The engine already tells us whose slot is open (BranchList highlights it).
  // Real agreement → launch the EXISTING signing page; sandbox → placeholder.
  const canEmbed = Boolean(embedDocs) && looksLikeAgreementId(instance.subject_ref);
  return (
    <StepShell step={step}>
      {canEmbed ? <SigningLaunch instance={instance} /> : <EmbedSlot label="[ Signing panel mounts here ]" />}
      <p style={{ color: "#475569", margin: "12px 0 0" }}>Signatures are collected in order:</p>
      <BranchList step={step} instance={instance} ordered />
      <ActionButtons actions={actions} busy={busy} onAct={onAct} />
    </StepShell>
  );
}

// ---- BROADCAST (notify all) ----------------------------------------------
export function BroadcastStep({ step, instance, actions, busy, onAct }: StepProps) {
  const items = stepItems(step) ?? [];
  return (
    <StepShell step={step}>
      <p style={{ color: "#475569", margin: 0 }}>Notifying {items.length} recipients:</p>
      <BranchList step={step} instance={instance} ordered={false} />
      <ActionButtons actions={actions} busy={busy} onAct={onAct} />
    </StepShell>
  );
}

// ---- TERMINAL ------------------------------------------------------------
export function TerminalStep({ step }: StepProps) {
  return (
    <StepShell step={step}>
      <p style={{ color: "#16a34a", fontWeight: 600, margin: 0 }}>This workflow has reached its end state.</p>
    </StepShell>
  );
}

// ---- SPLIT / JOIN (V2 gateways — automatic; transiently visible) -----------
export function SplitStep({ step }: StepProps) {
  return (
    <StepShell step={step}>
      <p style={{ color: "#475569", margin: 0 }}>
        Opening {step.transitions.length} parallel branches — each branch runs as its own track.
      </p>
    </StepShell>
  );
}

export function JoinStep({ step, instance }: StepProps) {
  const joins = (instance.context as Record<string, unknown>)?._joins as
    | Record<string, Record<string, number>> | undefined;
  const arrived = Object.values(joins?.[step.id] ?? {}).reduce((a, b) => a + Number(b || 0), 0);
  const policy = (step.config?.join as { mode?: string; value?: number } | undefined) ?? {};
  const policyLabel =
    policy.mode === "n_of_m" ? `${policy.value} branches` :
    policy.mode === "percent" ? `${policy.value}% of branches` : "all branches";
  return (
    <StepShell step={step}>
      <p style={{ color: "#475569", margin: 0 }}>
        Waiting for parallel branches to arrive — proceeds when {policyLabel} complete.
        {arrived > 0 && <> {arrived} arrived so far.</>}
      </p>
    </StepShell>
  );
}

// ---- DISPATCHER ----------------------------------------------------------
export function StepRenderer(props: StepProps) {
  switch (props.step.type) {
    case "form":
      return <FormStep {...props} />;
    case "approval":
      return <ApprovalStep {...props} />;
    case "signature":
      return <SignatureStep {...props} />;
    case "parallel":
      return <ParallelStep {...props} />;
    case "ordered_signing":
      return <OrderedSigningStep {...props} />;
    case "broadcast":
      return <BroadcastStep {...props} />;
    case "terminal":
      return <TerminalStep {...props} />;
    case "split":
      return <SplitStep {...props} />;
    case "join":
      return <JoinStep {...props} />;
    case "job":
      return <JobStep {...props} />;
    case "wait_message":
      return <WaitMessageStep {...props} />;
    case "wait_condition":
      return <WaitConditionStep {...props} />;
    case "call":
      return <CallStep {...props} />;
    default:
      return (
        <StepShell step={props.step}>
          <p style={{ color: "#64748b" }}>Processing…</p>
        </StepShell>
      );
  }
}
