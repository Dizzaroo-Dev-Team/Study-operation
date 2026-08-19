import { useMemo } from 'react'
import { SiteStatusDetail, ControlStage } from '@/features/sites/types/siteStatus'
import { mapRawStatusToControlStage, isOnHold, getBaseStage } from '@/features/sites/services/controlTowerMapping'

export interface ReadinessResult {
  isReady: boolean
  reason?: string
  currentStage: ControlStage
}

/**
 * Hook for UI-level readiness gating
 * 
 * Checks if a site is ready for specific actions (e.g., eConsent, screening)
 * based on the Control Tower stage. This is UI-level enforcement only.
 */
export function useReadinessGating(
  siteDetail: SiteStatusDetail | null,
  requiredStage: ControlStage = 'open_for_recruitment'
): ReadinessResult {
  return useMemo(() => {
    if (!siteDetail || !siteDetail.current_status) {
      return {
        isReady: false,
        reason: 'Site status information not available',
        currentStage: 'under_consideration',
      }
    }

    const rawStatus = siteDetail.current_status
    const onHold = isOnHold(rawStatus)
    const currentStage = mapRawStatusToControlStage(rawStatus, siteDetail.secondary_statuses || null)
    const baseStage = onHold ? getBaseStage(currentStage, siteDetail) : currentStage

    // Check if site is on hold
    if (onHold) {
      return {
        isReady: false,
        reason: `Site is currently on hold. Actions are disabled until the site resumes normal operations.`,
        currentStage: baseStage,
      }
    }

    // Check if site is in the required stage
    // Note: Stage-based restrictions are now handled at the milestone level
    // This hook is kept for backward compatibility but messaging is handled in UI components
    if (baseStage !== requiredStage) {
      return {
        isReady: false,
        reason: 'Required milestones must be completed before this action is available.',
        currentStage: baseStage,
      }
    }

    return {
      isReady: true,
      currentStage: baseStage,
    }
  }, [siteDetail, requiredStage])
}

/**
 * Hook specifically for eConsent readiness
 */
export function useEConsentReadiness(siteDetail: SiteStatusDetail | null): ReadinessResult {
  return useReadinessGating(siteDetail, 'open_for_recruitment')
}

/**
 * Hook specifically for screening readiness
 */
export function useScreeningReadiness(siteDetail: SiteStatusDetail | null): ReadinessResult {
  return useReadinessGating(siteDetail, 'open_for_recruitment')
}

