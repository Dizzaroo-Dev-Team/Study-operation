// definitions/VersionHistory.tsx
// Modal showing one workflow's full version history (newest first) with the metadata
// that already exists — who published each version and when. Each row can be made the
// published default, or cloned into the builder as a new workflow starting from that
// exact version. Read-only fetch + two existing endpoints (publish, clone-via-builder);
// no new global state.

import React from "react";
import { workflowApi } from "../api";
import type { DefinitionVersionSummary } from "../types";
import { ui } from "../runner/steps/common";

function fmt(ts?: string | null): string {
  if (!ts) return "";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString();
}

export function VersionHistory({
  defKey,
  title,
  onClose,
  onClone,
  onPublished,
}: {
  defKey: string;
  /** Human-friendly heading (template/workflow name). The raw defKey is never shown. */
  title?: string;
  onClose: () => void;
  onClone: (key: string, version: number) => void;
  onPublished: () => void; // tell the parent to refresh its list
}) {
  const [versions, setVersions] = React.useState<DefinitionVersionSummary[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoading(true);
    workflowApi
      .listVersions(defKey)
      .then((v) => setVersions(v))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [defKey]);

  React.useEffect(() => { load(); }, [load]);

  const publish = async (version: number) => {
    setBusy(true);
    setError(null);
    try {
      await workflowApi.publish(defKey, version);
      load();          // refresh the modal's badges
      onPublished();   // refresh the library list behind it
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff", borderRadius: 12, padding: 20, width: 560, maxWidth: "92vw",
          maxHeight: "82vh", overflowY: "auto", boxShadow: "0 10px 40px rgba(16,24,40,0.25)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <h3 style={{ margin: 0 }}>{title || "Workflow"} — version history</h3>
          <button style={{ ...ui.btnDanger, padding: "4px 10px" }} onClick={onClose}>Close</button>
        </div>
        <p style={{ color: "#64748b", fontSize: 13, marginTop: 4 }}>
          Every saved version. Publish makes one the default for new agreements; clone starts a new
          workflow from that version.
        </p>

        {error && (
          <div style={{ margin: "8px 0", padding: "8px 10px", background: "#fef2f2", color: "#b91c1c", borderRadius: 8, fontSize: 13 }}>
            {error}
          </div>
        )}

        {loading ? (
          <p>Loading…</p>
        ) : versions.length === 0 ? (
          <p style={{ color: "#94a3b8" }}>No versions yet.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {versions.map((v) => (
              <div
                key={v.version}
                style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "10px 12px",
                  border: "1px solid #e2e8f0", borderRadius: 10,
                  background: v.is_published ? "#f0fdf4" : "#fff",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 700 }}>v{v.version}</span>
                    {v.is_published ? (
                      <span style={{ ...ui.badge, background: "#dcfce7", color: "#166534" }}>published</span>
                    ) : (
                      <span style={{ ...ui.badge, background: "#f1f5f9", color: "#64748b" }}>draft</span>
                    )}
                    <span style={{ color: "#334155", fontSize: 13 }}>{v.name}</span>
                  </div>
                  <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 2 }}>
                    {v.published_at ? `Published · ${fmt(v.published_at)}` : `Created · ${fmt(v.created_at)}`}
                  </div>
                  {/* The prompt this version was authored from. Clone/edit pre-fills
                      it in the builder's description box. */}
                  {v.source_prompt && (
                    <div
                      title={v.source_prompt}
                      style={{
                        color: "#64748b", fontSize: 12, marginTop: 4, fontStyle: "italic",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}
                    >
                      ✨ “{v.source_prompt}”
                    </div>
                  )}
                </div>
                {!v.is_published && (
                  <button
                    style={{ ...ui.btnPrimary, padding: "6px 12px", background: "#16a34a" }}
                    onClick={() => publish(v.version)}
                    disabled={busy}
                  >
                    Publish
                  </button>
                )}
                <button
                  style={{ ...ui.btnDanger, color: "#4f46e5", borderColor: "#c7d2fe", padding: "6px 12px" }}
                  onClick={() => onClone(defKey, v.version)}
                  disabled={busy}
                >
                  Clone
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
