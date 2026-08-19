import React, { useCallback, useEffect, useState } from 'react'
import { listClauses, type Clause } from '../services/clauseService'
import ClauseCard from './ClauseCard'

interface ClauseLibraryPanelProps {
  /** IDs of clauses already inserted into this template (for "already added" state) */
  addedClauseIds: Set<string>
  /** Called when the user clicks Insert on a clause card */
  onInsert: (clause: Clause) => void
}

// Deduplicated list of all categories from loaded clauses
const KNOWN_CATEGORIES = [
  'CONFIDENTIALITY',
  'PAYMENT',
  'TERMINATION',
  'LIABILITY',
  'GOVERNING LAW',
  'INTELLECTUAL PROPERTY',
  'INDEMNIFICATION',
  'FORCE MAJEURE',
  'DISPUTE RESOLUTION',
  'GENERAL',
]

const ClauseLibraryPanel: React.FC<ClauseLibraryPanelProps> = ({
  addedClauseIds,
  onInsert,
}) => {
  const [clauses, setClauses]   = useState<Clause[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState<string | null>(null)
  const [search, setSearch]     = useState('')
  const [category, setCategory] = useState('')

  const fetchClauses = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listClauses({
        q:        search   || undefined,
        category: category || undefined,
      })
      setClauses(data)
    } catch {
      setError('Failed to load clause library')
    } finally {
      setLoading(false)
    }
  }, [search, category])

  // Debounce search
  useEffect(() => {
    const id = setTimeout(fetchClauses, 300)
    return () => clearTimeout(id)
  }, [fetchClauses])

  // Unique categories from loaded clauses (plus static known ones)
  const categoryOptions = Array.from(
    new Set([...KNOWN_CATEGORIES, ...clauses.map((c) => c.category)]),
  ).sort()

  return (
    <div className="flex h-full flex-col bg-gray-50">
      {/* Panel header */}
      <div className="border-b border-gray-200 bg-white px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-800">Clause Library</h2>
        <p className="mt-0.5 text-xs text-gray-500">
          Click "Insert" to add a clause to the template
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-2 border-b border-gray-200 bg-white p-3">
        <input
          type="text"
          placeholder="Search clauses…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
        >
          <option value="">All categories</option>
          {categoryOptions.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>

      {/* Clause list */}
      <div className="flex-1 overflow-y-auto p-3">
        {loading && (
          <p className="py-8 text-center text-xs text-gray-400">Loading clauses…</p>
        )}
        {!loading && error && (
          <p className="py-8 text-center text-xs text-red-500">{error}</p>
        )}
        {!loading && !error && clauses.length === 0 && (
          <p className="py-8 text-center text-xs text-gray-400">
            No clauses found.
            {search || category ? ' Try clearing the filters.' : ''}
          </p>
        )}
        {!loading && !error && clauses.length > 0 && (
          <div className="flex flex-col gap-3">
            {clauses.map((clause) => (
              <ClauseCard
                key={clause.id}
                clause={clause}
                onInsert={onInsert}
                alreadyAdded={addedClauseIds.has(clause.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-200 bg-white px-4 py-2">
        <p className="text-xs text-gray-400">
          {clauses.length} clause{clauses.length !== 1 ? 's' : ''} shown
        </p>
      </div>
    </div>
  )
}

export default ClauseLibraryPanel
