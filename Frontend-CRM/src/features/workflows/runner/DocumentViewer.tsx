// runner/DocumentViewer.tsx
// ONE shared document viewer every step renderer uses, so the user SEES the document
// at every step — always the CURRENT/latest version. It reuses the EXISTING
// OnlyOfficeEditor + the existing `agreements/{id}/onlyoffice-config` endpoint (which
// already serves _latest_agreement_document and cache-busts its key), so after a
// signature it shows the SIGNED version, after a review the reviewed version — never
// a stale pre-action copy. No new document pipeline.
//
// `refreshKey` (pass the instance's updated_at) forces a remount when the engine
// advances/records, so the viewer re-fetches the latest version when the doc "comes
// back to the owner". A manual Refresh is also provided. When the document does not
// exist yet at a very early step, it shows a graceful "preparing…" (reusing the
// existing create-from-template ensure) instead of a broken editor.

import React from "react";
import { api } from "@/lib/api";
import OnlyOfficeEditor from "@/components/OnlyOfficeEditor";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const btnOutline: React.CSSProperties = {
  padding: "5px 11px", background: "#fff", color: "#4338ca", border: "1px solid #c7d2fe",
  borderRadius: 8, fontWeight: 600, cursor: "pointer", fontSize: 12,
};

export function DocumentViewer({
  subjectRef,
  instanceId,
  stepId,
  canEdit = false,
  ensure = false,
  ensureTemplateId,
  refreshKey,
  height = "60vh",
}: {
  /** The agreement id (instance.subject_ref). */
  subjectRef: string | null;
  instanceId: number | string;
  stepId: string;
  /** Read-only preview by default (review/sign/approval); the draft step edits. */
  canEdit?: boolean;
  /** Only the draft/create step should ensure the working doc exists. */
  ensure?: boolean;
  ensureTemplateId?: string;
  /** Pass instance.updated_at — when it changes (engine advanced / signature recorded)
   *  the editor remounts and re-fetches the latest version. */
  refreshKey?: string | number;
  height?: string;
}) {
  const isAgreement = !!subjectRef && UUID_RE.test(subjectRef);
  const [state, setState] = React.useState<"preparing" | "ready" | "failed">(ensure ? "preparing" : "ready");
  const [err, setErr] = React.useState("");
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    if (!isAgreement || !ensure) { if (isAgreement) setState("ready"); return; }
    let alive = true;
    setState("preparing"); setErr("");
    (async () => {
      try {
        const fd = new FormData();
        if (ensureTemplateId) fd.append("template_id", ensureTemplateId);
        await api.post(`/agreements/${subjectRef}/create-from-template`, fd);
        if (alive) setState("ready");
      } catch (e: any) {
        // 400 = "already has a document" -> it exists, show it.
        if (alive) {
          if (e?.response?.status === 400) setState("ready");
          else { setErr(e?.response?.data?.detail || "Could not prepare the document."); setState("failed"); }
        }
      }
    })();
    return () => { alive = false; };
  }, [isAgreement, ensure, ensureTemplateId, subjectRef]);

  if (!isAgreement) {
    return (
      <div style={{ border: "1px dashed #cbd5e1", borderRadius: 10, padding: 24, margin: "14px 0", color: "#94a3b8", textAlign: "center", fontSize: 13, background: "#f8fafc" }}>
        Document available once the agreement exists.
      </div>
    );
  }
  if (state === "failed") {
    return (
      <div style={{ border: "1px solid #fecaca", background: "#fef2f2", color: "#b91c1c", borderRadius: 10, padding: 16, margin: "14px 0", fontSize: 13 }}>
        Could not prepare the document. {err}
      </div>
    );
  }
  if (state === "preparing") {
    return (
      <div style={{ border: "1px dashed #cbd5e1", borderRadius: 10, padding: 24, margin: "14px 0", color: "#94a3b8", textAlign: "center", fontSize: 13, background: "#f8fafc" }}>
        Preparing document…
      </div>
    );
  }

  return (
    <div style={{ margin: "14px 0" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.3, textTransform: "uppercase", color: canEdit ? "#4338ca" : "#64748b", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: 999, background: canEdit ? "#4f46e5" : "#94a3b8", display: "inline-block" }} />
          {canEdit ? "Document — editable" : "Document — current version (read-only)"}
        </span>
        <button style={{ ...btnOutline, marginLeft: "auto" }} onClick={() => setTick((t) => t + 1)} title="Reload the latest version">
          Refresh document
        </button>
      </div>
      <div style={{ width: "100%", height, minHeight: 380, border: "1px solid #e6eaf0", borderRadius: 10, overflow: "hidden", boxShadow: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)", background: "#fff" }}>
        {/* React key includes refreshKey + tick so a real change (engine advance /
            signature) or a manual Refresh remounts -> re-fetches the LATEST version. */}
        <OnlyOfficeEditor
          key={`oo-${subjectRef}-${stepId}-${refreshKey ?? ""}-${tick}`}
          agreementId={subjectRef as string}
          canEdit={canEdit}
          editorContainerId={`oo-${instanceId}-${stepId}-${tick}`}
        />
      </div>
      {/* No separate comments panel: reviewer comments now round-trip INSIDE the OnlyOffice
          document (native comments). On send-back the reviewed copy — which carries the
          comment thread — is promoted to the latest version (see unified_review.respond),
          so this editor opens with the comments shown. The owner Accepts (edit + resolve)
          or Rejects (reply with reason) in OnlyOffice; the DB extraction still runs silently
          for the audit trail. */}
    </div>
  );
}
