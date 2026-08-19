import { useState, useCallback } from "react";
import type { Toast } from "../../types";

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const showToast = useCallback((msg: string, type = "info") => {
    const id = Date.now();
    setToasts(p => [...p, { id, msg, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3200);
  }, []);
  const removeToast = useCallback((id: number) => setToasts(p => p.filter(t => t.id !== id)), []);
  return { toasts, showToast, removeToast };
}

export function ToastContainer({ toasts, removeToast }: { toasts: Toast[]; removeToast: (id: number) => void }) {
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.type === "success" ? "success" : t.type === "error" ? "error" : ""}`}
          style={{ animation: "toastIn .3s cubic-bezier(.34,1.56,.64,1)" }}>
          <span className="toast-icon">{t.type === "success" ? "✅" : t.type === "error" ? "❌" : "ℹ️"}</span>
          {t.msg}
          <button className="toast-close" onClick={() => removeToast(t.id)}>✕</button>
        </div>
      ))}
    </div>
  );
}
