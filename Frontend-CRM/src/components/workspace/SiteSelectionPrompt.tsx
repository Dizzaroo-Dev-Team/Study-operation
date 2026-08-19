import React from 'react'

export interface SiteSelectionPromptProps {
  /** Tab or feature name shown in the heading, e.g. "Monitoring". */
  title?: string
  /** Override the default body copy. */
  message?: string
  className?: string
}

/**
 * Shown inside site-scoped tabs when study/site is not set in the global navbar.
 * Does not include a local site dropdown — selection lives in the top bar only.
 */
const SiteSelectionPrompt: React.FC<SiteSelectionPromptProps> = ({
  title,
  message,
  className = '',
}) => {
  const heading = title ? `${title}` : 'Workspace'

  return (
    <div
      className={`flex-1 flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 p-8 ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="w-full max-w-lg text-center">
        <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-[#168AAD] mb-4">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
            <circle cx="12" cy="10" r="3" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-gray-900 mb-2">{heading}</h2>
        <p className="text-sm text-gray-600 leading-relaxed">
          {message ??
            'Please select a study and site from the top navigation to view these details. Your selection will apply across Monitoring, Documents, Tasks, and other site-specific areas.'}
        </p>
      </div>
    </div>
  )
}

export default SiteSelectionPrompt
