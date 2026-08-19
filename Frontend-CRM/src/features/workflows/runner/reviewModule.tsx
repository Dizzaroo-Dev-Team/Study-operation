// runner/reviewModule.tsx
// Unified REVIEW/COMMENT capability module (key "review"). Importing this file
// registers it. One registry entry, no runner changes.
//
// Runner/owner view ONLY: shows the document in OnlyOffice + lets the CREATOR send
// it to a reviewer (creator-owns). The reviewer reviews + comments + approves /
// sends-back on the REUSED public review page (emailed link). The ENGINE owns the
// loop (approve -> forward, send_back -> edit); it advances SERVER-SIDE on the
// reviewer's real response, reflected here on refresh. The owner has NO approve
// button (cannot self-approve the reviewer's step).

import React from "react";
import { api } from "@/lib/api";
import UserPicker from "@/components/UserPicker";
import { registerStepModule, ownsAgreement, type StepModuleContext } from "./modules";
import { DocumentViewer } from "./DocumentViewer";

type ReviewStatus = { current_step: string | null; review_out: boolean; reviewer_email: string | null };

const box: React.CSSProperties = { border: "1px solid #e6eaf0", borderRadius: 12, padding: 20, margin: "12px 0", background: "#fff", boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)" };
const btnPrimary: React.CSSProperties = { padding: "8px 14px", background: "#4f46e5", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: "pointer", boxShadow: "0 1px 2px rgba(79,70,229,0.18)" };
const btnOutline: React.CSSProperties = { padding: "6px 12px", background: "#fff", color: "#4338ca", border: "1px solid #c7d2fe", borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: "pointer" };
const reviewerInput: React.CSSProperties = { padding: "7px 10px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 13 };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function ReviewPanel({ ctx }: { ctx: StepModuleContext }) {
  const agreementId = ctx.subjectRef;
  const isAgreement = !!agreementId && UUID_RE.test(agreementId);
  const [status, setStatus] = React.useState<ReviewStatus | null>(null);
  const [isOwner, setIsOwner] = React.useState(false);
  const [email, setEmail] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");

  const load = React.useCallback(async () => {
    if (!isAgreement) return;
    try {
      setStatus(await api.get<ReviewStatus>(`/agreements/${agreementId}/review/status`).then((r) => r.data));
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Could not load review status.");
    }
  }, [agreementId, isAgreement]);

  React.useEffect(() => {
    void load();
    if (isAgreement && agreementId) ownsAgreement(agreementId).then(setIsOwner);
  }, [load, agreementId, isAgreement]);

  const sendForReview = async () => {
    if (!email.trim()) { setErr("Enter or pick a reviewer first."); return; }
    setBusy(true); setErr(""); setMsg("");
    try {
      await api.post(`/agreements/${agreementId}/review/dispatch`, {
        recipient_email: email.trim(), message: message.trim() || null,
      });
      setMsg(`Sent for review to ${email.trim()}.`);
      await load();
      ctx.onReload?.();  // also refresh the parent runner stepper / available actions
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Failed to send for review.");
    } finally {
      setBusy(false);
    }
  };

  if (!isAgreement) {
    return <div style={box}>Review is available once this agreement exists.</div>;
  }

  return (
    <div style={box}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <strong style={{ color: "#0f172a", fontSize: 15, fontWeight: 700 }}>Review</strong>
        <span style={{ fontSize: 12, color: "#64748b" }}>
          {status?.review_out ? `out to ${status.reviewer_email} — awaiting their response` : "not sent yet"}
        </span>
        <button style={{ ...btnOutline, marginLeft: "auto" }} onClick={() => { void load(); void ctx.onReload?.(); }}>Refresh</button>
      </div>

      {/* Current document, always latest version (shows reviewer changes when it returns). */}
      <DocumentViewer subjectRef={agreementId} instanceId={ctx.instance.id} stepId={ctx.step.id}
                      canEdit={false} refreshKey={ctx.instance.updated_at} />

      {/* Owner-only: pick a reviewer (email OR existing user) and send. No approve
          button here — the reviewer approves/sends-back on the secure review link. */}
      {isOwner ? (
        status?.review_out ? (
          // Already out + awaiting a response: NO resend (would just re-spam the reviewer).
          // When they send it back, the workflow returns to editing and a fresh review step
          // re-enables sending. Resend only when the doc actually comes back.
          <div style={{ fontSize: 13, color: "#475569", background: "#f8fafc", border: "1px solid #eef2f7", borderRadius: 8, padding: "10px 12px" }}>
            Sent to <b>{status.reviewer_email}</b> — awaiting their response. If they send it
            back, it returns to editing for your revision and you can re-send then.
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="reviewer@org.com"
                   style={{ ...reviewerInput, width: 240 }} />
            <div style={{ width: 220 }}>
              <UserPicker singleSelect selectedUserEmails={email ? [email] : []}
                          onSelectionChange={(es) => setEmail(es[0] ?? "")} placeholder="…or pick a user" />
            </div>
            <input type="text" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Optional message"
                   style={{ ...reviewerInput, width: 260 }} />
            <button style={btnPrimary} disabled={busy} onClick={sendForReview}>Send for review</button>
          </div>
        )
      ) : (
        <p style={{ color: "#64748b", fontSize: 13 }}>Waiting for the reviewer to respond.</p>
      )}

      {msg && <p style={{ marginTop: 12, color: "#15803d", fontSize: 13, background: "#ecfdf3", border: "1px solid #bbf7d0", borderRadius: 8, padding: "8px 10px" }}>{msg}</p>}
      {err && <p style={{ marginTop: 12, color: "#b91c1c", fontSize: 13, background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "8px 10px" }}>{err}</p>}
      <p style={{ marginTop: 12, color: "#94a3b8", fontSize: 12, lineHeight: 1.5 }}>
        The reviewer comments and chooses Approve or Send back on the secure link emailed to them.
        Approve advances the workflow; Send back returns it to editing for your revision — then re-send.
      </p>
    </div>
  );
}

// ── PARALLEL multi-reviewer review (type=parallel + module=review) ───────────
// Mirrors the signing module's per-slot UI: one row per reviewer branch (e.g. Legal,
// Financial), each with a recipient picker + Send. Reviewers approve / send-back on
// their own emailed link; the engine advances on quorum (all approve) or loops to
// edit on any send-back. Owner has no approve button (cannot self-approve).
type Reviewer = { id: string; name: string; state: "approved" | "sent_back" | "open" | "pending"; email: string | null };
type ParallelStatus = { active: boolean; step?: string; quorum?: any; reviewers: Reviewer[] };

function rdot(s: Reviewer["state"]) { return s === "approved" ? "✓" : s === "sent_back" ? "↩" : s === "open" ? "→" : "•"; }
function rcolor(s: Reviewer["state"]) { return s === "approved" ? "#16a34a" : s === "sent_back" ? "#b45309" : s === "open" ? "#4f46e5" : "#cbd5e1"; }

function ParallelReviewPanel({ ctx }: { ctx: StepModuleContext }) {
  const agreementId = ctx.subjectRef;
  const isAgreement = !!agreementId && UUID_RE.test(agreementId);
  const [status, setStatus] = React.useState<ParallelStatus | null>(null);
  const [isOwner, setIsOwner] = React.useState(false);
  const [emails, setEmails] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");

  const load = React.useCallback(async () => {
    if (!isAgreement) return;
    try {
      const s = await api.get<ParallelStatus>(`/agreements/${agreementId}/review/parallel-status`).then((r) => r.data);
      setStatus(s);
      setEmails((prev) => {
        const next = { ...prev };
        (s.reviewers || []).forEach((rv) => { if (rv.email && !next[rv.id]) next[rv.id] = rv.email; });
        return next;
      });
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Could not load review status.");
    }
  }, [agreementId, isAgreement]);

  React.useEffect(() => {
    void load();
    if (isAgreement && agreementId) ownsAgreement(agreementId).then(setIsOwner);
  }, [load, agreementId, isAgreement]);

  const dispatchBranch = async (branchId: string) => {
    const email = (emails[branchId] || "").trim();
    if (!email) { setErr("Enter or pick a reviewer first."); return; }
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await api.post(`/agreements/${agreementId}/review/parallel-dispatch`,
        { recipients: { [branchId]: email } }).then((x) => x.data);
      setMsg(`Review link sent (${(r.dispatched || []).map((d: any) => `${d.branch}:${d.status}`).join(", ")}).`);
      await load();
      ctx.onReload?.();  // also refresh the parent runner stepper / available actions
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Failed to send the review link.");
    } finally {
      setBusy(false);
    }
  };

  if (!isAgreement) return <div style={box}>Review is available once this agreement exists.</div>;
  const reviewers = status?.reviewers ?? [];
  const approved = reviewers.filter((r) => r.state === "approved").length;

  return (
    <div style={box}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <strong style={{ color: "#0f172a", fontSize: 15, fontWeight: 700 }}>Parallel Review</strong>
        <span style={{ fontSize: 12, color: "#64748b" }}>{approved}/{reviewers.length} approved · all must approve to advance</span>
        <button style={{ ...btnOutline, marginLeft: "auto" }} onClick={() => { void load(); void ctx.onReload?.(); }}>Refresh</button>
      </div>

      <DocumentViewer subjectRef={agreementId} instanceId={ctx.instance.id} stepId={ctx.step.id}
                      canEdit={false} refreshKey={ctx.instance.updated_at} height="62vh" />

      <ul style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
        {reviewers.map((rv, i) => (
          <li key={rv.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 0", borderTop: i ? "1px solid #eef2f7" : "none" }}>
            <span style={{ width: 20, height: 20, flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", borderRadius: 999, background: `${rcolor(rv.state)}1a`, color: rcolor(rv.state), fontWeight: 700, fontSize: 12 }}>{rdot(rv.state)}</span>
            <span style={{ width: 160, fontSize: 14, color: "#1e293b", fontWeight: rv.state === "open" ? 700 : 500 }}>{rv.name}</span>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: rcolor(rv.state), background: `${rcolor(rv.state)}14`, border: `1px solid ${rcolor(rv.state)}33`, borderRadius: 999, padding: "2px 9px" }}>
              {rv.state === "approved" ? "approved" : rv.state === "sent_back" ? "sent back" : rv.state === "open" ? "awaiting review" : "pending"}
            </span>
            {/* Send only when actionable: a branch not yet sent, or one that CAME BACK
                (sent_back). An OPEN branch with a link already out shows "awaiting" — no
                resend, so the reviewer isn't re-spammed. */}
            {isOwner && (
              (rv.state === "open" && rv.email) ? (
                <span style={{ marginLeft: "auto", fontSize: 12, color: "#64748b" }}>
                  awaiting review — link sent to {rv.email}
                </span>
              ) : (rv.state === "open" || rv.state === "sent_back") ? (
                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
                  <input type="email" value={emails[rv.id] || ""} onChange={(e) => setEmails((p) => ({ ...p, [rv.id]: e.target.value }))}
                         placeholder="reviewer@org.com" style={{ ...reviewerInput, width: 190 }} />
                  <div style={{ width: 190 }}>
                    <UserPicker singleSelect selectedUserEmails={emails[rv.id] ? [emails[rv.id]] : []}
                                onSelectionChange={(es) => setEmails((p) => ({ ...p, [rv.id]: es[0] ?? "" }))} placeholder="…or pick a user" />
                  </div>
                  <button style={btnPrimary} disabled={busy} onClick={() => dispatchBranch(rv.id)}>
                    {rv.state === "sent_back" ? "Re-send for review" : "Send for review"}
                  </button>
                </div>
              ) : null
            )}
          </li>
        ))}
      </ul>

      {msg && <p style={{ marginTop: 12, color: "#15803d", fontSize: 13, background: "#ecfdf3", border: "1px solid #bbf7d0", borderRadius: 8, padding: "8px 10px" }}>{msg}</p>}
      {err && <p style={{ marginTop: 12, color: "#b91c1c", fontSize: 13, background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "8px 10px" }}>{err}</p>}
      <p style={{ marginTop: 12, color: "#94a3b8", fontSize: 12, lineHeight: 1.5 }}>
        Each reviewer approves or sends back on their secure link. The workflow advances only when
        ALL reviewers approve; any send-back returns it to editing for your revision — then re-send.
      </p>
    </div>
  );
}

registerStepModule({
  key: "review",
  canAct: (ctx) => ownsAgreement(ctx.subjectRef), // send/resend = creator-owns
  // A parallel step with module="review" = multi-reviewer; otherwise single review.
  render: (ctx) => (String((ctx.step as any)?.type) === "parallel"
    ? <ParallelReviewPanel ctx={ctx} />
    : <ReviewPanel ctx={ctx} />),
});
