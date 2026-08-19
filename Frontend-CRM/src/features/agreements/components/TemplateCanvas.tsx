/**
 * TemplateCanvas — Tiptap editor for composing clause-based agreement templates.
 *
 * Distinct from AgreementEditor.tsx (which is the review/signing editor).
 * Differences:
 *   - Uses ClauseBlock node extension instead of LockedMark
 *   - Has an "Insert Clause" command API (parent injects clauses)
 *   - Has a server-side lock-validation step before saving
 *   - Save path goes to clause override or reorder endpoints, not a version blob
 */
import React, { useEffect, useImperativeHandle, forwardRef, useCallback } from 'react'
import { useEditor, EditorContent, type JSONContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import Image from '@tiptap/extension-image'
import { ClauseBlock, type ClauseBlockAttrs } from '../extensions/ClauseBlock'
import type { Clause } from '../services/clauseService'

export interface TemplateCanvasHandle {
  /** Get the current editor JSON content */
  getJSON: () => Record<string, unknown> | null
  /** Insert a clause block at the current cursor position (or end of doc) */
  insertClause: (clause: Clause) => void
}

interface TemplateCanvasProps {
  /** Initial Tiptap JSON from the materialised template */
  initialContent: Record<string, unknown> | null
  /** Whether the editor is in read-only mode */
  readOnly?: boolean
  /** Called after content changes; debounced by the parent */
  onChange?: (json: Record<string, unknown>) => void
}

const TemplateCanvas = forwardRef<TemplateCanvasHandle, TemplateCanvasProps>(
  ({ initialContent, readOnly = false, onChange }, ref) => {
    const editor = useEditor({
      extensions: [
        StarterKit,
        Table.configure({ resizable: true }),
        TableRow,
        TableHeader,
        TableCell,
        Image,
        ClauseBlock,
      ],
      content: initialContent || { type: 'doc', content: [] },
      editable: !readOnly,
      onUpdate: ({ editor: ed }) => {
        onChange?.(ed.getJSON() as Record<string, unknown>)
      },
    })

    // Sync readOnly changes
    useEffect(() => {
      if (editor) editor.setEditable(!readOnly)
    }, [editor, readOnly])

    // Sync external content changes (e.g. after inserting a clause via the API)
    useEffect(() => {
      if (!editor || !initialContent) return
      const current  = JSON.stringify(editor.getJSON())
      const incoming = JSON.stringify(initialContent)
      if (current !== incoming) {
        editor.commands.setContent(initialContent)
      }
    }, [editor, initialContent])

    // Expose imperative API to parent
    useImperativeHandle(ref, () => ({
      getJSON: () => {
        if (!editor) return null
        return editor.getJSON() as Record<string, unknown>
      },

      insertClause: (clause: Clause) => {
        if (!editor || !clause.current_version) return

        const attrs: ClauseBlockAttrs = {
          clauseId:    clause.id,
          versionId:   clause.current_version_id,
          lockPolicy:  clause.lock_policy,
          isLocked:    clause.lock_policy === 'STANDARD_LOCKED',
          isEditable:  clause.lock_policy === 'EDITABLE',
          clauseTitle: clause.title,
          category:    clause.category,
        }

        // Use the clause's current version content as the initial block content
        const clauseContent = clause.current_version.content_json

        editor.commands.insertContent({
          type: 'clauseBlock',
          attrs,
          // Extract inner block array from the stored doc shape
          content: ((clauseContent as Record<string, unknown>)?.content as JSONContent[] | undefined) ?? [
            { type: 'paragraph' },
          ],
        })
      },
    }))

    const handleHeading = useCallback(
      (level: 1 | 2) => () =>
        editor?.chain().focus().toggleHeading({ level }).run(),
      [editor],
    )

    if (!editor) {
      return (
        <div className="flex h-full items-center justify-center text-sm text-gray-400">
          Loading editor…
        </div>
      )
    }

    return (
      <div className="flex h-full flex-col">
        {/* Toolbar */}
        {!readOnly && (
          <div className="flex flex-wrap items-center gap-1 border-b border-gray-200 bg-gray-50 px-3 py-2">
            <ToolbarBtn
              active={editor.isActive('bold')}
              onClick={() => editor.chain().focus().toggleBold().run()}
              label={<strong>B</strong>}
            />
            <ToolbarBtn
              active={editor.isActive('italic')}
              onClick={() => editor.chain().focus().toggleItalic().run()}
              label={<em>I</em>}
            />
            <Divider />
            <ToolbarBtn
              active={editor.isActive('heading', { level: 1 })}
              onClick={handleHeading(1)}
              label="H1"
            />
            <ToolbarBtn
              active={editor.isActive('heading', { level: 2 })}
              onClick={handleHeading(2)}
              label="H2"
            />
            <Divider />
            <ToolbarBtn
              active={editor.isActive('bulletList')}
              onClick={() => editor.chain().focus().toggleBulletList().run()}
              label="• List"
            />
            <ToolbarBtn
              active={editor.isActive('orderedList')}
              onClick={() => editor.chain().focus().toggleOrderedList().run()}
              label="1. List"
            />
            <Divider />
            <span className="ml-1 text-xs text-gray-400">
              ← Use the Clause Library panel to insert clauses
            </span>
          </div>
        )}

        {/* Editor */}
        <div className="flex-1 overflow-y-auto bg-white p-6">
          <EditorContent
            editor={editor}
            className="prose max-w-none min-h-full focus:outline-none"
          />
          {!readOnly && (
            <p className="mt-6 text-center text-xs text-gray-300">
              Locked clauses (amber border) cannot be edited. Click ▲▼ to reorder.
            </p>
          )}
        </div>
      </div>
    )
  },
)

TemplateCanvas.displayName = 'TemplateCanvas'
export default TemplateCanvas

// ---------------------------------------------------------------------------
// Toolbar helpers (private to this file)
// ---------------------------------------------------------------------------

interface ToolbarBtnProps {
  active: boolean
  onClick: () => void
  label: React.ReactNode
}

const ToolbarBtn: React.FC<ToolbarBtnProps> = ({ active, onClick, label }) => (
  <button
    type="button"
    onMouseDown={(e) => {
      e.preventDefault()
      onClick()
    }}
    className={[
      'rounded px-2.5 py-1 text-sm transition',
      active
        ? 'bg-indigo-600 text-white'
        : 'bg-white text-gray-700 hover:bg-gray-100 border border-gray-200',
    ].join(' ')}
  >
    {label}
  </button>
)

const Divider: React.FC = () => (
  <div className="mx-1 h-5 w-px bg-gray-300" />
)
