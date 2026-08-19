import React from "react";
import { createPortal } from "react-dom";

export function Modal({ open, title, subtitle, icon, onClose, children, footer, maxWidth }: {
  open: boolean; title: React.ReactNode; onClose: () => void;
  subtitle?: React.ReactNode; icon?: React.ReactNode; maxWidth?: number | string;
  children: React.ReactNode; footer: React.ReactNode;
}) {
  if (!open) return null;
  return createPortal(
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={maxWidth ? { maxWidth } : undefined}>
        <div className={icon || subtitle ? "modal-header modal-header--accent" : "modal-header"}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
            {icon && <div className="modal-header-icon" aria-hidden="true">{icon}</div>}
            <div style={{ minWidth: 0 }}>
              <div className="modal-title">{title}</div>
              {subtitle && <div className="modal-subtitle">{subtitle}</div>}
            </div>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="modal-body">{children}</div>
        <div className="modal-footer">{footer}</div>
      </div>
    </div>,
    document.body
  );
}
