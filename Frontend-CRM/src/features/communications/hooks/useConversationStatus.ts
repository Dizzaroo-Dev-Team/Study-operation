import { Conversation, ConversationStatus, Message } from '@/types'

export type DerivedStatus =
  | 'notice-board'       // persistent public notice board for the site/study
  | 'needs-reply'        // last inbound message, recent → user owes a reply
  | 'awaiting-reply'     // last outbound message, recent → counterpart owes a reply
  | 'stale'              // no activity in 7+ days
  | 'no-messages'        // freshly created, nothing sent yet
  | 'snoozed'            // explicit snooze; not until snooze_until is in future
  | 'resolved'           // explicit resolved
  | 'closed'             // explicit closed

export interface DerivedStatusInfo {
  status: DerivedStatus
  label: string
  /** Tailwind classes for the status pill (background + text + border). */
  pillClass: string
  /** Tailwind classes for a small left-edge dot only. */
  dotClass: string
  /** Section title used by the grouped sidebar. */
  sectionTitle: string
  /** Sort weight — lower is higher up in the sidebar. */
  weight: number
  /** Hours since the most recent message, or null when there are no messages. */
  hoursSinceLastMessage: number | null
}

const STALE_THRESHOLD_DAYS = 7

const STATUS_META: Record<DerivedStatus, Omit<DerivedStatusInfo, 'hoursSinceLastMessage'>> = {
  'notice-board': {
    status: 'notice-board',
    label: 'Notice board',
    pillClass: 'bg-brand-50 text-brand-700 border-brand-500/30',
    dotClass: 'bg-brand-500',
    sectionTitle: 'Notice board',
    weight: -1,  // sits above every other section
  },
  'needs-reply': {
    status: 'needs-reply',
    label: 'Needs your reply',
    pillClass: 'bg-danger-50 text-danger-600 border-danger-500/30',
    dotClass: 'bg-danger-500',
    sectionTitle: 'Needs your reply',
    weight: 0,
  },
  'awaiting-reply': {
    status: 'awaiting-reply',
    label: 'Awaiting reply',
    pillClass: 'bg-warning-50 text-warning-600 border-warning-500/30',
    dotClass: 'bg-warning-500',
    sectionTitle: 'Awaiting their reply',
    weight: 1,
  },
  'stale': {
    status: 'stale',
    label: 'No update 7d+',
    pillClass: 'bg-slate-100 text-slate-600 border-slate-300',
    dotClass: 'bg-slate-400',
    sectionTitle: 'No update in 7 days',
    weight: 2,
  },
  'no-messages': {
    status: 'no-messages',
    label: 'Just created',
    pillClass: 'bg-brand-50 text-brand-600 border-brand-500/30',
    dotClass: 'bg-brand-500',
    sectionTitle: 'Just created',
    weight: 3,
  },
  'snoozed': {
    status: 'snoozed',
    label: 'Snoozed',
    pillClass: 'bg-slate-100 text-slate-500 border-slate-300',
    dotClass: 'bg-slate-300',
    sectionTitle: 'Snoozed',
    weight: 4,
  },
  'resolved': {
    status: 'resolved',
    label: 'Resolved',
    pillClass: 'bg-accent-50 text-accent-600 border-accent-500/30',
    dotClass: 'bg-accent-500',
    sectionTitle: 'Resolved',
    weight: 5,
  },
  'closed': {
    status: 'closed',
    label: 'Closed',
    pillClass: 'bg-slate-100 text-slate-500 border-slate-300',
    dotClass: 'bg-slate-400',
    sectionTitle: 'Closed',
    weight: 6,
  },
}

/**
 * Map the persisted backend `ConversationStatus` to the visual `DerivedStatus`
 * the UI renders. `awaiting_us` (backend) → `needs-reply` (UI) and
 * `awaiting_reply` (backend) → `awaiting-reply` (UI); the wording change is
 * deliberate (the UI is user-centric, the backend is content-centric).
 */
const STATUS_FROM_BACKEND: Partial<Record<ConversationStatus, DerivedStatus>> = {
  awaiting_us: 'needs-reply',
  awaiting_reply: 'awaiting-reply',
  snoozed: 'snoozed',
  resolved: 'resolved',
  closed: 'closed',
  // `open` falls through to inference so age/direction can refine the bucket.
}

/**
 * Resolve a conversation's display status.
 *
 * Resolution order (first match wins):
 *   1. If the conversation is the persistent public notice board (created by
 *      the system and pinned to a site/study) → `notice-board`. These are not
 *      operational items — they're an always-on broadcast surface.
 *   2. If a snooze is active (`snooze_until` in the future) → `snoozed`.
 *   3. If the conversation has a persisted `status` other than `open` →
 *      map via `STATUS_FROM_BACKEND`.
 *   4. Otherwise infer from the last message direction + recency.
 */
export function deriveConversationStatus(
  lastMessage: Message | undefined,
  fallbackUpdatedAt?: string | Date,
  conversation?: Pick<
    Conversation,
    'status' | 'snooze_until' | 'conversation_type' | 'is_pinned' | 'created_by'
  >,
): DerivedStatusInfo {
  const now = Date.now()
  const lastTimeRaw = lastMessage?.created_at ?? fallbackUpdatedAt
  const lastTime = lastTimeRaw ? new Date(lastTimeRaw).getTime() : NaN
  const ageHours = isNaN(lastTime) ? null : (now - lastTime) / 3600_000

  // (1) Public notice board — always its own bucket. Note: the backend
  // defaults `conversation_type` to `'notice_board'` on EVERY new conversation,
  // so that field is useless for detection. The real notice board is created
  // by `ensure_public_notice_board` with `is_pinned == 'true'` AND
  // `created_by == 'system'`; only those land in this bucket.
  if (conversation) {
    const isPinned = String(conversation.is_pinned || '').toLowerCase() === 'true'
    const isSystem = String(conversation.created_by || '').toLowerCase() === 'system'
    if (isPinned && isSystem) {
      return { ...STATUS_META['notice-board'], hoursSinceLastMessage: ageHours }
    }
  }

  // (2) Active snooze beats everything else.
  if (conversation?.snooze_until) {
    const snoozeMs = new Date(conversation.snooze_until).getTime()
    if (!isNaN(snoozeMs) && snoozeMs > now) {
      return { ...STATUS_META['snoozed'], hoursSinceLastMessage: ageHours }
    }
  }

  // (3) Persisted backend status (skip `open` to let inference refine it).
  if (conversation?.status && conversation.status !== 'open') {
    const mapped = STATUS_FROM_BACKEND[conversation.status]
    if (mapped) {
      return { ...STATUS_META[mapped], hoursSinceLastMessage: ageHours }
    }
  }

  // (3) Fall through to inference.
  if (!lastMessage || ageHours === null) {
    return { ...STATUS_META['no-messages'], hoursSinceLastMessage: null }
  }
  const ageDays = ageHours / 24
  if (ageDays >= STALE_THRESHOLD_DAYS) {
    return { ...STATUS_META['stale'], hoursSinceLastMessage: ageHours }
  }
  const direction = String(lastMessage.direction || '').toLowerCase()
  if (direction === 'inbound') {
    return { ...STATUS_META['needs-reply'], hoursSinceLastMessage: ageHours }
  }
  return { ...STATUS_META['awaiting-reply'], hoursSinceLastMessage: ageHours }
}

export function formatAge(hours: number | null): string {
  if (hours === null || isNaN(hours)) return '—'
  if (hours < 1) return `${Math.max(1, Math.floor(hours * 60))}m`
  if (hours < 24) return `${Math.floor(hours)}h`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d`
  const weeks = Math.floor(days / 7)
  return `${weeks}w`
}
