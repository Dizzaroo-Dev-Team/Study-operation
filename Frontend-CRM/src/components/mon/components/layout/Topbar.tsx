import type { BreadcrumbItem } from "../../types";

export function Topbar({ breadcrumb, onNavigate, onNotifToggle, notifOpen, unreadCount }: {
  breadcrumb: BreadcrumbItem[];
  onNavigate: (view: string) => void;
  onNotifToggle: () => void;
  notifOpen: boolean;
  unreadCount: number;
}) {
  return (
    <header className="mon-topbar">
      <div className="mon-breadcrumb">
        {breadcrumb.map((b, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {i > 0 && <span className="mon-breadcrumb-sep">›</span>}
            {b.view
              ? <span onClick={() => onNavigate(b.view!)}>{b.label}</span>
              : <span className="mon-breadcrumb-current">{b.label}</span>}
          </div>
        ))}
      </div>
      <div className="mon-topbar-right" style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button type="button" className="mon-icon-btn" aria-expanded={notifOpen} onClick={onNotifToggle}>
          🔔{unreadCount > 0 && <span className="mon-notif-dot" />}
        </button>
      </div>
    </header>
  );
}
