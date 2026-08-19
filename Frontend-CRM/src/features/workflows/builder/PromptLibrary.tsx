// builder/PromptLibrary.tsx
// A collapsed-by-default shelf of ready-made prompts shown above the
// "Describe your workflow" box in the builder's AI panel. Picking one drops its
// text into the description (via onPick) so the user can edit + generate, instead
// of writing a prompt from scratch. Purely presentational — no data fetching.

import { PROMPT_LIBRARY } from "./promptLibraryData";

export function PromptLibrary({ onPick }: { onPick: (text: string) => void }) {
  return (
    <details style={{ marginBottom: 8 }}>
      <summary style={{ cursor: "pointer", fontSize: 12, color: "#475569", fontWeight: 600 }}>
        📚 Start from a prompt ({PROMPT_LIBRARY.length})
      </summary>
      <div style={{ fontSize: 12, color: "#64748b", margin: "6px 0 8px" }}>
        Pick a starting point, then tweak the text and generate.
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {PROMPT_LIBRARY.map((p) => (
          <button
            key={p.id}
            type="button"
            title={p.text}
            onClick={() => onPick(p.text)}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-start",
              gap: 2,
              maxWidth: 240,
              textAlign: "left",
              padding: "7px 11px",
              borderRadius: 10,
              border: "1px solid #cbd5e1",
              background: "#fff",
              color: "#334155",
              cursor: "pointer",
            }}
          >
            <span style={{ fontSize: 13, fontWeight: 700, color: "#3730a3" }}>{p.label}</span>
            <span style={{ fontSize: 11.5, color: "#64748b" }}>{p.blurb}</span>
          </button>
        ))}
      </div>
    </details>
  );
}
