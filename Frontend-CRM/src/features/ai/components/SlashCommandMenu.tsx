import React, { useEffect, useMemo, useState } from 'react'
import { MessageTemplate } from '@/features/communications/hooks/useMessageTemplates'

export type SlashCommandKind =
  | 'summary'
  | 'task'
  | 'template'
  | 'snooze'
  | 'escalate'
  | 'resolve'

export interface SlashCommand {
  kind: SlashCommandKind
  label: string
  description: string
  /** Optional template id for `kind = 'template'`. */
  templateId?: string
}

interface SlashCommandMenuProps {
  /** Text after the leading `/`. Empty string = show every command. */
  query: string
  templates: MessageTemplate[]
  /** When the user picks a command — caller is responsible for state mutation. */
  onPick: (cmd: SlashCommand) => void
  /** When the menu wants to close itself (esc, click-out). */
  onClose: () => void
}

const BASE_COMMANDS: SlashCommand[] = [
  { kind: 'summary', label: '/summary', description: 'Insert the AI summary of this thread' },
  { kind: 'task', label: '/task', description: 'Promote this draft to a task' },
  { kind: 'snooze', label: '/snooze', description: 'Snooze this conversation' },
  { kind: 'resolve', label: '/resolve', description: 'Mark this conversation as resolved' },
  { kind: 'escalate', label: '/escalate', description: 'Set priority to urgent' },
]

/**
 * Compact floating menu that filters slash commands as the user types.
 * Designed to sit above the composer; the parent positions it.
 */
const SlashCommandMenu: React.FC<SlashCommandMenuProps> = ({
  query,
  templates,
  onPick,
  onClose,
}) => {
  const [activeIndex, setActiveIndex] = useState(0)

  const commands = useMemo<SlashCommand[]>(() => {
    const q = query.trim().toLowerCase()
    const templated: SlashCommand[] = templates.map((t) => ({
      kind: 'template',
      label: `/template ${t.name}`,
      description: 'Insert message template',
      templateId: t.id,
    }))
    const all = [...BASE_COMMANDS, ...templated]
    if (!q) return all
    return all.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q),
    )
  }, [query, templates])

  useEffect(() => setActiveIndex(0), [query, commands.length])

  // Bind global key handler — Arrow keys + Enter pick, Esc closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIndex((i) => Math.min(i + 1, Math.max(commands.length - 1, 0)))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === 'Enter') {
        const cmd = commands[activeIndex]
        if (cmd) {
          e.preventDefault()
          onPick(cmd)
        }
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [commands, activeIndex, onPick, onClose])

  if (commands.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg shadow-popover w-full max-w-md py-2 px-3 text-ui-body-sm text-slate-500">
        No matching command.
      </div>
    )
  }

  return (
    <div
      className="bg-white border border-slate-200 rounded-lg shadow-popover w-full max-w-md py-1 overflow-hidden"
      role="listbox"
      aria-label="Slash commands"
    >
      <div className="px-3 py-1.5 text-ui-caption uppercase tracking-wide text-slate-400 border-b border-slate-100">
        Commands
      </div>
      <ul>
        {commands.map((cmd, idx) => (
          <li
            key={`${cmd.kind}-${cmd.templateId ?? idx}`}
            role="option"
            aria-selected={idx === activeIndex}
            onMouseEnter={() => setActiveIndex(idx)}
            onMouseDown={(e) => {
              // Use mouseDown to fire before the input loses focus.
              e.preventDefault()
              onPick(cmd)
            }}
            className={`px-3 py-1.5 cursor-pointer flex items-center justify-between gap-3 ${
              idx === activeIndex ? 'bg-brand-50' : 'hover:bg-slate-50'
            }`}
          >
            <div className="min-w-0">
              <p className="text-ui-body text-slate-900 font-mono">{cmd.label}</p>
              <p className="text-ui-caption text-slate-500 truncate">{cmd.description}</p>
            </div>
            {idx === activeIndex && (
              <kbd className="text-ui-caption text-slate-400 border border-slate-200 rounded px-1.5 py-0.5">
                ↵
              </kbd>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default SlashCommandMenu
