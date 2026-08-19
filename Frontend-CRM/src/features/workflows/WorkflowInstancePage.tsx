// WorkflowInstancePage.tsx
// Route host for the runner: /workflows/instances/:id. The Task Inbox links
// here; the page is just a thin chrome (back link) around WorkflowRunner.

import { useNavigate, useParams } from "react-router-dom";
import { WorkflowRunner } from "./runner/WorkflowRunner";

export default function WorkflowInstancePage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const instanceId = Number(id);

  if (!Number.isFinite(instanceId) || instanceId <= 0) {
    return <div style={{ padding: 24, color: "#b91c1c" }}>Invalid workflow instance id.</div>;
  }
  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 24px",
                    borderBottom: "1px solid #e2e8f0", background: "#fff" }}>
        <button
          onClick={() => navigate("/workflows/inbox")}
          style={{ padding: "6px 12px", borderRadius: 8, border: "1px solid #cbd5e1",
                   background: "#fff", color: "#334155", cursor: "pointer", fontWeight: 600, fontSize: 13 }}
        >
          ← Task inbox
        </button>
        <span style={{ fontSize: 12, color: "#94a3b8" }}>workflow instance #{instanceId}</span>
      </div>
      {/* key by instanceId so navigating between instances remounts the runner —
          otherwise the cached workflow definition (and other per-instance state)
          would leak from the previously viewed instance. */}
      <WorkflowRunner key={instanceId} instanceId={instanceId} />
    </div>
  );
}
