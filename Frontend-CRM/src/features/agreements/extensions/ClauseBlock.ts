/**
 * ClauseBlock — Tiptap custom NODE extension for the clause library.
 *
 * This is a BLOCK-LEVEL NODE, not a Mark.  Using a node (instead of
 * extending LockedMark) gives us:
 *   - Atomic reorder: the whole clause moves as one unit
 *   - Per-clause lock state in attrs (not a character-range mark)
 *   - A NodeView with header bar, badge, and move buttons
 *   - filterTransaction ProseMirror plugin that is the REAL lock enforcement
 *     on the client side (server also validates via /templates/{id}/validate-locks)
 *
 * Node schema:
 *   group:   'block'
 *   content: 'block+'    (paragraphs, headings, lists, tables)
 *   attrs:
 *     clauseId    string  — database Clause.id
 *     versionId   string  — ClauseVersion.id used (for display)
 *     lockPolicy  string  — 'STANDARD_LOCKED' | 'EDITABLE' | 'ALTERNATE'
 *     isLocked    bool    — per-template override (true = prevent all edits)
 *     isEditable  bool    — per-template flag (editable slot)
 *     clauseTitle string  — for NodeView header; NOT persisted to DB separately
 *     category    string  — for NodeView badge
 */
import { Node, mergeAttributes } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'

export interface ClauseBlockOptions {
  HTMLAttributes: Record<string, unknown>
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    clauseBlock: {
      /** Insert a clauseBlock node at the current position */
      insertClauseBlock: (attrs: ClauseBlockAttrs) => ReturnType
      /** Move a clauseBlock up by one position */
      moveClauseBlockUp: (pos: number) => ReturnType
      /** Move a clauseBlock down by one position */
      moveClauseBlockDown: (pos: number) => ReturnType
    }
  }
}

export interface ClauseBlockAttrs {
  clauseId: string
  versionId: string | null
  lockPolicy: string
  isLocked: boolean
  isEditable: boolean
  clauseTitle: string
  category: string
}

const LOCK_PLUGIN_KEY = new PluginKey('clauseBlockLock')

export const ClauseBlock = Node.create<ClauseBlockOptions>({
  name: 'clauseBlock',
  group: 'block',
  content: 'block+',
  defining: true,   // copy attrs when splitting
  isolating: false, // allow cursor to enter/exit

  addOptions() {
    return { HTMLAttributes: {} }
  },

  addAttributes() {
    return {
      clauseId:   { default: null },
      versionId:  { default: null },
      lockPolicy: { default: 'STANDARD_LOCKED' },
      isLocked:   { default: true },
      isEditable: { default: false },
      clauseTitle:{ default: '' },
      category:   { default: '' },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-clause-block]' }]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        'data-clause-block':  'true',
        'data-clause-id':     node.attrs.clauseId,
        'data-version-id':    node.attrs.versionId,
        'data-lock-policy':   node.attrs.lockPolicy,
        'data-is-locked':     String(node.attrs.isLocked),
        'data-category':      node.attrs.category,
        class: [
          'clause-block',
          node.attrs.isLocked ? 'clause-block--locked' : 'clause-block--editable',
        ].join(' '),
      }),
      0,  // contentDOM placeholder
    ]
  },

  addCommands() {
    return {
      insertClauseBlock: (attrs: ClauseBlockAttrs) => ({ commands }) => {
        return commands.insertContent({
          type: this.name,
          attrs,
          content: [{ type: 'paragraph' }],
        })
      },

      moveClauseBlockUp: (pos: number) => ({ state, dispatch }) => {
        const { doc, tr } = state
        const $pos = doc.resolve(pos)
        const nodeIndex = $pos.index($pos.depth - 1)
        if (nodeIndex === 0) return false  // already first

        const parent = $pos.node($pos.depth - 1)
        const prevChild = parent.child(nodeIndex - 1)
        const thisChild = parent.child(nodeIndex)

        // Swap by deleting both and re-inserting in reverse order
        const thisStart = $pos.before($pos.depth)
        const prevStart = thisStart - prevChild.nodeSize

        tr.delete(prevStart, thisStart + thisChild.nodeSize)
        tr.insert(prevStart, [thisChild, prevChild])

        if (dispatch) dispatch(tr)
        return true
      },

      moveClauseBlockDown: (pos: number) => ({ state, dispatch }) => {
        const { doc, tr } = state
        const $pos = doc.resolve(pos)
        const nodeIndex = $pos.index($pos.depth - 1)
        const parent = $pos.node($pos.depth - 1)
        if (nodeIndex >= parent.childCount - 1) return false  // already last

        const thisChild = parent.child(nodeIndex)
        const nextChild = parent.child(nodeIndex + 1)

        const thisStart = $pos.before($pos.depth)
        const nextEnd   = thisStart + thisChild.nodeSize + nextChild.nodeSize

        tr.delete(thisStart, nextEnd)
        tr.insert(thisStart, [nextChild, thisChild])

        if (dispatch) dispatch(tr)
        return true
      },
    }
  },

  addNodeView() {
    return ({ node, getPos, editor }) => {
      // -------- outer wrapper --------
      const dom = document.createElement('div')
      dom.className = [
        'clause-block',
        node.attrs.isLocked ? 'clause-block--locked' : 'clause-block--editable',
      ].join(' ')
      dom.setAttribute('data-clause-block', 'true')
      dom.setAttribute('data-clause-id', node.attrs.clauseId ?? '')

      // -------- header bar --------
      const header = document.createElement('div')
      header.className = 'clause-block__header'
      header.contentEditable = 'false'

      const title = document.createElement('span')
      title.className = 'clause-block__title'
      title.textContent = node.attrs.clauseTitle || 'Clause'

      const badge = document.createElement('span')
      badge.className = `clause-block__badge clause-block__badge--${(node.attrs.lockPolicy || '').toLowerCase().replace('_', '-')}`
      badge.textContent = node.attrs.isLocked ? '🔒 Locked' : '✏️ Editable'

      const categoryBadge = document.createElement('span')
      categoryBadge.className = 'clause-block__category'
      categoryBadge.textContent = node.attrs.category || ''

      // Move Up / Down buttons
      const btnUp = document.createElement('button')
      btnUp.className = 'clause-block__btn'
      btnUp.type = 'button'
      btnUp.title = 'Move clause up'
      btnUp.textContent = '▲'
      btnUp.addEventListener('mousedown', (e) => {
        e.preventDefault()
        const pos = typeof getPos === 'function' ? getPos() : null
        if (pos != null) editor.commands.moveClauseBlockUp(pos)
      })

      const btnDown = document.createElement('button')
      btnDown.className = 'clause-block__btn'
      btnDown.type = 'button'
      btnDown.title = 'Move clause down'
      btnDown.textContent = '▼'
      btnDown.addEventListener('mousedown', (e) => {
        e.preventDefault()
        const pos = typeof getPos === 'function' ? getPos() : null
        if (pos != null) editor.commands.moveClauseBlockDown(pos)
      })

      header.appendChild(title)
      header.appendChild(categoryBadge)
      header.appendChild(badge)
      header.appendChild(btnUp)
      header.appendChild(btnDown)

      // -------- content area --------
      const contentDOM = document.createElement('div')
      contentDOM.className = 'clause-block__content'

      dom.appendChild(header)
      dom.appendChild(contentDOM)

      return {
        dom,
        contentDOM,
        update(updatedNode) {
          if (updatedNode.type.name !== 'clauseBlock') return false
          // Re-sync lock state visual
          dom.className = [
            'clause-block',
            updatedNode.attrs.isLocked ? 'clause-block--locked' : 'clause-block--editable',
          ].join(' ')
          badge.textContent = updatedNode.attrs.isLocked ? '🔒 Locked' : '✏️ Editable'
          title.textContent  = updatedNode.attrs.clauseTitle || 'Clause'
          categoryBadge.textContent = updatedNode.attrs.category || ''
          return true
        },
      }
    }
  },

  // ---------------------------------------------------------------------------
  // ProseMirror plugin: filterTransaction (CLIENT-SIDE lock gate)
  //
  // Prevents any transaction from mutating the content of a locked clauseBlock.
  // Note: the server also validates via POST /templates/{id}/validate-locks —
  // this is the client-side UX guard, not the security gate.
  // ---------------------------------------------------------------------------
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: LOCK_PLUGIN_KEY,
        filterTransaction(tr, state) {
          if (!tr.docChanged) return true

          let blocked = false

          tr.steps.forEach((step) => {
            if (blocked) return
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const map = (step as any).getMap?.()
            if (!map) return

            map.forEach((oldStart: number, oldEnd: number) => {
              if (blocked) return
              // Walk nodes in the old range to see if any are locked clauseBlocks
              state.doc.nodesBetween(oldStart, oldEnd, (node) => {
                if (
                  node.type.name === 'clauseBlock' &&
                  node.attrs.isLocked === true
                ) {
                  blocked = true
                }
              })
            })
          })

          return !blocked
        },
      }),
    ]
  },
})

// ---------------------------------------------------------------------------
// Companion CSS — injected at load time (no separate .css file needed)
// ---------------------------------------------------------------------------
const CLAUSE_BLOCK_CSS = `
.clause-block {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  margin: 12px 0;
  overflow: hidden;
  transition: border-color 0.15s;
}
.clause-block:focus-within {
  border-color: #6366f1;
}
.clause-block--locked {
  border-color: #fbbf24;
  background: #fffbeb;
}
.clause-block--editable {
  border-color: #6ee7b7;
  background: #f0fdf4;
}

.clause-block__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-size: 12px;
  user-select: none;
}
.clause-block--locked .clause-block__header {
  background: #fef3c7;
  border-bottom-color: #fbbf24;
}
.clause-block--editable .clause-block__header {
  background: #d1fae5;
  border-bottom-color: #6ee7b7;
}

.clause-block__title {
  font-weight: 600;
  color: #111827;
  flex: 1;
}
.clause-block__category {
  font-size: 11px;
  background: #e5e7eb;
  color: #6b7280;
  padding: 1px 6px;
  border-radius: 9999px;
}
.clause-block__badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 9999px;
}
.clause-block__badge--standard-locked {
  background: #fef3c7;
  color: #92400e;
}
.clause-block__badge--editable {
  background: #d1fae5;
  color: #065f46;
}
.clause-block__badge--alternate {
  background: #ede9fe;
  color: #5b21b6;
}

.clause-block__btn {
  background: none;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 1px 5px;
  cursor: pointer;
  font-size: 10px;
  color: #6b7280;
  line-height: 1.2;
}
.clause-block__btn:hover {
  background: #f3f4f6;
  border-color: #9ca3af;
}

.clause-block__content {
  padding: 12px 16px;
  min-height: 40px;
}
.clause-block--locked .clause-block__content {
  cursor: not-allowed;
  color: #374151;
}
`

if (typeof document !== 'undefined' && !document.getElementById('clause-block-styles')) {
  const style = document.createElement('style')
  style.id = 'clause-block-styles'
  style.textContent = CLAUSE_BLOCK_CSS
  document.head.appendChild(style)
}
