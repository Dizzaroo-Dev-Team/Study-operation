// runner/broadcastModule.tsx
// Module "broadcast" (distribute final copy): REAL per-recipient delivery. The
// engine only RECORDS recipients; this does the actual fan-out by reusing
// enqueue_email (POST /agreements/{id}/broadcast). Owner-triggered ("Send to all",
// creator-owns); reports per-recipient success, then advances on completion.

import React from "react";
import { api } from "@/lib/api";
import { registerStepModule, ModuleActions, ownsAgreement, type StepModuleContext } from "./modules";
import { DocumentViewer } from "./DocumentViewer";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const card: React.CSSProperties = { border: "1px solid #e6eaf0", borderRadius: 12, padding: 20, background: "#fff", maxWidth: "100%", margin: "12px 0", boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)" };
const btn: React.CSSProperties = { padding: "9px 16px", background: "#4f46e5", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, fontSize: 14, cursor: "pointer", boxShadow: "0 1px 2px rgba(79,70,229,0.18)" };

type Recip = { id: string; name: string };
type Result = { recipient: string; email: string | null; sent: boolean; reason?: string };

function BroadcastPanel({ ctx }: { ctx: StepModuleContext }) {
  const aid = ctx.subjectRef;
  const isAgreement = !!aid && UUID_RE.test(aid);
  const cfg = (ctx.step.config?.recipients as any[]) || [];
  const recipients: Recip[] = cfg.map((r) => ({ id: String(r.id), name: String(r.name || r.id) }));
  const [emails, setEmails] = React.useState<Record<string, string>>({});
  const [isOwner, setIsOwner] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [results, setResults] = React.useState<Result[] | null>(null);
  const [err, setErr] = React.useState("");

  React.useEffect(() => { if (isAgreement && aid) ownsAgreement(aid).then(setIsOwner); }, [aid, isAgreement]);

  const sendAll = async () => {
    setBusy(true); setErr("");
    try {
      const payload = {
        recipients: recipients.map((r) => ({ name: r.name, email: (emails[r.id] || "").trim() })),
        attach_document: true,
      };
      const r = await api.post(`/agreements/${aid}/broadcast`, payload).then((x) => x.data);
      const out: Result[] = r.results || [];
      // Only advance if at least one recipient actually received the document. If
      // EVERY send failed (e.g. SMTP down / all addresses bad), advancing would
      // complete the distribution step with nobody reached — keep the step open
      // (results cleared) so the owner can fix addresses and retry.
      if (out.some((x) => x.sent)) {
        setResults(out);
        const fwd = ctx.actions.find((a) => !["reject", "send_back", "decline"].includes(a.action)) ?? ctx.actions[0];
        if (fwd) ctx.onComplete(fwd.transition_id);
      } else {
        setResults(null);
        setErr("No recipients could be reached — nothing was sent. Check the email addresses and try again.");
      }
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Broadcast failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={card}>
      <h3 style={{ marginTop: 0, marginBottom: 8, fontSize: 16, fontWeight: 700, color: "#0f172a" }}>{ctx.step.name}</h3>
      {!isAgreement ? (
        <><p style={{ color: "#94a3b8" }}>No agreement (sandbox). Advance manually:</p><ModuleActions ctx={ctx} /></>
      ) : (
        <>
          {/* The final signed artifact being distributed — latest version. */}
          <DocumentViewer subjectRef={aid} instanceId={ctx.instance.id} stepId={ctx.step.id}
                          canEdit={false} refreshKey={ctx.instance.updated_at} height="58vh" />
          <p style={{ color: "#475569", marginTop: 0 }}>Distribute the final copy to {recipients.length} recipients:</p>
          <ul style={{ listStyle: "none", padding: 0, margin: "10px 0" }}>
            {recipients.map((r, i) => {
              const res = results?.find((x) => x.recipient === r.name);
              return (
                <li key={r.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderTop: i ? "1px solid #eef2f7" : "none" }}>
                  <span style={{ width: 160, fontSize: 14, color: "#1e293b", fontWeight: 500 }}>{r.name}</span>
                  {res ? (
                    <span style={{ fontSize: 12, fontWeight: 600, color: res.sent ? "#15803d" : "#b91c1c", background: res.sent ? "#ecfdf3" : "#fef2f2", border: `1px solid ${res.sent ? "#bbf7d0" : "#fecaca"}`, borderRadius: 999, padding: "2px 9px" }}>
                      {res.sent ? `✓ sent → ${res.email}` : `✗ ${res.reason || "failed"}`}
                    </span>
                  ) : isOwner ? (
                    <input type="email" value={emails[r.id] || ""} onChange={(e) => setEmails((p) => ({ ...p, [r.id]: e.target.value }))}
                           placeholder={`${r.name} email`} style={{ padding: "7px 10px", border: "1px solid #cbd5e1", borderRadius: 8, fontSize: 13, width: 240 }} />
                  ) : (
                    <span style={{ fontSize: 12, color: "#94a3b8" }}>pending</span>
                  )}
                </li>
              );
            })}
          </ul>
          {isOwner && !results && (
            <button style={btn} disabled={busy} onClick={sendAll}>{busy ? "Sending…" : "Send to all recipients"}</button>
          )}
          {results && (
            <p style={{ color: "#15803d", fontSize: 13, marginTop: 10, background: "#ecfdf3", border: "1px solid #bbf7d0", borderRadius: 8, padding: "8px 10px" }}>
              Sent {results.filter((r) => r.sent).length}/{results.length} — advancing…
            </p>
          )}
          {err && <p style={{ color: "#b91c1c", fontSize: 13, marginTop: 10, background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "8px 10px" }}>{err}</p>}
        </>
      )}
    </div>
  );
}

registerStepModule({
  key: "broadcast",
  canAct: (ctx) => ownsAgreement(ctx.subjectRef), // "send to all" = creator-owns
  render: (ctx) => <BroadcastPanel ctx={ctx} />,
});
