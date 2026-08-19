import React from 'react'
import type { Clause, LockPolicy } from '../services/clauseService'

interface ClauseCardProps {
  clause: Clause
  /** Called when user clicks "Insert" — the parent inserts into the editor */
  onInsert: (clause: Clause) => void
  /** Whether the insert button is disabled (e.g. clause already in template) */
  alreadyAdded?: boolean
}

const LOCK_POLICY_LABELS: Record<LockPolicy, { label: string; className: string }> = {
  STANDARD_LOCKED: { label: 'Locked',    className: 'bg-amber-100 text-amber-800' },
  EDITABLE:        { label: 'Editable',  className: 'bg-green-100 text-green-800' },
  ALTERNATE:       { label: 'Alternate', className: 'bg-purple-100 text-purple-800' },
}

const ClauseCard: React.FC<ClauseCardProps> = ({ clause, onInsert, alreadyAdded = false }) => {
  const policyMeta = LOCK_POLICY_LABELS[clause.lock_policy] ?? {
    label: clause.lock_policy,
    className: 'bg-gray-100 text-gray-700',
  }

  return (
    <div className="group relative flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition hover:border-indigo-300 hover:shadow-md">
      {/* Category + policy badges */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs rounded-full bg-gray-100 px-2 py-0.5 text-gray-600 font-medium">
          {clause.category}
        </span>
        <span
          className={`text-xs rounded-full px-2 py-0.5 font-medium ${policyMeta.className}`}
        >
          {policyMeta.label}
        </span>
        {clause.current_version && (
          <span className="ml-auto text-xs text-gray-400">
            v{clause.current_version.version_number}
          </span>
        )}
      </div>

      {/* Title */}
      <p className="text-sm font-semibold text-gray-800 leading-snug">{clause.title}</p>

      {/* Description preview */}
      {clause.description && (
        <p className="text-xs text-gray-500 line-clamp-2">{clause.description}</p>
      )}

      {/* Insert button */}
      <button
        type="button"
        disabled={alreadyAdded}
        onClick={() => onInsert(clause)}
        className={[
          'mt-1 w-full rounded-md py-1.5 text-xs font-medium transition',
          alreadyAdded
            ? 'cursor-not-allowed bg-gray-100 text-gray-400'
            : 'bg-indigo-600 text-white hover:bg-indigo-700 active:bg-indigo-800',
        ].join(' ')}
      >
        {alreadyAdded ? 'Already added' : '+ Insert'}
      </button>
    </div>
  )
}

export default ClauseCard
