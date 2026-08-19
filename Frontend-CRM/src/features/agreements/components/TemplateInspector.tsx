import React from 'react'
import type { TemplateClause } from '../services/clauseService'

interface TemplateInspectorProps {
  templateId: string
  /** Currently selected clause slot, or null if nothing selected */
  selected: TemplateClause | null
  /** Full ordered list (for clause count / position display) */
  allClauses: TemplateClause[]
  /** Called when user changes lock/editable toggles */
  onLockChange: (tc: TemplateClause, isLocked: boolean, isEditable: boolean) => void
  /** Called when user removes a clause slot */
  onRemove: (tc: TemplateClause) => void
  /** Whether any save is in progress (disables buttons) */
  saving?: boolean
}

const LOCK_POLICY_DESCRIPTIONS: Record<string, string> = {
  STANDARD_LOCKED: 'Legal text — cannot be modified in this template or any agreement generated from it.',
  EDITABLE:        'Users may edit this clause content directly in the template.',
  ALTERNATE:       'Swap-in fallback clause for negotiation.',
}

const TemplateInspector: React.FC<TemplateInspectorProps> = ({
  selected,
  allClauses,
  onLockChange,
  onRemove,
  saving = false,
}) => {
  if (!selected) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 bg-gray-50 p-6">
        <span className="text-2xl">📋</span>
        <p className="text-center text-sm text-gray-500">
          Click on a clause block in the editor to inspect it here.
        </p>
        <div className="mt-4 w-full rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase text-gray-500">
            Template summary
          </h3>
          <p className="text-sm text-gray-700">
            <span className="font-medium">{allClauses.length}</span> clause
            {allClauses.length !== 1 ? 's' : ''} in this template
          </p>
          <ul className="mt-2 space-y-1">
            {allClauses.map((tc, idx) => (
              <li key={tc.id} className="flex items-center gap-2 text-xs text-gray-500">
                <span className="w-4 text-gray-300">{idx + 1}.</span>
                <span className="flex-1 truncate">{tc.clause_title ?? 'Unnamed'}</span>
                <LockBadge isLocked={tc.is_locked} />
              </li>
            ))}
          </ul>
        </div>
      </div>
    )
  }

  const position = allClauses.findIndex((tc) => tc.id === selected.id) + 1

  return (
    <div className="flex h-full flex-col bg-gray-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-800">Clause Inspector</h2>
          <span className="text-xs text-gray-400">#{position} of {allClauses.length}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Identity */}
        <Section title="Identity">
          <Field label="Title"     value={selected.clause_title ?? '—'} />
          <Field label="Category"  value={selected.clause_category ?? '—'} />
          <Field
            label="Lock Policy"
            value={selected.lock_policy ?? '—'}
            hint={LOCK_POLICY_DESCRIPTIONS[selected.lock_policy ?? ''] ?? ''}
          />
          <Field
            label="Pinned Version"
            value={
              selected.pinned_version_number != null
                ? `v${selected.pinned_version_number}`
                : 'Latest'
            }
          />
          {selected.has_override && (
            <p className="mt-1 rounded bg-amber-50 border border-amber-200 px-2 py-1 text-xs text-amber-700">
              This slot has a template-local override (EDITABLE clause was customised).
            </p>
          )}
        </Section>

        {/* Lock controls */}
        <Section title="Template-level Lock Override">
          <p className="mb-2 text-xs text-gray-500">
            Override the clause's default lock policy for THIS template only.
          </p>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={selected.is_locked}
              onChange={(e) =>
                onLockChange(selected, e.target.checked, !e.target.checked)
              }
              disabled={saving}
              className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-sm text-gray-700">
              Lock clause in this template
              <span className="ml-1 text-xs text-gray-400">(prevents editing)</span>
            </span>
          </label>

          <label className="mt-2 flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={selected.is_editable}
              onChange={(e) =>
                onLockChange(selected, !e.target.checked, e.target.checked)
              }
              disabled={saving}
              className="h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
            />
            <span className="text-sm text-gray-700">
              Allow editing in this template
              <span className="ml-1 text-xs text-gray-400">(overrides lock)</span>
            </span>
          </label>
        </Section>

        {/* Danger zone */}
        <Section title="Actions">
          <button
            type="button"
            disabled={saving}
            onClick={() => onRemove(selected)}
            className="w-full rounded-md border border-red-300 bg-white px-3 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50 transition"
          >
            Remove from template
          </button>
        </Section>
      </div>
    </div>
  )
}

export default TemplateInspector

// ---------------------------------------------------------------------------
// Small sub-components (private)
// ---------------------------------------------------------------------------

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({
  title,
  children,
}) => (
  <div className="rounded-lg border border-gray-200 bg-white p-3">
    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
      {title}
    </h3>
    {children}
  </div>
)

const Field: React.FC<{ label: string; value: string; hint?: string }> = ({
  label,
  value,
  hint,
}) => (
  <div className="mb-2">
    <span className="text-xs text-gray-500">{label}: </span>
    <span className="text-xs font-medium text-gray-800">{value}</span>
    {hint && <p className="mt-0.5 text-xs text-gray-400">{hint}</p>}
  </div>
)

const LockBadge: React.FC<{ isLocked: boolean }> = ({ isLocked }) => (
  <span
    className={`rounded-full px-1.5 py-0.5 text-xs ${
      isLocked ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'
    }`}
  >
    {isLocked ? '🔒' : '✏️'}
  </span>
)
