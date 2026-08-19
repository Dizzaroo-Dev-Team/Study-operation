import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import {
  createClause,
  deleteClause,
  listClauses,
  publishClauseVersion,
  updateClause,
  type Clause,
  type LockPolicy,
} from '../services/clauseService'

// ---------------------------------------------------------------------------
// Types / constants
// ---------------------------------------------------------------------------

const LOCK_POLICY_OPTIONS: { value: LockPolicy; label: string; description: string }[] = [
  { value: 'STANDARD_LOCKED', label: 'Locked',    description: 'Cannot be edited in any template' },
  { value: 'EDITABLE',        label: 'Editable',  description: 'Can be customised per template'   },
  { value: 'ALTERNATE',       label: 'Alternate', description: 'Swap-in / fallback clause'        },
]

const LOCK_POLICY_BADGE: Record<LockPolicy, string> = {
  STANDARD_LOCKED: 'bg-amber-100 text-amber-800',
  EDITABLE:        'bg-green-100  text-green-800',
  ALTERNATE:       'bg-purple-100 text-purple-800',
}

const KNOWN_CATEGORIES = [
  'CONFIDENTIALITY', 'PAYMENT', 'TERMINATION', 'LIABILITY',
  'GOVERNING LAW', 'INTELLECTUAL PROPERTY', 'INDEMNIFICATION',
  'FORCE MAJEURE', 'DISPUTE RESOLUTION', 'GENERAL',
]

const EMPTY_DOC = { type: 'doc', content: [{ type: 'paragraph' }] }

// ---------------------------------------------------------------------------
// Mini Tiptap editor (reused in the modal)
// ---------------------------------------------------------------------------

interface ClauseEditorProps {
  initialContent?: Record<string, unknown>
  onChange: (json: Record<string, unknown>) => void
}

const ClauseEditor: React.FC<ClauseEditorProps> = ({ initialContent, onChange }) => {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: initialContent ?? EMPTY_DOC,
    onUpdate: ({ editor: ed }) => onChange(ed.getJSON() as Record<string, unknown>),
  })

  if (!editor) return null

  return (
    <div className="flex flex-col rounded-md border border-gray-300 overflow-hidden">
      {/* Mini toolbar */}
      <div className="flex items-center gap-1 border-b border-gray-200 bg-gray-50 px-2 py-1.5">
        {[
          { label: <strong>B</strong>, action: () => editor.chain().focus().toggleBold().run(),           active: editor.isActive('bold') },
          { label: <em>I</em>,         action: () => editor.chain().focus().toggleItalic().run(),         active: editor.isActive('italic') },
          { label: 'H1',               action: () => editor.chain().focus().toggleHeading({ level: 1 }).run(), active: editor.isActive('heading', { level: 1 }) },
          { label: 'H2',               action: () => editor.chain().focus().toggleHeading({ level: 2 }).run(), active: editor.isActive('heading', { level: 2 }) },
          { label: '• List',           action: () => editor.chain().focus().toggleBulletList().run(),     active: editor.isActive('bulletList') },
          { label: '1. List',          action: () => editor.chain().focus().toggleOrderedList().run(),    active: editor.isActive('orderedList') },
        ].map(({ label, action, active }, i) => (
          <button
            key={i}
            type="button"
            onMouseDown={(e) => { e.preventDefault(); action() }}
            className={[
              'rounded px-2 py-0.5 text-sm transition',
              active ? 'bg-indigo-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-100 border border-gray-200',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="min-h-[140px] overflow-y-auto bg-white p-3">
        <EditorContent editor={editor} className="prose max-w-none text-sm focus:outline-none" />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modal for create / edit
// ---------------------------------------------------------------------------

interface ClauseModalProps {
  clause?: Clause | null
  onSave: () => void
  onClose: () => void
}

const ClauseModal: React.FC<ClauseModalProps> = ({ clause, onSave, onClose }) => {
  const isEdit = Boolean(clause)

  const [title, setTitle]           = useState(clause?.title ?? '')
  const [category, setCategory]     = useState(clause?.category ?? '')
  const [customCat, setCustomCat]   = useState('')
  const [description, setDescription] = useState(clause?.description ?? '')
  const [lockPolicy, setLockPolicy] = useState<LockPolicy>(clause?.lock_policy ?? 'STANDARD_LOCKED')
  const [saving, setSaving]         = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const contentRef = useRef<Record<string, unknown>>(
    clause?.current_version?.content_json ?? EMPTY_DOC as Record<string, unknown>,
  )

  const handleContentChange = useCallback((json: Record<string, unknown>) => {
    contentRef.current = json
  }, [])

  const effectiveCategory = category === '__custom__' ? customCat.trim() : category

  const handleSave = async () => {
    if (!title.trim()) { setError('Title is required'); return }
    if (!effectiveCategory.trim()) { setError('Category is required'); return }

    setSaving(true)
    setError(null)
    try {
      if (isEdit && clause) {
        await updateClause(clause.id, {
          title:       title.trim(),
          category:    effectiveCategory.toUpperCase(),
          description: description.trim() || undefined,
          lock_policy: lockPolicy,
        })
        // Publish new version only if user changed the content
        await publishClauseVersion(clause.id, {
          content_json: contentRef.current,
          status: 'APPROVED',
        })
      } else {
        await createClause({
          title:       title.trim(),
          category:    effectiveCategory.toUpperCase(),
          description: description.trim() || undefined,
          lock_policy: lockPolicy,
          content_json: contentRef.current,
        })
      }
      onSave()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save clause'
      setError(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center bg-black/50 p-4">
      <div className="flex flex-col bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
          <h2 className="text-base font-semibold text-gray-900">
            {isEdit ? 'Edit Clause' : 'New Clause'}
          </h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {error && (
            <p className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">{error}</p>
          )}

          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title <span className="text-red-500">*</span></label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Standard Confidentiality Clause"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              autoFocus
            />
          </div>

          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Category <span className="text-red-500">*</span></label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">Select a category…</option>
              {KNOWN_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
              <option value="__custom__">+ Custom…</option>
            </select>
            {category === '__custom__' && (
              <input
                type="text"
                value={customCat}
                onChange={(e) => setCustomCat(e.target.value)}
                placeholder="Type category name"
                className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            )}
          </div>

          {/* Lock policy */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Lock Policy</label>
            <div className="flex flex-col gap-2">
              {LOCK_POLICY_OPTIONS.map((opt) => (
                <label key={opt.value} className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="lockPolicy"
                    value={opt.value}
                    checked={lockPolicy === opt.value}
                    onChange={() => setLockPolicy(opt.value)}
                    className="mt-0.5 h-4 w-4 text-indigo-600 border-gray-300"
                  />
                  <div>
                    <span className="text-sm font-medium text-gray-800">{opt.label}</span>
                    <span className="ml-2 text-xs text-gray-400">{opt.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description <span className="text-gray-400 font-normal">(optional)</span></label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Brief description shown in the library panel"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          </div>

          {/* Content editor */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Clause Content
              {isEdit && <span className="ml-2 text-xs text-gray-400">(saving publishes a new version)</span>}
            </label>
            <ClauseEditor
              initialContent={contentRef.current}
              onChange={handleContentChange}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-200 shrink-0">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 rounded-md border border-gray-300 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 rounded-md bg-indigo-600 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Clause'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const ClauseLibraryManager: React.FC = () => {
  const [clauses, setClauses]         = useState<Clause[]>([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState<string | null>(null)
  const [search, setSearch]           = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [showModal, setShowModal]     = useState(false)
  const [editTarget, setEditTarget]   = useState<Clause | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listClauses({
        q:        search        || undefined,
        category: filterCategory || undefined,
      })
      setClauses(data)
    } catch {
      setError('Failed to load clauses')
    } finally {
      setLoading(false)
    }
  }, [search, filterCategory])

  useEffect(() => {
    const id = setTimeout(load, 300)
    return () => clearTimeout(id)
  }, [load])

  const handleDelete = async (clause: Clause) => {
    if (!window.confirm(`Delete "${clause.title}"? This cannot be undone.`)) return
    try {
      await deleteClause(clause.id)
      setClauses((prev) => prev.filter((c) => c.id !== clause.id))
    } catch {
      setError('Failed to delete clause')
    }
  }

  const handleModalSave = () => {
    setShowModal(false)
    setEditTarget(null)
    load()
  }

  const categoryOptions = Array.from(
    new Set([...KNOWN_CATEGORIES, ...clauses.map((c) => c.category)]),
  ).sort()

  return (
    <div className="flex flex-col h-full bg-gray-50 p-6 min-h-0 max-w-7xl mx-auto w-full overflow-hidden">
      {/* Header */}
      <div className="mb-5 shrink-0" data-testid="clause-library-header">
        <h1 className="text-3xl font-bold text-gray-900 mb-1">Clause Library</h1>
        <p className="text-gray-500 text-sm">
          Create and manage reusable clauses. Insert them into any agreement template from the Clause Builder.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800 shrink-0">
          {error}
        </div>
      )}

      {/* Toolbar */}
      <div className="mb-4 flex items-center gap-3 shrink-0" data-testid="clause-library-toolbar">
        <button
          onClick={() => { setEditTarget(null); setShowModal(true) }}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium"
        >
          + New Clause
        </button>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search clauses…"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 w-56"
        />
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          <option value="">All categories</option>
          {categoryOptions.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="ml-auto text-xs text-gray-400">{clauses.length} clause{clauses.length !== 1 ? 's' : ''}</span>
      </div>

      {/* Table */}
      <div className="flex-1 min-h-0 flex flex-col bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
        {loading ? (
          <div className="flex-1 flex items-center justify-center text-sm text-gray-400">Loading…</div>
        ) : clauses.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-gray-400">
            <span className="text-4xl">📋</span>
            <p className="text-sm">No clauses yet. Click "+ New Clause" to create one.</p>
          </div>
        ) : (
          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 sticky top-0 z-10">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Title</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Category</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Lock Policy</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider min-w-[140px]">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {clauses.map((clause) => (
                  <tr key={clause.id} className="hover:bg-gray-50/60">
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-gray-900">{clause.title}</p>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-xs rounded-full bg-gray-100 px-2 py-0.5 text-gray-600 font-medium">
                        {clause.category}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`text-xs rounded-full px-2 py-0.5 font-medium ${LOCK_POLICY_BADGE[clause.lock_policy]}`}>
                        {LOCK_POLICY_OPTIONS.find((o) => o.value === clause.lock_policy)?.label ?? clause.lock_policy}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {clause.current_version ? `v${clause.current_version.version_number}` : '—'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500 max-w-xs">
                      <p className="truncate">{clause.description ?? '—'}</p>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => { setEditTarget(clause); setShowModal(true) }}
                          className="text-indigo-600 hover:text-indigo-800"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(clause)}
                          className="text-red-500 hover:text-red-700"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showModal && (
        <ClauseModal
          clause={editTarget}
          onSave={handleModalSave}
          onClose={() => { setShowModal(false); setEditTarget(null) }}
        />
      )}
    </div>
  )
}

export default ClauseLibraryManager
