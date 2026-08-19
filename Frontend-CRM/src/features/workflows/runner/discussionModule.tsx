// runner/discussionModule.tsx
// Module "discussion" (NEED 1): a tracked, in-system two-party comment exchange on a
// workflow step. Two (or more) named parties — e.g. Site Legal ↔ Internal Legal —
// post comments back-and-forth; every comment is STORED + VISIBLE TO BOTH + audited
// (append-only rows). The step ADVANCES when the discussion is marked RESOLVED, which
// is just the normal engine advance on the step's resolve transition — so the engine
// stays unchanged.
//
// GENERAL: the parties + who-can-resolve come from the step's config (not hardcoded
// to legal). Storage REUSES agreement_comments via the workflow discussion endpoints
// (workflowApi.getDiscussion / postDiscussion); nothing about comments is rebuilt.
//
// Step shape this module expects (an `approval`-type step, module="discussion"):
//   config.discussion = {
//     parties: [{ role, label }, { role, label }],   // who is talking (for display)
//     resolve: "owner" | "any_party"                 // who may mark it resolved
//   }
// and one forward transition (the "resolve & advance" arrow).

import React from "react";
import { workflowApi } from "../api";
import { registerStepModule, ownsAgreement, type StepModuleContext } from "./modules";
import type { DiscussionComment } from "../types";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const card: React.CSSProperties = { border: "1px solid #e6eaf0", borderRadius: 12, padding: 20, background: "#fff", maxWidth: "100%", margin: "12px 0", boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)" };
const btnPrimary: React.CSSProperties = { padding: "8px 14px", background: "#4f46e5", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: "pointer", boxShadow: "0 1px 2px rgba(79,70,229,0.18)" };
const btnGhost: React.CSSProperties = { padding: "6px 12px", background: "#fff", color: "#334155", border: "1px solid #cbd5e1", borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: "pointer" };

interface Party { role?: string; label: string }

function DiscussionPanel({ ctx }: { ctx: StepModuleContext }) {
  const cfg = ((ctx.step.config as any)?.discussion ?? {}) as { parties?: Party[]; resolve?: string };
  const parties: Party[] = Array.isArray(cfg.parties) && cfg.parties.length
    ? cfg.parties
    : [{ label: "Internal" }, { label: "External" }];
  const resolveMode = cfg.resolve === "any_party" ? "any_party" : "owner";

  const [comments, setComments] = React.useState<DiscussionComment[]>([]);
  const [draft, setDraft] = React.useState("");
  // Which side am I posting as — maps to the backend party (1st party -> internal).
  const [partyIdx, setPartyIdx] = React.useState(0);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [isOwner, setIsOwner] = React.useState(false);

  const subjectRef = ctx.subjectRef;
  const isSandbox = !subjectRef || !UUID_RE.test(subjectRef);
  // The resolve/advance action is the step's forward transition (not a send-back).
  const resolveAction = ctx.actions.find((a) => a.action !== "reject" && a.action !== "send_back");

  const load = React.useCallback(async () => {
    try {
      setComments(await workflowApi.getDiscussion(ctx.instance.id));
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Could not load the discussion.");
    }
  }, [ctx.instance.id]);

  React.useEffect(() => {
    void load();
    if (!isSandbox && subjectRef) ownsAgreement(subjectRef).then(setIsOwner);
  }, [load, subjectRef, isSandbox]);

  const post = async () => {
    const content = draft.trim();
    if (!content) return;
    setBusy(true); setErr("");
    try {
      const party = partyIdx === 0 ? "internal" : "external";
      await workflowApi.postDiscussion(ctx.instance.id, content, party);
      setDraft("");
      await load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Could not post your comment.");
    } finally {
      setBusy(false);
    }
  };

  // Config-driven resolve gate: "owner" -> only the agreement owner; "any_party" ->
  // anyone the engine authorized (it returned the resolve action). Sandbox is open.
  const canResolve = !!resolveAction && (resolveMode === "any_party" || isOwner || isSandbox);

  const partyLabel = (c: DiscussionComment) => {
    if (c.party === "internal") return parties[0]?.label ?? "Internal";
    if (c.party === "external") return parties[1]?.label ?? "External";
    return "System";
  };
  const partyColor = (c: DiscussionComment) =>
    c.party === "internal" ? "#4f46e5" : c.party === "external" ? "#0d9488" : "#64748b";

  return (
    <div style={card}>
      <h3 style={{ marginTop: 0, marginBottom: 4, fontSize: 16, fontWeight: 700, color: "#0f172a" }}>{ctx.step.name}</h3>
      <p style={{ color: "#64748b", marginTop: 0, fontSize: 13, lineHeight: 1.5 }}>
        Tracked discussion between <strong>{parties.map((p) => p.label).join(" ↔ ")}</strong>.
        Every message is stored, visible to both, and part of the audit trail.
      </p>

      {/* Thread — all comments, both parties, oldest first. */}
      <div style={{ border: "1px solid #e6eaf0", borderRadius: 10, padding: 12, maxHeight: "40vh", overflowY: "auto", background: "#f8fafc" }}>
        {comments.length === 0 ? (
          <p style={{ color: "#94a3b8", fontSize: 13, margin: 4 }}>No messages yet — start the discussion below.</p>
        ) : (
          comments.map((c) => (
            <div key={c.id} style={{ background: "#fff", border: "1px solid #eef2f7", borderLeft: `3px solid ${partyColor(c)}`, borderRadius: 8, padding: "8px 10px", marginBottom: 8 }}>
              <div style={{ fontSize: 11, marginBottom: 3 }}>
                <span style={{ fontWeight: 700, color: partyColor(c) }}>{partyLabel(c)}</span>
                {c.author && <span style={{ color: "#94a3b8" }}> · {c.author}</span>}
                <span style={{ color: "#cbd5e1" }}> · {new Date(c.created_at).toLocaleString()}</span>
              </div>
              <div style={{ fontSize: 14, color: "#0f172a", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{c.content}</div>
            </div>
          ))
        )}
      </div>

      {/* Post a message — choose which side you are posting as. */}
      <div style={{ marginTop: 10 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6 }}>
          <span style={{ fontSize: 12, color: "#64748b" }}>Posting as:</span>
          {parties.map((p, i) => (
            <button
              key={i}
              onClick={() => setPartyIdx(i)}
              style={{
                padding: "4px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, cursor: "pointer",
                border: `1px solid ${partyIdx === i ? "#4f46e5" : "#cbd5e1"}`,
                background: partyIdx === i ? "#eef2ff" : "#fff", color: partyIdx === i ? "#3730a3" : "#334155",
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Write a message to the other party…"
          style={{ width: "100%", minHeight: 56, padding: "8px 10px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 14, boxSizing: "border-box" }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center" }}>
          <button style={{ ...btnPrimary, opacity: busy || !draft.trim() ? 0.5 : 1 }} disabled={busy || !draft.trim()} onClick={() => void post()}>
            {busy ? "Posting…" : "Post comment"}
          </button>
          <button style={btnGhost} onClick={() => void load()}>↻ Refresh</button>
        </div>
      </div>

      {/* Resolve & advance — config-driven gate. */}
      <div style={{ marginTop: 14, borderTop: "1px solid #f1f5f9", paddingTop: 12 }}>
        {canResolve ? (
          <button
            style={{ ...btnPrimary, background: "#16a34a" }}
            disabled={ctx.busy}
            onClick={() => resolveAction && ctx.onComplete(resolveAction.transition_id)}
          >
            {resolveAction?.label || "Mark resolved & continue"}
          </button>
        ) : (
          <p style={{ color: "#94a3b8", fontSize: 13, margin: 0 }}>
            {resolveAction
              ? `Only the ${resolveMode === "owner" ? "owner" : "assigned party"} can mark this discussion resolved.`
              : "The discussion will advance once it is resolved."}
          </p>
        )}
      </div>

      {err && <p style={{ marginTop: 10, color: "#b91c1c", fontSize: 13 }}>{err}</p>}
    </div>
  );
}

registerStepModule({
  key: "discussion",
  canAct: (ctx) => ownsAgreement(ctx.subjectRef), // resolve defaults to creator-owns
  render: (ctx) => <DiscussionPanel ctx={ctx} />,
});
