import React from 'react'
import { useStudySite } from '../contexts/StudySiteContext'

interface SiteRequiredPromptProps {
  /**
   * Optional label for the gated area (e.g. "the inbox", "site profile").
   * Falls back to a generic message when not provided.
   */
  feature?: string
  /**
   * When true, render the prompt full-screen-centered. When false (the
   * default), render as an inline card suitable for a tab body.
   */
  fullPage?: boolean
}

/**
 * Single source of truth for the "you need to pick a study + site first"
 * empty state. Used by every module that scopes its data to the active
 * study/site (conversations, site profile, status, logistics, control
 * tower, monitoring, etc.).
 *
 * The selectors themselves live in the navbar — see Navbar.tsx — so this
 * component only needs to *describe* what the user must do, not duplicate
 * the dropdowns. Reads the active selection from StudySiteContext to tailor
 * the message ("pick a site" vs "pick a study and a site").
 */
const SiteRequiredPrompt: React.FC<SiteRequiredPromptProps> = ({
  feature,
  fullPage = false,
}) => {
  const { selectedStudyId, selectedSiteId } = useStudySite()

  const needStudy = !selectedStudyId
  const needSite = !selectedSiteId
  const label = feature ? ` to view ${feature}` : ''

  let title: string
  let body: string
  if (needStudy && needSite) {
    title = `Select a study and a site first${label ? '' : ''}`
    body = `Pick a study, then a site from the navbar at the top of the page${label}.`
  } else if (needStudy) {
    title = `Select a study first${label ? '' : ''}`
    body = `Use the study dropdown in the navbar to choose a study${label}.`
  } else {
    title = `Select a site first${label ? '' : ''}`
    body = `Use the site dropdown in the navbar to choose a site${label}.`
  }

  const containerClass = fullPage
    ? 'min-h-[60vh] flex items-center justify-center px-6 py-10'
    : 'w-full px-6 py-10 flex items-center justify-center'

  return (
    <div className={containerClass} data-testid="site-required-prompt">
      <div className="w-full max-w-md mx-auto rounded-2xl bg-white shadow-sm ring-1 ring-gray-200 px-6 py-7 text-center">
        <div className="mx-auto mb-3 h-10 w-10 rounded-full bg-[#168AAD]/10 flex items-center justify-center">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#168AAD"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 22s8-7.58 8-13a8 8 0 1 0-16 0c0 5.42 8 13 8 13z" />
            <circle cx="12" cy="9" r="2.5" />
          </svg>
        </div>
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        <p className="mt-1.5 text-sm text-gray-500 leading-relaxed">{body}</p>
      </div>
    </div>
  )
}

export default SiteRequiredPrompt
