import React, { useCallback, useEffect, useState } from 'react'
import { createNote, deleteNote, fetchNotes } from './services/budgeting.api'
import { btn } from './ui'

type Note = { id: string; body: string; created_at: string | null }

type Props = {
  templateId: string
  readOnly?: boolean
}

export const NotesSection: React.FC<Props> = ({ templateId, readOnly = false }) => {
  const [notes, setNotes] = useState<Note[]>([])
  const [loading, setLoading] = useState(true)
  const [newBody, setNewBody] = useState('')
  const [saving, setSaving] = useState(false)

  const loadNotes = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchNotes(templateId)
      setNotes(data)
    } finally {
      setLoading(false)
    }
  }, [templateId])

  useEffect(() => { loadNotes() }, [loadNotes])

  const addNote = async () => {
    if (!newBody.trim()) return
    setSaving(true)
    try {
      await createNote(templateId, { body: newBody.trim() })
      setNewBody('')
      await loadNotes()
    } finally {
      setSaving(false)
    }
  }

  const removeNote = async (noteId: string) => {
    await deleteNote(templateId, noteId)
    setNotes((prev) => prev.filter((n) => n.id !== noteId))
  }

  return (
    <div className="space-y-3 max-w-3xl">
      {loading ? (
        <div className="flex items-center gap-2 py-4 text-sm text-slate-500">
          <svg className="animate-spin h-4 w-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          Loading notes…
        </div>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {notes.length === 0 && (
            <p className="text-sm text-slate-400 italic py-2">No notes yet.</p>
          )}
          {notes.map((n) => (
            <div key={n.id} className="group flex items-start gap-2 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2.5">
              <div className="flex-1">
                <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{n.body}</p>
                {n.created_at && (
                  <p className="text-xs text-slate-400 mt-1">{new Date(n.created_at).toLocaleDateString()}</p>
                )}
              </div>
              {!readOnly && (
                <button
                  onClick={() => removeNote(n.id)}
                  className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-red-500 transition-all text-sm shrink-0 mt-0.5"
                  title="Delete note"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {!readOnly && (
        <div className="flex gap-2 pt-2 border-t border-slate-100">
          <textarea
            rows={2}
            placeholder="Add a note…"
            className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 transition-colors"
            value={newBody}
            onChange={(e) => setNewBody(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && e.ctrlKey) addNote() }}
          />
          <button
            onClick={addNote}
            disabled={saving || !newBody.trim()}
            className={`${btn.primary} self-end`}
          >
            {saving ? '…' : 'Add'}
          </button>
        </div>
      )}
    </div>
  )
}
