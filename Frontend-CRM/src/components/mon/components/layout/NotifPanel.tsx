import React, { useState, useEffect, useCallback, useRef } from "react";
import { Btn } from "../ui";
import { useNotifications, type Notification } from "@/lib/queries/useMonitoring";

// -----------------------------------------------------------------------------
// NotifItem — memoized row.
// Marking a single notification read used to re-render every other row in the
// panel; now only the row whose `unread` flipped re-renders.
// -----------------------------------------------------------------------------
interface NotifItemProps {
  notif: Notification;
  onMarkRead: (id: number) => void;
}

const NotifItemImpl: React.FC<NotifItemProps> = ({ notif, onMarkRead }) => {
  const handleClick = () => onMarkRead(notif.id);
  return (
    <div
      className={`notif-item${notif.unread ? " unread" : ""}`}
      onClick={handleClick}
    >
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <div className="notif-icon">{notif.icon}</div>
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: notif.unread ? 500 : 400,
              color: "var(--text-primary)",
            }}
          >
            {notif.text}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 3 }}>
            {notif.time}
          </div>
        </div>
        {notif.unread && (
          <div
            style={{
              width: 8,
              height: 8,
              background: "var(--blue)",
              borderRadius: "50%",
              flexShrink: 0,
              marginTop: 4,
            }}
          />
        )}
      </div>
    </div>
  );
};

const NotifItem = React.memo(NotifItemImpl, (prev, next) => {
  if (prev.onMarkRead !== next.onMarkRead) return false;
  if (prev.notif.id !== next.notif.id) return false;
  if (prev.notif.unread !== next.notif.unread) return false;
  if (prev.notif.text !== next.notif.text) return false;
  if (prev.notif.time !== next.notif.time) return false;
  if (prev.notif.icon !== next.notif.icon) return false;
  return true;
});

const READ_IDS_KEY = "mon_notif_read_ids";
const CLEARED_BEFORE_KEY = "mon_notif_cleared_before";

function getReadIds(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_IDS_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function saveReadIds(ids: Set<string>) {
  try {
    localStorage.setItem(READ_IDS_KEY, JSON.stringify([...ids]));
  } catch {
    // localStorage unavailable — silently ignore
  }
}

function getClearedBeforeIso(): string | null {
  try {
    const v = localStorage.getItem(CLEARED_BEFORE_KEY);
    return v && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

function setClearedBeforeNow() {
  try {
    localStorage.setItem(CLEARED_BEFORE_KEY, new Date().toISOString());
  } catch {
    // ignore
  }
}

function sortNotificationsNewestFirst(list: Notification[]): Notification[] {
  return [...list].sort((a, b) => {
    const sa = a.sort_at || "";
    const sb = b.sort_at || "";
    return sb.localeCompare(sa);
  });
}

function applyClearedBeforeFilter(list: Notification[]): Notification[] {
  const cleared = getClearedBeforeIso();
  if (!cleared) return list;
  return list.filter((n) => (n.sort_at ? n.sort_at > cleared : true));
}

export function NotifPanel({
  open,
  onClose,
  onMarkAll,
  onUnreadChange,
}: {
  open: boolean;
  onClose: () => void;
  onMarkAll?: () => void;
  onUnreadChange?: (count: number) => void;
}) {
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const notificationsQuery = useNotifications({
    enabled: open,
    refetchInterval: open ? 60_000 : false,
  });

  // Keep a ref so the load callback always sees the latest without re-creating
  const onUnreadChangeRef = useRef(onUnreadChange);
  onUnreadChangeRef.current = onUnreadChange;

  const mergeAndApply = useCallback((res: { notifications: Notification[] }) => {
    const readIds = getReadIds();
    let merged = res.notifications.map((n) => ({
      ...n,
      unread: n.unread && !readIds.has(String(n.id)),
    }));
    merged = sortNotificationsNewestFirst(merged);
    merged = applyClearedBeforeFilter(merged);
    setNotifs(merged);
    const unread = merged.filter((n) => n.unread).length;
    onUnreadChangeRef.current?.(unread);
  }, []);

  useEffect(() => {
    if (notificationsQuery.data) {
      mergeAndApply(notificationsQuery.data);
    }
  }, [notificationsQuery.data, mergeAndApply]);

  const loading = notificationsQuery.isPending;

  const unreadCount = notifs.filter((n) => n.unread).length;

  // useCallback-stable so the memoized NotifItem rows don't see a new
  // function identity on every parent re-render.
  const markRead = useCallback((id: number) => {
    setNotifs((prev) => {
      const updated = prev.map((n) => (n.id === id ? { ...n, unread: false } : n));
      const newUnread = updated.filter((n) => n.unread).length;
      onUnreadChangeRef.current?.(newUnread);
      // Persist
      const readIds = getReadIds();
      readIds.add(String(id));
      saveReadIds(readIds);
      return updated;
    });
  }, []);

  function clearAllNotifications() {
    setClearedBeforeNow();
    try {
      localStorage.removeItem(READ_IDS_KEY);
    } catch {
      // ignore
    }
    onUnreadChangeRef.current?.(0);
    void notificationsQuery.refetch();
  }

  function markAllRead() {
    setNotifs((prev) => {
      const updated = prev.map((n) => ({ ...n, unread: false }));
      // Persist all as read
      const readIds = getReadIds();
      updated.forEach((n) => readIds.add(String(n.id)));
      saveReadIds(readIds);
      onUnreadChangeRef.current?.(0);
      return updated;
    });
    onMarkAll?.();
  }

  return (
    <div className={`notif-panel${open ? "" : " hidden"}`}>
      <div className="notif-header">
        <div>
          <div className="notif-title">Notifications</div>
          {unreadCount > 0 && (
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{unreadCount} unread</div>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end", alignItems: "center" }}>
          {notifs.length > 0 && (
            <Btn
              variant="ghost"
              size="sm"
              onClick={clearAllNotifications}
              title="Dismiss all listed items. New alerts after this moment appear at the top."
            >
              Clear all
            </Btn>
          )}
          {unreadCount > 0 && (
            <Btn variant="ghost" size="sm" onClick={markAllRead}>
              Mark all read
            </Btn>
          )}
          <Btn variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Btn>
        </div>
      </div>

      <div style={{ overflowY: "auto", flex: 1 }}>
        {loading && notifs.length === 0 && (
          <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            Loading…
          </div>
        )}
        {!loading && notifs.length === 0 && (
          <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            No notifications right now.
          </div>
        )}
        {notifs.map((n) => (
          <NotifItem key={n.id} notif={n} onMarkRead={markRead} />
        ))}
      </div>
    </div>
  );
}
