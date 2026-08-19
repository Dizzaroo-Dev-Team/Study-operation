import { PrimarySiteStatus, SiteStatusDetail, ControlStage, StageProgress } from '@/features/sites/types/siteStatus'

/** Human-readable label for Site Status tab / Control Tower primary status (matches SiteHeaderBanner). */
export function formatPrimarySiteStatusLabel(status?: PrimarySiteStatus | null): string {
  if (!status) return 'Under Evaluation'
  switch (status) {
    case 'UNDER_EVALUATION':
      return 'Under Evaluation'
    case 'STARTUP':
      return 'Under Start-up'
    case 'INITIATING':
      return 'Initiating'
    case 'INITIATED_NOT_RECRUITING':
      return 'Initiated – Not Yet Recruiting'
    case 'RECRUITING':
      return 'Open for Recruitment'
    case 'ACTIVE_NOT_RECRUITING':
      return 'Active – Not Recruiting'
    case 'SUSPENDED':
      return 'Suspended'
    case 'TERMINATED':
      return 'Terminated'
    case 'WITHDRAWN':
      return 'Withdrawn'
    case 'COMPLETED':
      return 'Completed'
    case 'CLOSED':
      return 'Closed (Site Close-out Completed)'
    default:
      return String(status).replace(/_/g, ' ')
  }
}

/**
 * Maps raw PrimarySiteStatus to Control Tower stage
 * This is a UI-level mapping - does NOT change backend status values
 */
export function mapRawStatusToControlStage(
  rawStatus: PrimarySiteStatus | null | undefined,
  metadata?: Record<string, any> | null
): ControlStage {
  if (!rawStatus) {
    return 'under_consideration'
  }

  switch (rawStatus) {
    case 'UNDER_EVALUATION':
      return 'under_consideration'
    case 'STARTUP':
      return 'startup_site_selection'
    case 'INITIATING':
      return 'enrollment_initiation'
    case 'INITIATED_NOT_RECRUITING':
      return 'initiated_post_siv'
    case 'RECRUITING':
      return 'open_for_recruitment'
    case 'ACTIVE_NOT_RECRUITING':
      return 'active_not_recruiting'
    case 'CLOSED':
    case 'COMPLETED':
      return 'closed_final'
    case 'SUSPENDED':
    case 'TERMINATED':
    case 'WITHDRAWN':
      // These map to "On Hold" overlay - determine base stage from metadata
      // If we have metadata with previous stage, use that
      if (metadata?.previous_stage) {
        return metadata.previous_stage as ControlStage
      }
      // Try to get from previous_status in metadata (raw status value)
      if (metadata?.previous_status) {
        const prevStatus = metadata.previous_status as PrimarySiteStatus
        // Map the previous status directly (avoid recursion by checking it's not a hold status)
        if (prevStatus !== 'SUSPENDED' && prevStatus !== 'TERMINATED' && prevStatus !== 'WITHDRAWN') {
          return mapRawStatusToControlStage(prevStatus, null)
        }
      }
      // Default fallback - return a valid stage (will be marked as on hold separately)
      return 'under_consideration'
    default:
      return 'under_consideration'
  }
}

/**
 * Checks if a site is in "On Hold" state
 */
export function isOnHold(rawStatus: PrimarySiteStatus | null | undefined): boolean {
  if (!rawStatus) return false
  return rawStatus === 'SUSPENDED' || rawStatus === 'TERMINATED' || rawStatus === 'WITHDRAWN'
}

/**
 * Gets the stage order number (0-based)
 */
export function getStageOrder(stage: ControlStage): number {
  const orderMap: Record<ControlStage, number> = {
    under_consideration: 0,
    startup_site_selection: 1,
    enrollment_initiation: 2,
    initiated_post_siv: 3,
    open_for_recruitment: 4,
    active_not_recruiting: 5,
    on_hold: -1, // Special case - overlay
    closed_final: 6,
  }
  return orderMap[stage] ?? 0
}

/**
 * Gets all stages in order (excluding on_hold as it's an overlay)
 */
export function getAllStagesInOrder(): ControlStage[] {
  return [
    'under_consideration',
    'startup_site_selection',
    'enrollment_initiation',
    'initiated_post_siv',
    'open_for_recruitment',
    'active_not_recruiting',
    'closed_final',
  ]
}

/**
 * Calculates stage progress from site status detail
 */
export function getStageProgress(siteDetail: SiteStatusDetail | null): StageProgress {
  if (!siteDetail || !siteDetail.current_status) {
    return {
      currentStage: 'under_consideration',
      completedStages: [],
      isOnHold: false,
      stageOrder: 0,
    }
  }

  const currentStage = mapRawStatusToControlStage(
    siteDetail.current_status,
    siteDetail.secondary_statuses || null
  )
  const onHold = isOnHold(siteDetail.current_status)
  const currentOrder = getStageOrder(currentStage)

  // Determine completed stages based on history
  const completedStages: ControlStage[] = []
  const allStages = getAllStagesInOrder()

  // If current stage is valid (not on_hold), mark previous stages as completed
  if (currentOrder >= 0) {
    for (let i = 0; i < currentOrder; i++) {
      completedStages.push(allStages[i])
    }
  } else {
    // If on hold, try to determine base stage from history
    if (siteDetail.history && siteDetail.history.length > 0) {
      // Find last non-suspended/terminated/withdrawn status
      for (let i = siteDetail.history.length - 1; i >= 0; i--) {
        const histStatus = siteDetail.history[i].status
        if (!isOnHold(histStatus)) {
          const baseStage = mapRawStatusToControlStage(histStatus)
          const baseOrder = getStageOrder(baseStage)
          for (let j = 0; j < baseOrder; j++) {
            completedStages.push(allStages[j])
          }
          break
        }
      }
    }
  }

  return {
    currentStage: onHold ? 'on_hold' : currentStage,
    completedStages,
    isOnHold: onHold,
    stageOrder: currentOrder >= 0 ? currentOrder : 0,
  }
}

/**
 * Gets the base stage when on hold (removes on_hold overlay)
 */
export function getBaseStage(stage: ControlStage, siteDetail: SiteStatusDetail | null): ControlStage {
  if (stage !== 'on_hold') {
    return stage
  }

  // Try to get base stage from history
  if (siteDetail?.history && siteDetail.history.length > 0) {
    for (let i = siteDetail.history.length - 1; i >= 0; i--) {
      const histStatus = siteDetail.history[i].status
      if (!isOnHold(histStatus)) {
        return mapRawStatusToControlStage(histStatus)
      }
    }
  }

  // Default fallback
  return 'under_consideration'
}

