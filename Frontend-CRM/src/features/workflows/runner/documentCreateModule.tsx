// runner/documentCreateModule.tsx
// Module "document_create": the draft/initial-version step. Ensures the working v1
// document exists from the template (owner action), then shows it + the step's
// forward action. Wraps the EXISTING create-from-template service
// (POST /agreements/{id}/create-from-template -> crud/doc_operations clone+fill via
// docx_placeholder_replace). Importing this file registers it.

import React from "react";
import { registerStepModule, ownsAgreement, type StepModuleContext } from "./modules";
import { DocumentViewer } from "./DocumentViewer";

const card: React.CSSProperties = { border: "1px solid #e2e8f0", borderRadius: 12, padding: 20, background: "#fff", maxWidth: "100%" };

interface FormFieldDef { key: string; label?: string; type?: string; required?: boolean; options?: string[]; }

// One input for a declared draft-form field. The value is written into the workflow
// context on submit (the engine merges the action payload into context), so a
// downstream decision step can branch on it (e.g. is_cro_involved -> CRO vs Site).
function FieldInput({ f, value, onChange }: { f: FormFieldDef; value: unknown; onChange: (v: unknown) => void }) {
  const label = f.label || f.key;
  if (f.type === "boolean") {
    return (
      <label style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0", fontSize: 14 }}>
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span>
      </label>
    );
  }
  if (f.type === "select" && Array.isArray(f.options)) {
    return (
      <label style={{ display: "block", margin: "8px 0", fontSize: 14 }}>
        <span style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>{label}{f.required ? " *" : ""}</span>
        <select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}
                style={{ padding: "8px 10px", border: "1px solid #cbd5e1", borderRadius: 8, minWidth: 220 }}>
          <option value="">— select —</option>
          {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
    );
  }
  const inputType = f.type === "number" ? "number" : f.type === "date" ? "date" : "text";
  return (
    <label style={{ display: "block", margin: "8px 0", fontSize: 14 }}>
      <span style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>{label}{f.required ? " *" : ""}</span>
      <input
        type={inputType}
        value={value == null ? "" : String(value)}
        onChange={(e) => onChange(f.type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)}
        style={{ padding: "8px 10px", border: "1px solid #cbd5e1", borderRadius: 8, minWidth: 260 }}
      />
    </label>
  );
}

function DocumentCreatePanel({ ctx }: { ctx: StepModuleContext }) {
  const aid = ctx.subjectRef;

  // Declared draft-form fields (e.g. a decision variable like is_cro_involved). They
  // must render so the owner can set them; their values ride the submit payload into
  // the engine context (which the decision step reads). Seed from any existing context.
  const fields = (((ctx.step.config as Record<string, unknown> | undefined)?.fields) as FormFieldDef[] | undefined) ?? [];
  const [values, setValues] = React.useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {};
    for (const f of fields) {
      const fromCtx = ctx.instance.context?.[f.key];
      init[f.key] = fromCtx !== undefined ? fromCtx : (f.type === "boolean" ? false : "");
    }
    return init;
  });
  const missingRequired = fields.some(
    (f) => f.required && f.type !== "boolean" && (values[f.key] === "" || values[f.key] == null),
  );

  return (
    <div style={card}>
      <h3 style={{ marginTop: 0 }}>{ctx.step.name}</h3>
      {/* The draft document — this step ENSURES it exists (create-from-template) and
          shows the current version in OnlyOffice. */}
      <DocumentViewer
        subjectRef={aid}
        instanceId={ctx.instance.id}
        stepId={ctx.step.id}
        canEdit={false}
        ensure
        ensureTemplateId={(ctx.instance.context?.["template_id"] as string) || undefined}
        refreshKey={ctx.instance.updated_at}
        height="62vh"
      />

      {/* Declared form fields (e.g. decision variables). Rendered so the owner can set
          them at draft; submitted as the action payload -> written into the context. */}
      {fields.length > 0 && (
        <div style={{ borderTop: "1px solid #f1f5f9", marginTop: 12, paddingTop: 8 }}>
          {fields.map((f) => (
            <FieldInput key={f.key} f={f} value={values[f.key]}
                        onChange={(v) => setValues((p) => ({ ...p, [f.key]: v }))} />
          ))}
        </div>
      )}

      {/* Forward action(s) — carry the field values as payload so the engine merges
          them into context (a downstream decision can then branch on them).
          LABEL: this is the DRAFT step — its forward action only ADVANCES the workflow to
          the next step (e.g. Review or Signing), it does NOT send anything itself (the
          actual review dispatch / signing send happens AT that next step). So when there's
          a single forward action we present it as "Submit draft & continue" rather than the
          raw authored label (which is often misleadingly "Send for review"). Decision-style
          steps with multiple forward actions keep their own labels. */}
      {ctx.actions.length ? (
        (() => {
          const forwardCount = ctx.actions.filter((a) => a.action !== "reject" && a.action !== "send_back").length;
          return (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          {ctx.actions.map((a) => {
            const isBack = a.action === "reject" || a.action === "send_back";
            const label = !isBack && forwardCount === 1 ? "Submit draft & continue" : a.label;
            return (
            <button
              key={a.transition_id}
              disabled={ctx.busy || missingRequired}
              onClick={() => ctx.onComplete(a.transition_id, values)}
              style={{
                padding: "9px 16px",
                background: isBack ? "#fff" : "#4f46e5",
                color: isBack ? "#dc2626" : "#fff",
                border: isBack ? "1px solid #fca5a5" : "none",
                borderRadius: 8, fontWeight: 600, cursor: "pointer", opacity: ctx.busy || missingRequired ? 0.5 : 1,
              }}
            >
              {label}
            </button>
            );
          })}
        </div>
          );
        })()
      ) : (
        <p style={{ color: "#94a3b8", marginTop: 12, fontSize: 13 }}>No action available on this step for you.</p>
      )}
    </div>
  );
}

registerStepModule({
  key: "document_create",
  canAct: (ctx) => ownsAgreement(ctx.subjectRef), // create/draft = creator-owns
  render: (ctx) => <DocumentCreatePanel ctx={ctx} />,
});
