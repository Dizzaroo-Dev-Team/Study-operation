import { useEffect, useRef } from "react";
import { renderAsync } from "docx-preview";

type DocxPreviewModalProps = {
  blob: Blob;
  fileName: string;
  onClose: () => void;
};

export function DocxPreviewModal({ blob, fileName, onClose }: DocxPreviewModalProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !blob) return;

    container.innerHTML = "";
    void renderAsync(blob, container, undefined, {
      inWrapper: true,
      ignoreWidth: false,
      ignoreHeight: false,
      breakPages: true,
    });
  }, [blob]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 2000,
        background: "rgba(15, 23, 42, 0.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
      }}
    >
      <div
        style={{
          width: "80%",
          height: "90%",
          background: "#fff",
          borderRadius: "12px",
          boxShadow: "0 20px 60px rgba(2, 6, 23, 0.3)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: "14px 18px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            background: "#f8fafc",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#1e293b" }}>Preview Document</div>
            <div
              style={{
                fontSize: 12,
                color: "#64748b",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={fileName}
            >
              {fileName}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close preview"
            style={{
              border: "none",
              background: "transparent",
              fontSize: 20,
              color: "#475569",
              cursor: "pointer",
              lineHeight: 1,
              padding: "4px 8px",
              borderRadius: 6,
            }}
          >
            ×
          </button>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: "20px", background: "#f1f5f9" }}>
          <div ref={containerRef} />
        </div>

        <div
          style={{
            padding: "12px 18px",
            borderTop: "1px solid #e2e8f0",
            display: "flex",
            justifyContent: "flex-end",
            background: "#fff",
          }}
        >
          <button
            onClick={onClose}
            style={{
              border: "1px solid #cbd5e1",
              background: "#fff",
              color: "#334155",
              borderRadius: 8,
              padding: "9px 14px",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Close Preview
          </button>
        </div>
      </div>
    </div>
  );
}
