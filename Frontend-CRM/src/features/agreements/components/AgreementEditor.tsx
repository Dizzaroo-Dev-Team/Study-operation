import React, { useEffect, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import Image from '@tiptap/extension-image'
import { LockedMark } from '@/features/agreements/extensions/LockedMark'

interface AgreementEditorProps {
  content: any // TipTap JSON content
  canEdit: boolean
  onSave?: (content: any) => void
  isLoading?: boolean
  onHasChangesChange?: (hasChanges: boolean) => void // Callback to notify parent of unsaved changes
}

const AgreementEditor: React.FC<AgreementEditorProps> = ({
  content,
  canEdit,
  onSave,
  isLoading = false,
  onHasChangesChange,
}) => {
  const [isSaving, setIsSaving] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  
  // Notify parent when hasChanges changes
  useEffect(() => {
    if (onHasChangesChange) {
      onHasChangesChange(hasChanges)
    }
  }, [hasChanges, onHasChangesChange])

  const editor = useEditor({
    extensions: [
      StarterKit,
      Table.configure({
        resizable: true,
      }),
      TableRow,
      TableHeader,
      TableCell,
      Image,
      LockedMark
    ],
    content: content || { type: 'doc', content: [] },
    editable: canEdit,
    onUpdate: ({ editor }) => {
      // Check if the update is trying to modify locked content
      const { state } = editor.view
      const { selection } = state
      const { $from } = selection
      const lockedMark = state.schema.marks.locked
      
      // If editing locked content, prevent the update
      if (lockedMark && $from.marks().some(mark => mark.type === lockedMark)) {
        // Revert the change
        editor.commands.setContent(content)
        return
      }
      
      // Mark as having changes when user edits
      setHasChanges(true)
    },
  })

  useEffect(() => {
    if (editor && content) {
      // Only reset changes if content actually changed from external source
      const currentContent = editor.getJSON()
      const contentStr = JSON.stringify(currentContent)
      const newContentStr = JSON.stringify(content)
      
      if (contentStr !== newContentStr) {
        editor.commands.setContent(content)
        setHasChanges(false)
      }
    }
  }, [content, editor])

  // Update editor editable state when canEdit changes
  useEffect(() => {
    if (editor) {
      editor.setEditable(canEdit)
    }
  }, [editor, canEdit])

  const handleSave = async () => {
    if (!editor || !onSave || !hasChanges || isSaving) return

    setIsSaving(true)
    try {
      const jsonContent = editor.getJSON()
      await onSave(jsonContent)
      // Clear changes flag after successful save
      setHasChanges(false)
      // Notify parent that changes are cleared
      if (onHasChangesChange) {
        onHasChangesChange(false)
      }
    } catch (error) {
      console.error('Failed to save document:', error)
      // Keep hasChanges as true if save failed
    } finally {
      setIsSaving(false)
    }
  }


  if (!editor) {
    return <div className="p-4 text-gray-600">Loading editor...</div>
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar - Always show when canEdit is true */}
      {canEdit ? (
        <div className="border-b border-gray-200 p-2 bg-gray-50 flex items-center gap-2 flex-wrap">
          <button
            onClick={() => editor.chain().focus().toggleBold().run()}
            disabled={!editor.can().chain().focus().toggleBold().run()}
            className={`px-3 py-1 rounded text-sm ${
              editor.isActive('bold')
                ? 'bg-blue-500 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            <strong>B</strong>
          </button>
          <button
            onClick={() => editor.chain().focus().toggleItalic().run()}
            disabled={!editor.can().chain().focus().toggleItalic().run()}
            className={`px-3 py-1 rounded text-sm ${
              editor.isActive('italic')
                ? 'bg-blue-500 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            <em>I</em>
          </button>
          <div className="w-px h-6 bg-gray-300 mx-1" />
          <button
            onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
            className={`px-3 py-1 rounded text-sm ${
              editor.isActive('heading', { level: 1 })
                ? 'bg-blue-500 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            H1
          </button>
          <button
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            className={`px-3 py-1 rounded text-sm ${
              editor.isActive('heading', { level: 2 })
                ? 'bg-blue-500 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            H2
          </button>
          <div className="w-px h-6 bg-gray-300 mx-1" />
          <button
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            className={`px-3 py-1 rounded text-sm ${
              editor.isActive('bulletList')
                ? 'bg-blue-500 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            • List
          </button>
          <button
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            className={`px-3 py-1 rounded text-sm ${
              editor.isActive('orderedList')
                ? 'bg-blue-500 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-100'
            }`}
          >
            1. List
          </button>
          <div className="flex-1" />
          <button
            onClick={handleSave}
            disabled={!hasChanges || isSaving || isLoading}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              hasChanges && !isSaving && !isLoading
                ? 'bg-blue-600 text-white hover:bg-blue-700'
                : 'bg-gray-400 text-gray-200 cursor-not-allowed'
            }`}
            title={hasChanges ? 'Save changes to create new version' : 'No changes to save'}
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
          {!hasChanges && (
            <span className="text-xs text-gray-500 ml-2">Make changes to enable save</span>
          )}
        </div>
      ) : (
        <div className="border-b border-gray-200 p-2 bg-yellow-50 text-xs text-yellow-800 text-center">
          Editor is in read-only mode. Editing is not allowed for this version.
        </div>
      )}

      {/* Editor Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <EditorContent
          editor={editor}
          className="prose max-w-none min-h-full focus:outline-none"
        />
        <style>{`
          [data-locked="true"] {
            background-color: #fef3c7;
            padding: 2px 4px;
            border-radius: 3px;
            cursor: not-allowed;
            user-select: none;
          }
          [data-locked="true"]::after {
            content: " 🔒";
            font-size: 0.8em;
            opacity: 0.6;
          }
        `}</style>
      </div>

      {/* Read-only indicator */}
      {!canEdit && (
        <div className="border-t border-gray-200 p-2 bg-gray-50 text-xs text-gray-600 text-center">
          Read-only mode
        </div>
      )}
    </div>
  )
}

export default AgreementEditor
