import React from 'react'
import { useWorkspaceContext } from '@/hooks/useWorkspaceContext'
import SiteSelectionPrompt from './SiteSelectionPrompt'

export interface SiteScopedTabProps {
  /** Feature name for the empty state, e.g. "Documents". */
  featureName: string
  children: React.ReactNode
}

/**
 * Template wrapper for site-specific tabs. Renders children only when a study
 * and site are selected in the global navbar; otherwise shows a polite prompt.
 *
 * @example
 * export function MonitoringTab() {
 *   return (
 *     <SiteScopedTab featureName="Monitoring">
 *       <MonitoringModule />
 *     </SiteScopedTab>
 *   )
 * }
 */
const SiteScopedTab: React.FC<SiteScopedTabProps> = ({ featureName, children }) => {
  const { isReady, missingStudy } = useWorkspaceContext()

  if (!isReady) {
    return (
      <SiteSelectionPrompt
        title={featureName}
        message={
          missingStudy
            ? 'Please select a study from the top navigation, then choose a site to view these details.'
            : 'Please select a site from the top navigation to view these details. Your selection applies across all site-specific tabs.'
        }
      />
    )
  }

  return <>{children}</>
}

export default SiteScopedTab
