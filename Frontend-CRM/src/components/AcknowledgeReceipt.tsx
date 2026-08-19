import { useEffect, useRef, useState } from "react";

type Status = "loading" | "success" | "error";

// VITE_API_BASE is already "http://localhost:8000/api" — strip trailing /api so we
// can build the path ourselves without doubling the prefix.
const RAW_BASE = ((import.meta as any).env?.VITE_API_BASE ?? "") as string;
const API_ORIGIN = RAW_BASE.replace(/\/api\/?$/, "");

export default function AcknowledgeReceipt() {
  const [status, setStatus] = useState<Status>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const hasFetched = useRef(false);

  useEffect(() => {
    if (hasFetched.current) return;
    hasFetched.current = true;

    const params = new URLSearchParams(window.location.search);
    const token = params.get("token") ?? "";

    if (!token) {
      setErrorMessage("No acknowledgment token was found in the link. Please check your email and try again.");
      setStatus("error");
      return;
    }

    fetch(`${API_ORIGIN}/api/monitor/acknowledge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        if (res.ok) {
          setStatus("success");
        } else {
          const json = await res.json().catch(() => ({}));
          setErrorMessage(
            (json as any)?.detail || "This link is invalid or has already been used."
          );
          setStatus("error");
        }
      })
      .catch(() => {
        setErrorMessage("A network error occurred. Please check your connection and try again.");
        setStatus("error");
      });
  }, []);

  return (
    <div style={styles.page}>
      {/* Logo */}
      <div style={styles.logoRow}>
        <div style={styles.logoDot} />
        <span style={styles.logoText}>Dizzaroo CRM</span>
      </div>

      {/* Card */}
      <div style={styles.card}>
        {status === "loading" && <LoadingState />}
        {status === "success" && <SuccessState />}
        {status === "error"   && <ErrorState message={errorMessage} />}
      </div>

      <p style={styles.footer}>
        © {new Date().getFullYear()} Dizzaroo CRM · Secure Clinical Research Management
      </p>
    </div>
  );
}

// ─── State views ──────────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div style={styles.stateWrap}>
      <div style={styles.spinnerRing} />
      <h2 style={{ ...styles.heading, color: "#1e293b" }}>Verifying your acknowledgment…</h2>
      <p style={styles.sub}>Please wait while we securely record your receipt.</p>
    </div>
  );
}

function SuccessState() {
  return (
    <div style={styles.stateWrap}>
      <div style={{ ...styles.iconCircle, background: "#dcfce7", border: "2px solid #86efac" }}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="11" stroke="#16a34a" strokeWidth="1.5" />
          <path d="M7 12.5l3.5 3.5 6-7" stroke="#16a34a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <h2 style={{ ...styles.heading, color: "#15803d" }}>Thank You!</h2>
      <p style={styles.sub}>
        Your receipt of the Follow-up Letter has been successfully recorded for our audit trail.
      </p>
      <p style={{ ...styles.sub, marginTop: 8, fontStyle: "italic", color: "#64748b" }}>
        You may now close this window.
      </p>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div style={styles.stateWrap}>
      <div style={{ ...styles.iconCircle, background: "#fee2e2", border: "2px solid #fca5a5" }}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="11" stroke="#dc2626" strokeWidth="1.5" />
          <path d="M12 7v5" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" />
          <circle cx="12" cy="16.5" r="1" fill="#dc2626" />
        </svg>
      </div>
      <h2 style={{ ...styles.heading, color: "#b91c1c" }}>Link Unavailable</h2>
      <p style={styles.sub}>{message}</p>
      <p style={{ ...styles.sub, marginTop: 8, color: "#64748b", fontSize: 13 }}>
        If you believe this is an error, please contact the assigned monitor directly.
      </p>
    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #f0f4ff 0%, #e8f5f0 100%)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "24px 16px",
    fontFamily: "'Inter', 'Segoe UI', sans-serif",
  },
  logoRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 32,
  },
  logoDot: {
    width: 32,
    height: 32,
    borderRadius: "50%",
    background: "linear-gradient(135deg, #2E5496 0%, #0F6E56 100%)",
  },
  logoText: {
    fontSize: 20,
    fontWeight: 700,
    color: "#1e293b",
    letterSpacing: "-0.02em",
  },
  card: {
    background: "#ffffff",
    borderRadius: 16,
    boxShadow: "0 8px 40px rgba(0,0,0,0.10)",
    padding: "48px 40px",
    width: "100%",
    maxWidth: 460,
    textAlign: "center",
  },
  stateWrap: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 16,
  },
  iconCircle: {
    width: 88,
    height: 88,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 4,
  },
  spinnerRing: {
    width: 64,
    height: 64,
    borderRadius: "50%",
    border: "4px solid #e2e8f0",
    borderTopColor: "#2E5496",
    animation: "spin 0.9s linear infinite",
    marginBottom: 4,
  },
  heading: {
    fontSize: 22,
    fontWeight: 700,
    margin: 0,
    letterSpacing: "-0.01em",
  },
  sub: {
    fontSize: 15,
    color: "#475569",
    lineHeight: 1.6,
    margin: 0,
    maxWidth: 360,
  },
  footer: {
    marginTop: 28,
    fontSize: 12,
    color: "#94a3b8",
  },
};

// Inject spinner keyframes once
if (typeof document !== "undefined") {
  const id = "__ack-spinner-style";
  if (!document.getElementById(id)) {
    const s = document.createElement("style");
    s.id = id;
    s.textContent = "@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }";
    document.head.appendChild(s);
  }
}
