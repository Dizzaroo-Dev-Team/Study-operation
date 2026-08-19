import { Mark, mergeAttributes } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'

export interface LockedOptions {
  HTMLAttributes: Record<string, any>
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    locked: {
      /**
       * Set a locked mark
       */
      setLocked: () => ReturnType
      /**
       * Toggle a locked mark
       */
      toggleLocked: () => ReturnType
      /**
       * Unset a locked mark
       */
      unsetLocked: () => ReturnType
    }
  }
}

export const LockedMark = Mark.create<LockedOptions>({
  name: 'locked',

  addOptions() {
    return {
      HTMLAttributes: {},
    }
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-locked="true"]',
      },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    return ['span', mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, { 'data-locked': 'true' }), 0]
  },

  addAttributes() {
    return {
      locked: {
        default: true,
        parseHTML: element => element.getAttribute('data-locked') === 'true',
        renderHTML: attributes => {
          if (!attributes.locked) {
            return {}
          }
          return {
            'data-locked': 'true',
          }
        },
      },
    }
  },

  addCommands() {
    return {
      setLocked: () => ({ commands }) => {
        return commands.setMark(this.name)
      },
      toggleLocked: () => ({ commands }) => {
        return commands.toggleMark(this.name)
      },
      unsetLocked: () => ({ commands }) => {
        return commands.unsetMark(this.name)
      },
    }
  },

  // Prevent editing of locked content
  addKeyboardShortcuts() {
    return {
      Backspace: () => {
        if (!this.editor.isEditable) return false
        const { state } = this.editor
        const { selection } = state
        const { $from } = selection
        
        // Check if we're in a locked mark
        const lockedMark = state.schema.marks.locked
        if (lockedMark && $from.marks().some(mark => mark.type === lockedMark)) {
          return true // Prevent deletion
        }
        return false
      },
      Delete: () => {
        if (!this.editor.isEditable) return false
        const { state } = this.editor
        const { selection } = state
        const { $from } = selection
        
        // Check if we're in a locked mark
        const lockedMark = state.schema.marks.locked
        if (lockedMark && $from.marks().some(mark => mark.type === lockedMark)) {
          return true // Prevent deletion
        }
        return false
      },
    }
  },

  // Prevent text input in locked marks
  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey('preventLockedEditing'),
        props: {
          handleTextInput: (view: any, from: number, _to: number, _text: string) => {
            if (!view.editable) return false
            const { state } = view
            const $from = state.doc.resolve(from)
            const lockedMark = state.schema.marks.locked
            
            if (lockedMark && $from.marks().some((mark: any) => mark.type === lockedMark)) {
              return true // Prevent text input
            }
            return false
          },
          handleKeyDown: (view: any, event: KeyboardEvent) => {
            if (!view.editable) return false
            const { state } = view
            const { selection } = state
            const { $from } = selection
            const lockedMark = state.schema.marks.locked
            
            // Prevent editing if cursor is in locked mark
            if (lockedMark && $from.marks().some((mark: any) => mark.type === lockedMark)) {
              // Allow navigation keys
              if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) {
                return false
              }
              // Allow Ctrl/Cmd combinations for copy, select all, etc.
              if ((event.ctrlKey || event.metaKey) && ['a', 'c', 'x', 'v'].includes(event.key.toLowerCase())) {
                // Allow copy (c) and select all (a), but prevent cut (x) and paste (v) in locked areas
                if (event.key.toLowerCase() === 'x' || event.key.toLowerCase() === 'v') {
                  return true
                }
                return false
              }
              // Prevent all other keys (typing, deletion, etc.)
              return true
            }
            return false
          },
        },
      }),
    ]
  },
})
