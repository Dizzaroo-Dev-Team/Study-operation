import React from 'react'
import { cn } from '@/lib/utils'

/** Shared input styling for all IRB form fields */
export const IRB_FIELD_INPUT =
  'mt-0 h-10 rounded-lg border-slate-200 bg-white shadow-sm transition focus-visible:ring-2 focus-visible:ring-[#168AAD]/30 focus-visible:border-[#168AAD]'

export const IRB_FIELD_SELECT =
  'h-10 rounded-lg border-slate-200 bg-white shadow-sm focus:ring-2 focus:ring-[#168AAD]/30 focus:border-[#168AAD]'

const FieldLabel = ({ children, required }) => (
  <label className="block w-full text-xs font-semibold uppercase tracking-wide text-slate-500 leading-snug">
    <span>{children}</span>
    {required && <span className="text-rose-500 normal-case tracking-normal ml-0.5">*</span>}
  </label>
)

const FieldError = ({ message }) => {
  if (!message) return null
  return (
    <p className="flex items-center gap-1 text-xs leading-tight text-rose-600">
      <span className="inline-block h-1 w-1 rounded-full bg-rose-500 shrink-0" />
      {message}
    </p>
  )
}

const HelpText = ({ children }) => {
  if (!children) return null
  return <p className="text-xs leading-tight text-slate-400 -mt-0.5">{children}</p>
}

/** Two-column form grid with top-aligned fields */
export const FORM_GRID = 'grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2 items-start'

/**
 * Aligns label + control + error in a fixed-height row so grid neighbours line up.
 * Labels get a 2-line min height; errors render only when present to avoid dead space.
 */
export function FormField({ label, required = false, error = '', help = '', children, className = '' }) {
  return (
    <div className={cn('flex flex-col gap-1 min-w-0', className)}>
      <div className="min-h-[1.75rem] flex items-end">
        <FieldLabel required={required}>{label}</FieldLabel>
      </div>
      <div className="min-w-0">{children}</div>
      {help ? <HelpText>{help}</HelpText> : null}
      {error ? (
        <div className="min-h-[1rem]">
          <FieldError message={error} />
        </div>
      ) : null}
    </div>
  )
}

const SectionShell = ({ title, description, children, className }) => {
  return (
    <div className={cn('space-y-2', className)}>
      {(title || description) && (
        <div className="sr-only">
          {title && <div>{title}</div>}
          {description && <div>{description}</div>}
        </div>
      )}
      {children}
    </div>
  )
}

/** Wraps a group of related fields with a subtle tinted background */
const FieldGroup = ({ title, children, className, accent = 'sky' }) => {
  const accents = {
    sky: 'border-sky-100 bg-gradient-to-br from-sky-50/80 to-white',
    violet: 'border-violet-100 bg-gradient-to-br from-violet-50/80 to-white',
    emerald: 'border-emerald-100 bg-gradient-to-br from-emerald-50/80 to-white',
    amber: 'border-amber-100 bg-gradient-to-br from-amber-50/80 to-white',
  }
  return (
    <div
      className={cn(
        'rounded-xl border p-3 sm:p-4 space-y-2',
        accents[accent] || accents.sky,
        className,
      )}
    >
      {title && (
        <div className="text-sm font-semibold text-slate-800 pb-1 border-b border-slate-200/60">
          {title}
        </div>
      )}
      {children}
    </div>
  )
}

export { SectionShell, FieldLabel, FieldError, HelpText, FieldGroup }
