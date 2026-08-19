// builder/NodeConfigPanel.tsx
// Right-hand inspector. When a node (step) is selected you edit its name, who acts,
// and (for forms) its fields. When an edge (transition) is selected you edit the
// label, the action verb, whether a comment is required, and the branch CONDITION.

import React from "react";
import type { Edge, Node } from "@xyflow/react";
import type { Clause, ConditionOperator, FormField, StepType } from "../types";
import { ui } from "../runner/steps/common";

const OPERATORS: { value: ConditionOperator; label: string; needsValue: boolean }[] = [
  { value: "is_true", label: "is true", needsValue: false },
  { value: "is_false", label: "is false", needsValue: false },
  { value: "eq", label: "equals", needsValue: true },
  { value: "neq", label: "not equals", needsValue: true },
  { value: "gt", label: ">", needsValue: true },
  { value: "gte", label: "≥", needsValue: true },
  { value: "lt", label: "<", needsValue: true },
  { value: "lte", label: "≤", needsValue: true },
  { value: "exists", label: "exists", needsValue: false },
  { value: "not_exists", label: "missing", needsValue: false },
];

const ACTIONS_BY_TYPE: Record<StepType, string[]> = {
  form: ["submit", "save"],
  approval: ["approve", "reject"],
  signature: ["sign", "decline"],
  decision: ["auto"],
  parallel: ["quorum_met", "quorum_failed"],       // transitions leaving a parallel step
  ordered_signing: ["all_signed", "signing_declined"],
  broadcast: ["broadcast_done"],
  terminal: [],
  // V2 step kinds — the structural actions their transitions use.
  split: ["auto"],
  join: ["join_met"],
  job: ["job_done", "job_failed"],
  wait_message: ["message_received"],
  wait_condition: ["condition_met"],
  call: ["children_done"],
};

export function NodeConfigPanel({
  selectedNode,
  selectedEdge,
  sourceType,
  onChangeNode,
  onChangeEdge,
  onDelete,
}: {
  selectedNode: Node | null;
  selectedEdge: Edge | null;
  sourceType?: StepType; // type of the edge's source node (drives action options)
  onChangeNode: (id: string, patch: Record<string, unknown>) => void;
  onChangeEdge: (id: string, patch: Record<string, unknown>) => void;
  onDelete: () => void;
}) {
  if (selectedNode) return <NodePanel node={selectedNode} onChange={onChangeNode} onDelete={onDelete} />;
  if (selectedEdge)
    return <EdgePanel edge={selectedEdge} sourceType={sourceType} onChange={onChangeEdge} onDelete={onDelete} />;
  return (
    <div style={panel}>
      <p style={{ color: "#94a3b8" }}>Select a step or an arrow to configure it.</p>
    </div>
  );
}

// ---- NODE ----------------------------------------------------------------
function NodePanel({ node, onChange, onDelete }: { node: Node; onChange: (id: string, p: Record<string, unknown>) => void; onDelete: () => void }) {
  const d = node.data as Record<string, unknown>;
  const type = d.type as StepType;
  const assignee = (d.assignee as { type?: string; value?: string } | null) ?? { type: "role", value: "" };
  const fields = (d.fields as FormField[]) ?? [];

  return (
    <div style={panel}>
      <h4 style={{ marginTop: 0 }}>Step · {type}</h4>

      <label style={ui.label}>Step id (stable key)</label>
      <input style={ui.input} value={node.id} disabled />

      <label style={ui.label}>Name</label>
      <input style={ui.input} value={String(d.name ?? "")} onChange={(e) => onChange(node.id, { name: e.target.value })} />

      <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <input type="checkbox" checked={Boolean(d.isStart)} onChange={(e) => onChange(node.id, { isStart: e.target.checked })} />
        <span style={{ fontSize: 13 }}>This is the start step</span>
      </label>

      {/* Single-assignee steps (form/approval/signature) pick ONE actor.
          parallel/ordered_signing have per-branch/per-signer assignees instead;
          decision/terminal/broadcast have none. */}
      {["form", "approval", "signature"].includes(type) && (
        <>
          <label style={ui.label}>Who acts?</label>
          <div style={{ display: "flex", gap: 8 }}>
            <select
              style={{ ...ui.input, flex: "0 0 110px" }}
              value={assignee.type}
              onChange={(e) => onChange(node.id, { assignee: { ...assignee, type: e.target.value } })}
            >
              <option value="role">role</option>
              <option value="user">user</option>
              <option value="context">context</option>
            </select>
            <input
              style={ui.input}
              placeholder={assignee.type === "role" ? "e.g. legal" : "id / context key"}
              value={assignee.value ?? ""}
              onChange={(e) => onChange(node.id, { assignee: { ...assignee, value: e.target.value } })}
            />
          </div>
        </>
      )}

      {type === "form" && (
        <FieldEditor fields={fields} onChange={(f) => onChange(node.id, { fields: f })} />
      )}

      {type === "ordered_signing" && (
        <SignerEditor
          signers={(d.signers as SignerRow[]) ?? []}
          onChange={(s) => onChange(node.id, { signers: s })}
        />
      )}

      {(type === "parallel" || type === "broadcast") && (
        <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 8 }}>
          {type === "parallel" ? "Parallel review" : "Broadcast"} configuration
          (branches / quorum / recipients) isn't editable in the UI yet — define it
          in the seeded definition for now.
        </p>
      )}

      <button style={{ ...ui.btnDanger, marginTop: 16 }} onClick={onDelete}>Delete step</button>
    </div>
  );
}

function FieldEditor({ fields, onChange }: { fields: FormField[]; onChange: (f: FormField[]) => void }) {
  const update = (i: number, patch: Partial<FormField>) =>
    onChange(fields.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));
  const add = () => onChange([...fields, { key: `field_${fields.length + 1}`, label: "New field", type: "text" }]);
  const remove = (i: number) => onChange(fields.filter((_, idx) => idx !== i));

  return (
    <div style={{ marginTop: 8 }}>
      <label style={ui.label}>Form fields</label>
      {fields.map((f, i) => (
        <div key={i} style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, marginBottom: 8 }}>
          <input style={ui.input} value={f.key} onChange={(e) => update(i, { key: e.target.value })} placeholder="key" />
          <input style={ui.input} value={f.label} onChange={(e) => update(i, { label: e.target.value })} placeholder="label" />
          <select style={ui.input} value={f.type} onChange={(e) => update(i, { type: e.target.value as FormField["type"] })}>
            {["text", "number", "boolean", "date", "select"].map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
            <input type="checkbox" checked={Boolean(f.required)} onChange={(e) => update(i, { required: e.target.checked })} /> required
          </label>
          <button style={{ ...ui.btnDanger, marginTop: 6, padding: "4px 10px" }} onClick={() => remove(i)}>remove</button>
        </div>
      ))}
      <button style={{ ...ui.btnPrimary, padding: "6px 12px" }} onClick={add}>+ field</button>
    </div>
  );
}

// ---- ORDERED-SIGNING SIGNER LIST -----------------------------------------
// Writes config.signers as an ordered [{id, name, assignee}] — the exact shape
// the engine + toDefinition()/fromDefinition() use. The engine gates signing to
// one slot at a time in THIS array order; the editor just lets a user define it.
interface SignerRow {
  id: string;
  name: string;
  assignee: { type: string; value: string };
}

let _signerSeq = 0;
function _newSignerId(): string {
  _signerSeq += 1;
  return `signer_${Date.now().toString(36)}_${_signerSeq}`;
}

function SignerEditor({ signers, onChange }: { signers: SignerRow[]; onChange: (s: SignerRow[]) => void }) {
  const update = (i: number, patch: Partial<SignerRow>) =>
    onChange(signers.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  const setAssignee = (i: number, patch: Partial<SignerRow["assignee"]>) =>
    update(i, { assignee: { ...(signers[i].assignee ?? { type: "role", value: "" }), ...patch } });
  const add = () =>
    onChange([...signers, { id: _newSignerId(), name: `Signer ${signers.length + 1}`, assignee: { type: "role", value: "" } }]);
  const remove = (i: number) => onChange(signers.filter((_, idx) => idx !== i));
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= signers.length) return;
    const cp = [...signers];
    [cp[i], cp[j]] = [cp[j], cp[i]];
    onChange(cp);
  };

  return (
    <div style={{ marginTop: 8 }}>
      <label style={ui.label}>Signers (in order)</label>
      <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 8px" }}>
        Signers sign in this order — each one's signature opens only after the previous has signed.
      </p>
      {signers.map((s, i) => {
        const a = s.assignee ?? { type: "role", value: "" };
        return (
          <div key={s.id || i} style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: 8, marginBottom: 8 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: "#64748b", width: 18 }}>{i + 1}.</span>
              <input
                style={{ ...ui.input, marginBottom: 0 }}
                placeholder="Signer name (e.g. Site Director)"
                value={s.name}
                onChange={(e) => update(i, { name: e.target.value })}
              />
              <button style={miniBtn} disabled={i === 0} onClick={() => move(i, -1)} title="Move up">↑</button>
              <button style={miniBtn} disabled={i === signers.length - 1} onClick={() => move(i, 1)} title="Move down">↓</button>
              <button style={{ ...miniBtn, color: "#dc2626", borderColor: "#fca5a5" }} onClick={() => remove(i)} title="Remove">✕</button>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <select
                style={{ ...ui.input, marginBottom: 0, flex: "0 0 100px" }}
                value={a.type}
                onChange={(e) => setAssignee(i, { type: e.target.value })}
              >
                <option value="role">role</option>
                <option value="user">user</option>
                <option value="context">context</option>
              </select>
              <input
                style={{ ...ui.input, marginBottom: 0 }}
                placeholder={a.type === "role" ? "e.g. sponsor" : "id / context key"}
                value={a.value ?? ""}
                onChange={(e) => setAssignee(i, { value: e.target.value })}
              />
            </div>
          </div>
        );
      })}
      <button style={{ ...ui.btnPrimary, padding: "6px 12px" }} onClick={add}>+ Add signer</button>
    </div>
  );
}

const miniBtn: React.CSSProperties = {
  padding: "4px 8px", border: "1px solid #cbd5e1", borderRadius: 6,
  background: "#fff", cursor: "pointer", fontWeight: 600, lineHeight: 1,
};

// ---- EDGE (transition) ---------------------------------------------------
function EdgePanel({ edge, sourceType, onChange, onDelete }: { edge: Edge; sourceType?: StepType; onChange: (id: string, p: Record<string, unknown>) => void; onDelete: () => void }) {
  const d = (edge.data as Record<string, unknown>) ?? {};
  const action = String(d.action ?? "next");
  const clauses = (d.clauses as Clause[]) ?? [];
  const mode = (d.conditionMode as "all" | "any") ?? "all";
  const actionOptions = sourceType ? ACTIONS_BY_TYPE[sourceType] : ["next"];

  const setClauses = (c: Clause[]) => onChange(edge.id, { clauses: c });
  const addClause = () => setClauses([...clauses, { field: "", op: "is_true" }]);
  const updateClause = (i: number, patch: Partial<Clause>) =>
    setClauses(clauses.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));

  return (
    <div style={panel}>
      <h4 style={{ marginTop: 0 }}>Transition (arrow)</h4>

      <label style={ui.label}>Button label</label>
      <input style={ui.input} value={String(d.label ?? "")} onChange={(e) => onChange(edge.id, { label: e.target.value })} />

      <label style={ui.label}>Action verb</label>
      <select style={ui.input} value={action} onChange={(e) => onChange(edge.id, { action: e.target.value })}>
        {(actionOptions.length ? actionOptions : ["next"]).map((a) => <option key={a} value={a}>{a}</option>)}
      </select>
      {action === "auto" && (
        <small style={{ color: "#8b5cf6" }}>Auto — the engine fires this itself when the condition is met (no human click).</small>
      )}

      <label style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0" }}>
        <input type="checkbox" checked={Boolean(d.requires_comment)} onChange={(e) => onChange(edge.id, { requires_comment: e.target.checked })} />
        <span style={{ fontSize: 13 }}>Require a comment</span>
      </label>

      <label style={ui.label}>Condition {clauses.length > 1 && <>(match <em>{mode}</em>)</>}</label>
      {clauses.length > 1 && (
        <select style={ui.input} value={mode} onChange={(e) => onChange(edge.id, { conditionMode: e.target.value })}>
          <option value="all">all (AND)</option>
          <option value="any">any (OR)</option>
        </select>
      )}
      {clauses.map((c, i) => {
        const op = OPERATORS.find((o) => o.value === c.op);
        return (
          <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
            <input style={{ ...ui.input, marginBottom: 0 }} placeholder="field" value={c.field} onChange={(e) => updateClause(i, { field: e.target.value })} />
            <select style={{ ...ui.input, marginBottom: 0, flex: "0 0 90px" }} value={c.op} onChange={(e) => updateClause(i, { op: e.target.value as ConditionOperator })}>
              {OPERATORS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            {op?.needsValue && (
              <input style={{ ...ui.input, marginBottom: 0, flex: "0 0 80px" }} placeholder="value" value={String(c.value ?? "")} onChange={(e) => updateClause(i, { value: coerce(e.target.value) })} />
            )}
          </div>
        );
      })}
      <button style={{ ...ui.btnPrimary, padding: "6px 12px" }} onClick={addClause}>+ condition</button>
      {clauses.length > 0 && (
        <button style={{ ...ui.btnDanger, padding: "6px 12px", marginLeft: 8 }} onClick={() => setClauses([])}>clear</button>
      )}

      <button style={{ ...ui.btnDanger, marginTop: 16, display: "block" }} onClick={onDelete}>Delete arrow</button>
    </div>
  );
}

function coerce(v: string): unknown {
  if (v === "true") return true;
  if (v === "false") return false;
  if (v !== "" && !isNaN(Number(v))) return Number(v);
  return v;
}

const panel: React.CSSProperties = {
  width: 300,
  borderLeft: "1px solid #e2e8f0",
  padding: 16,
  overflowY: "auto",
  height: "100%",
  boxSizing: "border-box",
  background: "#fafafa",
};
