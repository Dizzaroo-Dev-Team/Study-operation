// Conceptual agreement workflow helpers
// Maps backend AgreementStatus values to user-friendly stages for the UI.

export type AgreementStage = 'PREPARATION' | 'REVIEW' | 'SIGNATURE' | 'COMPLETED'

/**
 * Map raw backend status string to conceptual UI stage.
 *
 * NOTE:
 * - We do NOT change backend enums or database values.
 * - This function is purely a presentation layer helper.
 */
export function getAgreementStage(status: string | null | undefined): AgreementStage {
  if (!status) return 'PREPARATION'
  const normalized = status.toUpperCase()

  if (normalized === 'DRAFT') return 'PREPARATION'

  // UNDER_REVIEW is the primary review stage; UNDER_NEGOTIATION is a legacy alias
  // that maps to the same conceptual stage (negotiation happens inside Review).
  // CTA-only states AWAITING_INTERNAL_REVIEW / INTERNAL_REVIEW_APPROVED also map
  // to REVIEW — the reviewer is acting (or has acted) on the document.
  if (
    normalized === 'UNDER_REVIEW' ||
    normalized === 'UNDER_NEGOTIATION' ||
    normalized === 'REVIEWED_AND_SIGNED' ||
    normalized === 'AWAITING_INTERNAL_REVIEW' ||
    normalized === 'INTERNAL_REVIEW_APPROVED'
  ) return 'REVIEW'

  if (
    normalized === 'READY_FOR_SIGNATURE' ||
    normalized === 'SENT_FOR_SIGNATURE' ||
    normalized === 'AWAITING_SPONSOR_SIGNATURE'
  ) {
    return 'SIGNATURE'
  }

  if (normalized === 'FULLY_SIGNED' || normalized === 'EXECUTED' || normalized === 'CLOSED') {
    return 'COMPLETED'
  }

  // Fallback: treat unknown states as preparation
  return 'PREPARATION'
}

/**
 * Linear CRM workflow (internal UI): one primary action per conceptual stage.
 * Backend statuses stay unchanged (DRAFT, UNDER_REVIEW, READY_FOR_SIGNATURE, …).
 */
export type PrimaryWorkflowAction =
  | 'mark_ready_send_review'
  | 'complete_review'
  | 'send_signature'
  | 'sync_signature'
  | 'none'

export function getPrimaryWorkflowAction(status: string | null | undefined): PrimaryWorkflowAction {
  const normalized = (status || '').toUpperCase()
  const stage = getAgreementStage(status)

  if (stage === 'PREPARATION' && normalized === 'DRAFT') {
    return 'mark_ready_send_review'
  }
  if (
    stage === 'REVIEW' &&
    (
      normalized === 'UNDER_REVIEW' ||
      normalized === 'UNDER_NEGOTIATION' ||
      normalized === 'REVIEWED_AND_SIGNED'
    )
  ) {
    return 'complete_review'
  }
  if (stage === 'SIGNATURE' && normalized === 'READY_FOR_SIGNATURE') {
    return 'send_signature'
  }
  if (stage === 'SIGNATURE' && normalized === 'SENT_FOR_SIGNATURE') {
    return 'sync_signature'
  }
  return 'none'
}

/** True when the agreement can receive another review invitation (same API as initial send). */
export function canResendReviewInvitation(status: string | null | undefined): boolean {
  const n = (status || '').toUpperCase()
  return n === 'UNDER_REVIEW' || n === 'UNDER_NEGOTIATION'
}

export function getStageLabel(stage: AgreementStage): string {
  switch (stage) {
    case 'PREPARATION':
      return 'Agreement Preparation'
    case 'REVIEW':
      return 'Agreement Review'
    case 'SIGNATURE':
      return 'Agreement Signature'
    case 'COMPLETED':
      return 'Completed'
    default:
      return 'Agreement Preparation'
  }
}

/**
 * Workflow steps that own the panel's primary call-to-action button.
 * One token per step the user can advance from.
 */
export type WorkflowActionStep =
  | 'setup'
  | 'fill_placeholders'
  | 'internal_review'
  | 'ready_for_signature'

/**
 * Single source of truth for the primary action button label at each workflow step.
 * Centralises what used to be four string literals hardcoded across the panel, so the
 * label progression (Setup → Send for Internal Review → Approve → Send for Signature)
 * lives in one place and is driven by the step rather than a static string. Wording is
 * unchanged from the prior inline literals — only the source of truth moved. Mirrors
 * the existing getStageLabel() pattern; generic, no document-type branching.
 */
export function getPrimaryActionLabel(step: WorkflowActionStep): string {
  switch (step) {
    case 'setup':
      return 'Save & Continue'
    case 'fill_placeholders':
      return 'Submit & Send for Internal Review'
    case 'internal_review':
      return 'Approve'
    case 'ready_for_signature':
      return 'Send for Signature'
    default:
      return 'Continue'
  }
}

/**
 * Returns true when the agreement is in the conceptual negotiation/review stage.
 * Internally this is backed by the UNDER_REVIEW status.
 */
export function isNegotiationStage(status: string | null | undefined): boolean {
  const stage = getAgreementStage(status)
  return stage === 'REVIEW'
}

// ---------------------------------------------------------------------------
// Agreement Timeline Helpers
// ---------------------------------------------------------------------------

/**
 * Event categories used in the activity timeline.
 *
 * There are exactly three categories:
 *   'workflow'    — high-level agreement lifecycle events shown in the Activity Timeline.
 *                   Examples: Agreement created, Sent for review, Sent for signature.
 *   'version'     — document version creation events shown in the Version History section.
 *                   Examples: Version 1 created, Version 3 created.
 *   'negotiation' — change detection / acceptance / rejection events shown in the
 *                   External Changes panel.
 *                   Examples: External change detected, Change accepted.
 *
 * NOTE: 'comment' is intentionally absent. The system does not support human comments
 * in the activity timeline.
 */
export type AgreementTimelineKind = 'workflow' | 'version' | 'negotiation'

export interface AgreementTimelineItem {
  id: string
  timestamp: string
  label: string
  description?: string
  kind: AgreementTimelineKind
}

// ---------------------------------------------------------------------------
// Internal input types (matches shapes returned by the agreement API)
// ---------------------------------------------------------------------------

type TimelineAgreement = {
  created_at?: string
  title?: string
  documents?: Array<{
    id: string
    created_at?: string
    version_number?: number
    created_by?: string | null
  }>
  comments?: Array<{
    id: string
    comment_type: string
    content: string
    created_at: string
    created_by: string | null
    version_id?: string | null
  }>
}

// ---------------------------------------------------------------------------
// Filtering helpers
// ---------------------------------------------------------------------------

/**
 * Returns true if a SYSTEM comment represents a workflow milestone that should
 * appear in the Activity Timeline (not in Version History or the changes panel).
 *
 * Excluded patterns (handled elsewhere):
 *   - "Version N created …"           → Version History section
 *   - "Review submitted by external"  → External Changes panel
 *   - "change(s) detected"            → External Changes panel
 *   - "accepted … change"             → External Changes panel
 *   - "rejected … change"             → External Changes panel
 */
function isWorkflowComment(content: string): boolean {
  if (content == null || typeof content !== 'string') return false
  const lower = content.toLowerCase()

  // Exclude document version creation events (shown in Version History section)
  if (/version \d+ created/.test(lower)) return false

  // Exclude granular change-detection / accept / reject events
  // (shown in the External Changes panel, not here)
  if (lower.includes('change(s) detected')) return false
  if (/accepted .* change/.test(lower)) return false
  if (/rejected .* change/.test(lower)) return false

  // "Review submitted by external site" IS a workflow milestone — keep it.
  // "External change recorded / detected" are granular negotiation events — exclude.
  if (lower.includes('external change recorded')) return false
  if (lower.includes('external change detected')) return false

  // Everything else from SYSTEM comments is a workflow event
  return true
}

/**
 * Map a SYSTEM comment's content to a user-friendly label.
 * Returns null if the comment should not appear in the timeline.
 */
function systemCommentToLabel(content: string): string | null {
  if (content == null || typeof content !== 'string') return null
  const lower = content.toLowerCase()

  if (lower.includes('sent for review') || lower.includes('agreement sent for review')) {
    return 'Sent for review'
  }
  // External reviewer submitted their edits — this IS a workflow milestone
  if (lower.includes('review submitted by external')) {
    return 'External review submitted'
  }
  if (lower.includes('reviewed and signed by external reviewer')) {
    return 'External reviewer approved'
  }
  if (lower.includes('sent for signature') || lower.includes('agreement sent for signature')) {
    return 'Sent for signature'
  }
  if (lower.includes('executed')) {
    return 'Agreement executed'
  }
  if (lower.includes('fully signed')) {
    return 'Agreement fully signed'
  }
  if (lower.includes('closed')) {
    return 'Agreement closed'
  }
  if (lower.includes('ready for signature') || lower.includes('ready_for_signature')) {
    return 'Moved to ready for signature'
  }
  if (lower.includes('draft created') || lower.includes('created from template')) {
    return 'Draft created from template'
  }
  if (lower.includes('status changed') || lower.includes('moved to')) {
    return 'Status updated'
  }

  // Generic system event label for any other workflow-related SYSTEM comment
  return 'System event'
}

// ---------------------------------------------------------------------------
// Public API — Activity Timeline (WORKFLOW events only)
// ---------------------------------------------------------------------------

/**
 * Build the Activity Timeline for an agreement.
 *
 * Returns ONLY workflow-level events:
 *   • Agreement created
 *   • Draft created from template
 *   • Sent for review
 *   • Sent for signature
 *   • Agreement executed / closed
 *   • Other SYSTEM comments that represent workflow milestones
 *
 * Does NOT include:
 *   • Document version creation events  → use buildVersionHistory()
 *   • Negotiation / change events       → use the External Changes panel (allChanges)
 *   • Human comments (not supported)
 *
 * This is a pure helper — no API calls are made.
 */
export function buildAgreementTimeline(
  agreement: TimelineAgreement | null | undefined,
): AgreementTimelineItem[] {
  if (!agreement) return []

  const items: AgreementTimelineItem[] = []

  // ── 1. Agreement created ─────────────────────────────────────────────────
  if (agreement.created_at) {
    items.push({
      id: 'agreement-created',
      timestamp: agreement.created_at,
      label: 'Agreement created',
      description: agreement.title,
      kind: 'workflow',
    })
  }

  // ── 2. SYSTEM comments that are workflow milestones ───────────────────────
  // Excludes version-creation comments and negotiation-related comments.
  if (agreement.comments && agreement.comments.length > 0) {
    agreement.comments.forEach((comment) => {
      const { id, comment_type, content, created_at } = comment

      // Only process SYSTEM comments; skip INTERNAL / EXTERNAL (human comments)
      if (comment_type !== 'SYSTEM') return

      // Skip if this comment belongs to a different category
      if (!isWorkflowComment(content)) return

      const label = systemCommentToLabel(content)
      if (!label) return

      items.push({
        id: `workflow-${id}`,
        timestamp: created_at,
        label,
        description: content,
        kind: 'workflow',
      })
    })
  }

  // ── Sort chronologically ──────────────────────────────────────────────────
  return items
    .filter((item) => !!item.timestamp)
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
}

// ---------------------------------------------------------------------------
// Public API — Version History (VERSION events only)
// ---------------------------------------------------------------------------

/**
 * Build the Version History list for an agreement.
 *
 * Returns one item per AgreementDocument version.
 * Shown in the Version History section, NOT in the Activity Timeline.
 */
export function buildVersionHistory(
  agreement: TimelineAgreement | null | undefined,
): AgreementTimelineItem[] {
  if (!agreement?.documents || agreement.documents.length === 0) return []

  return agreement.documents
    .filter((doc) => !!doc.created_at)
    .map((doc) => ({
      id: `version-${doc.id}`,
      timestamp: doc.created_at!,
      label:
        typeof doc.version_number === 'number'
          ? `Version ${doc.version_number} created`
          : 'Document version created',
      description: doc.created_by || undefined,
      kind: 'version' as AgreementTimelineKind,
    }))
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
}
