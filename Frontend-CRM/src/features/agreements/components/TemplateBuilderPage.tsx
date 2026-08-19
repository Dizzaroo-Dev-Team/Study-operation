/**
 * TemplateBuilderPage — choose WHERE clauses go in an existing document.
 *
 * The original DOCX is never converted or edited — that's what preserves its
 * tables / colors / fonts. Instead the builder shows the document's blocks in
 * order with drop zones between them. Dragging a clause into a drop zone records
 * an "insertion" (after_block + clause). At agreement generation the backend
 * clones the original DOCX and splices the clauses in at those anchors.
 *
 * Left panel : searchable clause library (drag a card onto a drop zone)
 * Center     : ordered document blocks + drop zones + inserted clauses (inline)
 * Top bar    : Save
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  getDocumentBlocks,
  listClauses,
  saveClauseInsertions,
  type Clause,
  type ClauseInsertion,
  type DocumentBlock,
} from '../services/clauseService'

interface TemplateBuilderPageProps {
  templateId: string
  templateName?: string
  onClose?: () => void
}

const LOCK_BADGE: Record<string, string> = {
  STANDARD_LOCKED: 'bg-amber-100 text-amber-700',
  EDITABLE:        'bg-green-100  text-green-700',
  ALTERNATE:       'bg-purple-100 text-purple-700',
}
const LOCK_LABEL: Record<string, string> = {
  STANDARD_LOCKED: 'Locked', EDITABLE: 'Editable', ALTERNATE: 'Alternate',
}

// ---------------------------------------------------------------------------
// Clause library (left)
// ---------------------------------------------------------------------------

interface ClausePanelProps {
  onDragStart: (clause: Clause) => void
  onDragEnd: () => void
}

const ClausePanel: React.FC<ClausePanelProps> = ({ onDragStart, onDragEnd }) => {
  const [clauses, setClauses] = useState<Clause[]>([])
  const [search, setSearch]   = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setClauses(await listClauses({ q: search || undefined }))
    } finally {
      setLoading(false)
    }
  }, [search])

  useEffect(() => {
    const id = setTimeout(load, 300)
    return () => clearTimeout(id)
  }, [load])

  return (
    <div className="flex h-full flex-col bg-gray-50 border-r border-gray-200">
      <div className="shrink-0 border-b border-gray-200 bg-white px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-800">Clause Library</h2>
        <p className="mt-0.5 text-xs text-gray-400">Drag a clause into the document →</p>
      </div>
      <div className="shrink-0 border-b border-gray-200 bg-white px-3 py-2">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search clauses…"
          className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400"
        />
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {loading && <p className="py-6 text-center text-xs text-gray-400">Loading…</p>}
        {!loading && clauses.length === 0 && <p className="py-6 text-center text-xs text-gray-400">No clauses found.</p>}
        {!loading && clauses.map((clause) => {
          const draggable = Boolean(clause.current_version)
          return (
            <div
              key={clause.id}
              draggable={draggable}
              onDragStart={(e) => {
                if (!draggable) return
                e.dataTransfer.effectAllowed = 'copy'
                e.dataTransfer.setData('text/plain', clause.id)
                onDragStart(clause)
              }}
              onDragEnd={onDragEnd}
              className={[
                'rounded-lg border border-gray-200 bg-white p-3 shadow-sm transition',
                draggable ? 'cursor-grab active:cursor-grabbing hover:border-indigo-300 hover:shadow-md' : 'opacity-60',
              ].join(' ')}
            >
              <div className="mb-1 flex items-center gap-1.5 flex-wrap">
                <span className="text-gray-300 select-none">⠿</span>
                <span className="text-xs rounded-full bg-gray-100 px-2 py-0.5 text-gray-600">{clause.category}</span>
                <span className={`text-xs rounded-full px-2 py-0.5 font-medium ${LOCK_BADGE[clause.lock_policy] ?? 'bg-gray-100 text-gray-600'}`}>
                  {LOCK_LABEL[clause.lock_policy] ?? clause.lock_policy}
                </span>
                {clause.current_version && <span className="ml-auto text-xs text-gray-400">v{clause.current_version.version_number}</span>}
              </div>
              <p className="text-sm font-medium text-gray-800 leading-snug">{clause.title}</p>
              {clause.description && <p className="mt-1 text-xs text-gray-500 line-clamp-2">{clause.description}</p>}
            </div>
          )
        })}
      </div>
      <div className="shrink-0 border-t border-gray-200 bg-white px-4 py-2">
        <p className="text-xs text-gray-400">{clauses.length} clause{clauses.length !== 1 ? 's' : ''}</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Drop zone between blocks
// ---------------------------------------------------------------------------

interface DropZoneProps {
  afterBlock: number
  active: boolean
  onDrop: (afterBlock: number) => void
  onEnter: () => void
  onLeave: () => void
}

const DropZone: React.FC<DropZoneProps> = ({ afterBlock, active, onDrop, onEnter, onLeave }) => (
  <div
    onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; onEnter() }}
    onDragLeave={onLeave}
    onDrop={(e) => { e.preventDefault(); onDrop(afterBlock) }}
    className={[
      'my-1 rounded transition-all',
      active
        ? 'h-10 border-2 border-dashed border-indigo-400 bg-indigo-50 flex items-center justify-center'
        : 'h-2 hover:h-6 border border-dashed border-transparent hover:border-gray-300',
    ].join(' ')}
  >
    {active && <span className="text-xs font-medium text-indigo-600">Drop clause here</span>}
  </div>
)

// ---------------------------------------------------------------------------
// Inserted clause chip (shown inline in the document)
// ---------------------------------------------------------------------------

const InsertedClause: React.FC<{ ins: ClauseInsertion; onRemove: () => void }> = ({ ins, onRemove }) => (
  <div className="my-1.5 flex items-center gap-2 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-2">
    <span className="text-indigo-500">＋</span>
    <span className="flex-1 text-sm font-medium text-indigo-800">{ins.clause_title || 'Clause'}</span>
    <span className="text-xs text-indigo-400">clause</span>
    <button
      type="button"
      onClick={onRemove}
      className="rounded p-0.5 text-indigo-400 hover:bg-indigo-100 hover:text-indigo-700"
      title="Remove"
    >
      ✕
    </button>
  </div>
)

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TemplateBuilderPage: React.FC<TemplateBuilderPageProps> = ({ templateId, templateName, onClose }) => {
  const [blocks, setBlocks]           = useState<DocumentBlock[]>([])
  const [insertions, setInsertions]   = useState<ClauseInsertion[]>([])
  const [hasDocx, setHasDocx]         = useState(true)
  const [loading, setLoading]         = useState(true)
  const [saving, setSaving]           = useState(false)
  const [error, setError]             = useState<string | null>(null)
  const [successMsg, setSuccessMsg]   = useState<string | null>(null)
  const [activeZone, setActiveZone]   = useState<number | null>(null)
  const draggedClauseRef = useRef<Clause | null>(null)

  // ---- Load blocks + insertions ----------------------------------------------
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getDocumentBlocks(templateId)
      .then((data) => {
        if (cancelled) return
        setBlocks(data.blocks)
        setInsertions(data.clause_insertions || [])
        setHasDocx(data.has_docx)
      })
      .catch(() => { if (!cancelled) setError('Failed to load template document') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [templateId])

  // ---- Drop a clause into a zone ---------------------------------------------
  const handleDrop = useCallback((afterBlock: number) => {
    setActiveZone(null)
    const clause = draggedClauseRef.current
    if (!clause) return
    setInsertions((prev) => [
      ...prev,
      {
        after_block: afterBlock,
        clause_id: clause.id,
        clause_version_id: clause.current_version_id,
        clause_title: clause.title,
      },
    ])
    draggedClauseRef.current = null
  }, [])

  const handleRemove = useCallback((idx: number) => {
    setInsertions((prev) => prev.filter((_, i) => i !== idx))
  }, [])

  // ---- Save ------------------------------------------------------------------
  const handleSave = useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      await saveClauseInsertions(templateId, insertions)
      setSuccessMsg('Saved')
      setTimeout(() => setSuccessMsg(null), 2500)
    } catch {
      setError('Save failed. Please try again.')
    } finally {
      setSaving(false)
    }
  }, [templateId, insertions])

  // Group insertions by anchor for inline rendering
  const insertionsByAnchor = (anchor: number) =>
    insertions
      .map((ins, idx) => ({ ins, idx }))
      .filter(({ ins }) => ins.after_block === anchor)

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Top bar */}
      <div className="flex shrink-0 items-center justify-between border-b border-gray-200 bg-gray-50 px-6 py-3">
        <div className="flex items-center gap-3">
          {onClose && (
            <button type="button" onClick={onClose} className="rounded p-1 text-gray-500 hover:bg-gray-200" title="Back">←</button>
          )}
          <div>
            <h1 className="text-sm font-semibold text-gray-800">{templateName ?? 'Template Builder'}</h1>
            <p className="text-xs text-gray-400">Drag clauses into the document where you want them, then Save.</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {successMsg && <span className="text-xs font-medium text-green-600">{successMsg}</span>}
          {error && <span className="text-xs text-red-600 max-w-xs truncate" title={error}>{error}</span>}
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || loading}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <div className="w-72 shrink-0 overflow-hidden">
          <ClausePanel
            onDragStart={(c) => { draggedClauseRef.current = c }}
            onDragEnd={() => { draggedClauseRef.current = null; setActiveZone(null) }}
          />
        </div>

        {/* Document column */}
        <div className="flex-1 overflow-y-auto bg-gray-100 p-8">
          {loading ? (
            <p className="text-sm text-gray-400">Loading document…</p>
          ) : (
            <div className="mx-auto max-w-3xl rounded-lg bg-white p-8 shadow-sm">
              {!hasDocx && blocks.length === 0 && (
                <p className="mb-4 rounded bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
                  This template has no uploaded document. Clauses you add will make up the whole document, in order.
                </p>
              )}

              {/* Drop zone before the first block */}
              <DropZone
                afterBlock={-1}
                active={activeZone === -1}
                onDrop={handleDrop}
                onEnter={() => setActiveZone(-1)}
                onLeave={() => setActiveZone((z) => (z === -1 ? null : z))}
              />
              {insertionsByAnchor(-1).map(({ ins, idx }) => (
                <InsertedClause key={`ins-${idx}`} ins={ins} onRemove={() => handleRemove(idx)} />
              ))}

              {/* Each block followed by its drop zone + any clauses anchored to it */}
              {blocks.map((block) => (
                <div key={block.index}>
                  <div className="group relative">
                    {block.type === 'table' ? (
                      <div className="my-2 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500">
                        {block.text || '[Table]'}
                      </div>
                    ) : (
                      <p className="py-0.5 text-sm text-gray-800 whitespace-pre-wrap">
                        {block.text || <span className="text-gray-300">(empty line)</span>}
                      </p>
                    )}
                  </div>

                  <DropZone
                    afterBlock={block.index}
                    active={activeZone === block.index}
                    onDrop={handleDrop}
                    onEnter={() => setActiveZone(block.index)}
                    onLeave={() => setActiveZone((z) => (z === block.index ? null : z))}
                  />
                  {insertionsByAnchor(block.index).map(({ ins, idx }) => (
                    <InsertedClause key={`ins-${idx}`} ins={ins} onRemove={() => handleRemove(idx)} />
                  ))}
                </div>
              ))}

              {blocks.length === 0 && hasDocx && (
                <p className="text-sm text-gray-400">The document has no readable blocks.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default TemplateBuilderPage
