// runner/signingModule.tsx
// The first REAL capability module: unified SIGNING. Registered under key "signing"
// (one registry entry, no runner changes). Importing this file registers it.
//
// Runner/owner view ONLY: it shows slot status and lets the AGREEMENT CREATOR send
// the secure signing link to the open slot(s) (creator-owns). The actual signing
// happens on the REUSED AgreementSignPage (the emailed token link) — the engine is
// advanced SERVER-SIDE when a real signature is recorded, reflected here on refresh.
// There is NO bare "sign" button.

import React from "react";
import { api } from "@/lib/api";
import UserPicker from "@/components/UserPicker";
import { registerStepModule, ownsAgreement, type StepModuleContext } from "./modules";
import { DocumentViewer } from "./DocumentViewer";

type Slot = {
  id: string; name: string; state: "signed" | "open" | "pending"; email: string | null;
  /** Resolved up-front contact (stored email or what the assignee resolves to). */
  contact: string | null;
  /** True -> contact is known: auto-dispatch, no manual box. False on an open slot -> manual fallback. */
  auto: boolean;
  /** An active signing link already exists for this slot. */
  sent: boolean;
};
type SignStatus = { step: string; type: string; ordered: boolean; handoff: string; slots: Slot[] };

const box: React.CSSProperties = { border: "1px solid #e6eaf0", borderRadius: 12, padding: 20, margin: "12px 0", background: "#fff", boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)" };
const btnPrimary: React.CSSProperties = { padding: "8px 14px", background: "#4f46e5", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: "pointer", boxShadow: "0 1px 2px rgba(79,70,229,0.18)" };
const btnOutline: React.CSSProperties = { padding: "6px 12px", background: "#fff", color: "#4338ca", border: "1px solid #c7d2fe", borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: "pointer" };
const recipientInput: React.CSSProperties = { padding: "7px 10px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 13, width: 200 };

function dot(state: Slot["state"]) {
  return state === "signed" ? "✓" : state === "open" ? "→" : "•";
}
function color(state: Slot["state"]) {
  return state === "signed" ? "#16a34a" : state === "open" ? "#4f46e5" : "#cbd5e1";
}

function SigningPanel({ ctx }: { ctx: StepModuleContext }) {
  const agreementId = ctx.subjectRef;
  const [status, setStatus] = React.useState<SignStatus | null>(null);
  const [isOwner, setIsOwner] = React.useState(false);
  const [emails, setEmails] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<string>("");
  const [err, setErr] = React.useState<string>("");
  // NEED 2: the engine offers a "decline" action for the current signer when the step
  // has a signing_declined path; if it requires_comment, a reason is mandatory.
  const declineAction = ctx.actions.find((a) => a.action === "decline");
  const [showDecline, setShowDecline] = React.useState(false);
  const [declineReason, setDeclineReason] = React.useState("");
  const attachRef = React.useRef<HTMLInputElement>(null);

  const load = React.useCallback(async () => {
    if (!agreementId) return;
    try {
      const s = await api.get<SignStatus>(`/agreements/${agreementId}/sign/status`).then((r) => r.data);
      setStatus(s);
      // seed recipient inputs from any stored emails
      setEmails((prev) => {
        const next = { ...prev };
        s.slots.forEach((sl) => { if (sl.email && !next[sl.id]) next[sl.id] = sl.email; });
        return next;
      });
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Could not load signing status.");
    }
  }, [agreementId]);

  React.useEffect(() => {
    void load();
    if (agreementId) ownsAgreement(agreementId).then(setIsOwner);
  }, [load, agreementId]);

  // DocuSign-style AUTO-DISPATCH: when the signing step is reached and an OPEN slot's
  // contact is resolvable up front (assignee/role), auto-send its link with NO manual
  // step. Owner-triggered (dispatch is creator-owns); fires once per panel load. Slots
  // 2..N are auto-dispatched server-side by the engine's auto-handoff on each signature,
  // so this only needs to bootstrap the first open slot.
  const autoSentRef = React.useRef(false);
  React.useEffect(() => {
    if (!status || !isOwner || !agreementId || autoSentRef.current) return;
    const needsAuto = status.slots.some((s) => s.state === "open" && s.auto && !s.sent);
    if (!needsAuto) return;
    autoSentRef.current = true;
    api.post(`/agreements/${agreementId}/sign/dispatch`, { recipients: {} })
      .then(() => { void load(); ctx.onReload?.(); })
      .catch(() => { autoSentRef.current = false; });
  }, [status, isOwner, agreementId, load]);

  const dispatchSlot = async (slotId: string, emailOverride?: string) => {
    if (!agreementId) return;
    const email = (emailOverride || emails[slotId] || "").trim();
    if (!email) { setErr("Enter or pick a recipient first."); return; }
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await api.post(`/agreements/${agreementId}/sign/dispatch`, { recipients: { [slotId]: email } }).then((x) => x.data);
      setMsg(`Signing link sent (${(r.dispatched || []).map((d: any) => `${d.slot}:${d.status}`).join(", ")}).`);
      await load();
      ctx.onReload?.();  // also refresh the parent runner stepper / available actions
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Failed to send the signing link.");
    } finally {
      setBusy(false);
    }
  };

  const handleAttachExecuted = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f || !agreementId) return;
    setBusy(true); setErr(""); setMsg("");
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await api.post(`/agreements/${agreementId}/sign/attach-executed`, fd,
        { headers: { "Content-Type": "multipart/form-data" } }).then((x) => x.data);
      setMsg(`Executed document attached — signing completed (v${r.version ?? "?"}).`);
      await load();
      ctx.onReload?.();
    } catch (e2: any) {
      setErr(e2?.response?.data?.detail || "Failed to attach the executed document.");
    } finally {
      setBusy(false);
      if (attachRef.current) attachRef.current.value = "";
    }
  };

  if (!agreementId) {
    return <div style={box}>Signing is available once this agreement exists.</div>;
  }

  const slots = status?.slots ?? [];
  const signedCount = slots.filter((s) => s.state === "signed").length;

  return (
    <div style={box}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <strong style={{ color: "#0f172a", fontSize: 15, fontWeight: 700 }}>Signatures</strong>
        <span style={{ fontSize: 12, color: "#64748b" }}>
          {status ? `${status.ordered ? "ordered" : "parallel"} · ${status.handoff} handoff · ${signedCount}/${slots.length} signed` : "…"}
        </span>
        <button style={{ ...btnOutline, marginLeft: "auto" }} onClick={() => { void load(); void ctx.onReload?.(); }}>Refresh</button>
      </div>

      {/* The document being signed — current version; shows the SIGNED artifact after
          each signature (refreshKey = instance.updated_at remounts on engine change). */}
      <DocumentViewer subjectRef={agreementId} instanceId={ctx.instance.id} stepId={ctx.step.id}
                      canEdit={false} refreshKey={ctx.instance.updated_at} height="62vh" />

      <ul style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
        {slots.map((s, i) => (
          <li key={s.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 0", borderTop: i ? "1px solid #eef2f7" : "none" }}>
            <span style={{ width: 20, height: 20, flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", borderRadius: 999, background: `${color(s.state)}1a`, color: color(s.state), fontWeight: 700, fontSize: 12 }}>{dot(s.state)}</span>
            <span style={{ width: 160, fontSize: 14, color: "#1e293b", fontWeight: s.state === "open" ? 700 : 500 }}>
              {status?.ordered ? `${i + 1}. ` : ""}{s.name}
            </span>
            <span style={{ fontSize: 11.5, fontWeight: 600, color: s.state === "signed" ? "#15803d" : s.state === "open" ? "#4338ca" : "#94a3b8", background: s.state === "signed" ? "#ecfdf3" : s.state === "open" ? "#eef2ff" : "#f1f5f9", border: `1px solid ${s.state === "signed" ? "#bbf7d0" : s.state === "open" ? "#c7d2fe" : "#e2e8f0"}`, borderRadius: 999, padding: "2px 9px" }}>
              {s.state === "signed" ? "signed" : s.state === "open" ? "awaiting signature" : "pending"}
            </span>
            {/* OPEN slot: auto-sent state when the signer's contact is known up front;
                the manual recipient box appears ONLY as a fallback when it can't be
                resolved (no assignee contact). No "send" button next to a known contact. */}
            {s.state === "open" && (
              s.sent ? (
                // Link already out + awaiting this signer — NO resend button (would just
                // re-spam them). An expired link auto-re-dispatches; a signature advances
                // the slot. So the action returns only when the state genuinely changes.
                <span style={{ marginLeft: "auto", fontSize: 12, color: "#475569" }}>
                  Signing link sent{s.contact ? ` to ${s.contact}` : ""} — awaiting signature
                </span>
              ) : s.auto ? (
                <span style={{ marginLeft: "auto", fontSize: 12, color: "#4338ca" }}>
                  Sending signing link{s.contact ? ` to ${s.contact}` : ""}…
                </span>
              ) : isOwner ? (
                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
                  <input
                    type="email"
                    value={emails[s.id] || ""}
                    onChange={(e) => setEmails((p) => ({ ...p, [s.id]: e.target.value }))}
                    placeholder="signer@org.com"
                    style={recipientInput}
                  />
                  <div style={{ width: 200 }}>
                    <UserPicker
                      singleSelect
                      selectedUserEmails={emails[s.id] ? [emails[s.id]] : []}
                      onSelectionChange={(es) => setEmails((p) => ({ ...p, [s.id]: es[0] ?? "" }))}
                      placeholder="…or pick a user"
                    />
                  </div>
                  <button style={btnPrimary} disabled={busy} onClick={() => dispatchSlot(s.id)}>
                    Send for signature
                  </button>
                </div>
              ) : (
                <span style={{ marginLeft: "auto", fontSize: 12, color: "#94a3b8" }}>awaiting signer contact</span>
              )
            )}
          </li>
        ))}
      </ul>

      {/* Offline path: the agreement was signed OUTSIDE the system — the owner attaches the
          executed document and the engine completes signing (advances exactly like e-signing). */}
      {isOwner && slots.some((s) => s.state === "open") && (
        <div style={{ marginTop: 12, borderTop: "1px solid #eef2f7", paddingTop: 12 }}>
          <div style={{ fontSize: 12.5, color: "#334155", fontWeight: 600, marginBottom: 4 }}>Signed offline?</div>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
            If this was signed outside the system, attach the executed document to complete
            signing — it advances the workflow exactly like e-signing.
          </div>
          <input ref={attachRef} type="file" accept=".pdf,.doc,.docx" disabled={busy}
                 onChange={handleAttachExecuted} style={{ fontSize: 12 }} />
        </div>
      )}

      {status && status.ordered && status.handoff === "owner_gated" && isOwner && (
        <p style={{ marginTop: 12, color: "#475569", fontSize: 12.5, background: "#f8fafc", border: "1px solid #eef2f7", borderRadius: 8, padding: "8px 10px" }}>
          Ordered + owner-gated: the next signer stays locked until you send their link above.
        </p>
      )}

      {/* NEED 2 — the current signer may DECLINE with a mandatory reason. The reason
          is stored with the document + in the audit trail; routing stays send-back. */}
      {declineAction && (
        <div style={{ marginTop: 14, borderTop: "1px solid #eef2f7", paddingTop: 14 }}>
          {!showDecline ? (
            <button
              style={{ ...btnOutline, color: "#b91c1c", borderColor: "#fca5a5" }}
              onClick={() => setShowDecline(true)}
            >
              Decline to sign
            </button>
          ) : (
            <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, padding: 14 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "#b91c1c", marginBottom: 6 }}>
                Reason for declining {declineAction.requires_comment ? "(required)" : "(optional)"}
              </label>
              <textarea
                value={declineReason}
                onChange={(e) => setDeclineReason(e.target.value)}
                placeholder="Explain why you are declining to sign — this is stored with the document and the audit trail."
                style={{ width: "100%", minHeight: 64, padding: "9px 11px", border: "1px solid #fca5a5", borderRadius: 8, fontSize: 14, boxSizing: "border-box", background: "#fff" }}
              />
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button
                  style={{ ...btnPrimary, background: "#dc2626", boxShadow: "0 1px 2px rgba(220,38,38,0.2)", opacity: (declineAction.requires_comment && !declineReason.trim()) || ctx.busy ? 0.5 : 1 }}
                  disabled={(declineAction.requires_comment && !declineReason.trim()) || ctx.busy}
                  onClick={() => ctx.onComplete(declineAction.transition_id, {}, declineReason.trim() || undefined)}
                >
                  Submit decline
                </button>
                <button style={btnOutline} onClick={() => { setShowDecline(false); setDeclineReason(""); }}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}
      {msg && <p style={{ marginTop: 12, color: "#15803d", fontSize: 13, background: "#ecfdf3", border: "1px solid #bbf7d0", borderRadius: 8, padding: "8px 10px" }}>{msg}</p>}
      {err && <p style={{ marginTop: 12, color: "#b91c1c", fontSize: 13, background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "8px 10px" }}>{err}</p>}
      <p style={{ marginTop: 12, color: "#94a3b8", fontSize: 12, lineHeight: 1.5 }}>
        Each signer is emailed a secure link automatically (OTP + name + intent), and the
        next signer is notified the moment the previous one signs — no manual send. Where a
        signer's contact isn't on file, enter it above to send that one.
      </p>
    </div>
  );
}

// ── Register: one entry wires the capability for every step with module "signing".
registerStepModule({
  key: "signing",
  canAct: (ctx) => ownsAgreement(ctx.subjectRef), // dispatch/resend/handoff = creator-owns
  render: (ctx) => <SigningPanel ctx={ctx} />,
});
