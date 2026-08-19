/**
 * Message-list merge helpers — the single source of the "exactly-once" rule for
 * the open-conversation panel.
 *
 * Both the realtime append (instant) and the focus/reconnect self-heal (catch-up
 * refetch) funnel through these so a message can never render twice:
 *   - dedupe by message id,
 *   - reconcile an optimistic `temp-…` row with its real echo,
 *   - drop unconfirmed temps when the server set arrives.
 */
// Minimal shape these helpers need. Kept WITHOUT an index signature so the
// app's concrete `Message` type satisfies the `T extends MergeableMessage`
// constraint (a named type with no index signature is not assignable to one
// that has it), letting `T` infer as `Message` and the return stay `Message[]`.
export interface MergeableMessage {
  id: string
  body: string
  created_at: string
}

function byCreatedAt(a: MergeableMessage, b: MergeableMessage): number {
  return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
}

/**
 * Append one realtime message, guaranteeing it appears at most once:
 *  1. same id already present  -> replace in place (status/field updates),
 *  2. a matching optimistic `temp-` row (same body, within 5s) -> replace it,
 *  3. otherwise append.
 * Always returns a new, time-sorted array (or the same ref on no-op).
 */
export function appendRealtimeMessage<T extends MergeableMessage>(prev: T[], incoming: T): T[] {
  if (prev.some((p) => p.id === incoming.id)) {
    return prev
      .map((p) => (p.id === incoming.id ? incoming : p))
      .sort(byCreatedAt)
  }
  const tempIdx = prev.findIndex(
    (p) =>
      String(p.id).startsWith('temp-') &&
      p.body === incoming.body &&
      Math.abs(new Date(p.created_at).getTime() - new Date(incoming.created_at).getTime()) < 5000,
  )
  if (tempIdx !== -1) {
    const updated = [...prev]
    updated[tempIdx] = incoming
    return updated.sort(byCreatedAt)
  }
  return [...prev, incoming].sort(byCreatedAt)
}

/**
 * Merge an authoritative server message set into the current list. Drops
 * unconfirmed optimistic temps (the server is now the source of truth) and
 * dedupes by id, so a realtime-appended message and the same server message can
 * never both appear. Used by the focus / reconnect self-heal.
 */
export function mergeServerMessages<T extends MergeableMessage>(prev: T[], server: T[]): T[] {
  const byId = new Map<string, T>()
  for (const m of prev) {
    if (!String(m.id).startsWith('temp-')) byId.set(m.id, m)
  }
  for (const m of server) byId.set(m.id, m)
  return Array.from(byId.values()).sort(byCreatedAt)
}
