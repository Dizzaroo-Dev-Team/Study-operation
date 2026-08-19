// runner/notifyModule.tsx
// Module "notify": a (typically headless) step that fires a REAL in-app notification
// then advances. Reuses the existing in-app notice (POST /agreements/{id}/notify ->
// create_agreement_notice). When reached, it auto-fires once and advances on the
// step's forward transition; on failure it reports and offers a retry.

import React from "react";
import { api } from "@/lib/api";
import { registerStepModule, ModuleActions, type StepModuleContext } from "./modules";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const card: React.CSSProperties = { border: "1px solid #e2e8f0", borderRadius: 12, padding: 20, background: "#fff", maxWidth: 560 };

function NotifyPanel({ ctx }: { ctx: StepModuleContext }) {
  const aid = ctx.subjectRef;
  const isAgreement = !!aid && UUID_RE.test(aid);
  const [state, setState] = React.useState<"idle" | "firing" | "done" | "failed">("idle");
  const ranRef = React.useRef(false);

  const fire = React.useCallback(async () => {
    if (!isAgreement) return;
    setState("firing");
    try {
      const r = await api.post(`/agreements/${aid}/notify`, {}).then((x) => x.data);
      if (r?.fired) {
        setState("done");
        // Advance on the step's FORWARD transition. Don't assume actions[0] — pick the
        // first non-backward action so a step that also exposes a reject/send-back
        // can't accidentally advance down the wrong edge.
        const fwd = ctx.actions.find((a) => !["reject", "send_back", "decline"].includes(a.action)) ?? ctx.actions[0];
        if (fwd) ctx.onComplete(fwd.transition_id);
      } else {
        setState("failed");
      }
    } catch {
      setState("failed");
    }
  }, [aid, isAgreement, ctx]);

  React.useEffect(() => {
    if (ranRef.current || !isAgreement) return;
    ranRef.current = true;
    void fire();
  }, [fire, isAgreement]);

  return (
    <div style={card}>
      <h3 style={{ marginTop: 0 }}>{ctx.step.name}</h3>
      {!isAgreement ? (
        <>
          <p style={{ color: "#94a3b8" }}>No agreement to notify (sandbox). Advance manually:</p>
          <ModuleActions ctx={ctx} />
        </>
      ) : state === "failed" ? (
        <>
          <p style={{ color: "#b91c1c" }}>Notification failed to send.</p>
          <button onClick={() => { ranRef.current = true; void fire(); }}
                  style={{ padding: "9px 16px", background: "#4f46e5", color: "#fff", border: "none", borderRadius: 8, fontWeight: 600, cursor: "pointer" }}>
            Retry
          </button>
        </>
      ) : (
        <p style={{ color: state === "done" ? "#166534" : "#64748b" }}>
          {state === "done" ? "Notification sent — advancing…" : "Sending notification…"}
        </p>
      )}
    </div>
  );
}

registerStepModule({
  key: "notify",
  canAct: () => true, // headless; the engine forward transition gates advancement
  render: (ctx) => <NotifyPanel ctx={ctx} />,
});
