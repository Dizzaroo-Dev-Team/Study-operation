import React, { useState, FormEvent, useMemo, useRef } from 'react'
import SlashCommandMenu, { SlashCommand } from '@/features/ai/components/SlashCommandMenu'
import { useMessageTemplates, applyTemplate } from '@/features/communications/hooks/useMessageTemplates'

interface SendMessageFormProps {
  onSend: (data: { channel: string; body: string; files?: File[] }) => Promise<void>
  onUploadFile?: (file: File) => Promise<void>
  /** When set, the body text is auto-replaced once the user accepts the AI hint
   *  (Tab key from inside the textarea). */
  aiHint?: string | null
  /** Called when a slash command other than `/template` is picked. Caller
   *  applies workflow side-effects (snooze, resolve, etc.). */
  onSlashCommand?: (cmd: SlashCommand) => void
  /** Display name of the primary participant — used for `{{name}}` template var. */
  participantName?: string
}

const MENTION_EMAIL_RE = /@([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/

const SendMessageForm: React.FC<SendMessageFormProps> = ({
  onSend,
  onUploadFile,
  aiHint,
  onSlashCommand,
  participantName,
}) => {
  const [channel] = useState<'email'>('email')
  const [body, setBody] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { templates } = useMessageTemplates()

  const openTemplateMenu = () => {
    setBody('/')
    setTimeout(() => textareaRef.current?.focus(), 0)
  }

  // Slash-command state. We detect a leading `/` and surface the menu while
  // the user keeps typing. The query is the substring after the slash.
  const slashMatch = useMemo(() => {
    const m = body.match(/^\/([^\n]*)$/)
    return m ? { query: m[1] || '' } : null
  }, [body])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files)
      setFiles((prev) => [...prev, ...selectedFiles])
    }
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const acceptAiHint = () => {
    if (aiHint && aiHint.trim().length > 0) {
      setBody(aiHint)
      setTimeout(() => textareaRef.current?.focus(), 0)
    }
  }

  const handleSlashPick = (cmd: SlashCommand) => {
    if (cmd.kind === 'template' && cmd.templateId) {
      const tmpl = templates.find((t) => t.id === cmd.templateId)
      if (tmpl) {
        const out = applyTemplate(tmpl.body, { name: participantName || 'there' })
        setBody(out)
      }
    } else {
      // Workflow command — let the parent apply the side effect, then clear the slash.
      onSlashCommand?.(cmd)
      setBody('')
    }
    setTimeout(() => textareaRef.current?.focus(), 0)
  }

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!body.trim() && files.length === 0) {
      setError('Message body or file is required')
      return
    }
    if (slashMatch) {
      // Don't send raw slash commands as messages.
      setError('Pick a command from the menu, or remove the leading "/"')
      return
    }

    if (channel === 'email' && body.trim() && !MENTION_EMAIL_RE.test(body)) {
      setError(
        'To send an email, include the recipient as an @mention (e.g. @name@company.com)',
      )
      return
    }

    setLoading(true)
    setError(null)

    try {
      if (files.length > 0 && onUploadFile) {
        for (const file of files) {
          await onUploadFile(file)
        }
      }
      await onSend({ channel, body: body.trim() || '📎 File attached', files })
      setBody('')
      setFiles([])
      if (fileInputRef.current) fileInputRef.current.value = ''
      setError(null)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send message')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full">
      {error && (
        <div className="mb-2 bg-danger-50 border border-danger-500/30 text-danger-600 px-3 py-2 rounded-lg text-ui-body-sm">
          {error}
        </div>
      )}

      {files.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {files.map((file, index) => (
            <div
              key={`${file.name}-${file.size}-${file.lastModified}-${index}`}
              className="flex items-center gap-2 bg-brand-50 border border-brand-500/30 rounded-lg px-2.5 py-1 text-ui-body-sm text-brand-700"
            >
              <span>📎 {file.name}</span>
              <button
                type="button"
                onClick={() => removeFile(index)}
                className="text-brand-700 hover:text-brand-700/70 font-bold"
                aria-label={`Remove ${file.name}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Slash menu floats above the composer when the body starts with `/`. */}
      {slashMatch && (
        <div className="mb-2">
          <SlashCommandMenu
            query={slashMatch.query}
            templates={templates}
            onPick={handleSlashPick}
            onClose={() => setBody('')}
          />
        </div>
      )}

      {/* Discoverable Templates entry point (also available by typing "/"). */}
      <div className="mb-2 flex items-center gap-2">
        <button
          type="button"
          onClick={openTemplateMenu}
          className="px-2.5 py-1 text-ui-caption font-medium text-slate-600 rounded-lg border border-slate-200 hover:bg-slate-50 transition"
          title="Insert a saved template"
        >
          Templates
        </button>
      </div>

      <div className="flex items-end gap-2 bg-white rounded-xl border border-slate-300 shadow-card px-3 py-2.5 focus-within:border-brand-500 focus-within:ring-1 focus-within:ring-brand-500 transition">
        <div
          className="flex-shrink-0 px-1.5 text-slate-500"
          title="Email channel"
          aria-label="Email channel"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="5" width="18" height="14" rx="2" />
            <path d="m3 7 9 6 9-6" />
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <textarea
            ref={textareaRef}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder='Type a message — use @email@domain.com to send email'
            className="w-full px-2 py-1.5 border-0 resize-none text-ui-body focus:outline-none text-slate-900 placeholder-slate-400 bg-transparent"
            rows={1}
            disabled={loading}
            onKeyDown={(e) => {
              // Tab → accept AI hint.
              if (e.key === 'Tab' && aiHint && !body.trim() && !slashMatch) {
                e.preventDefault()
                acceptAiHint()
                return
              }
              if (e.key === 'Enter' && !e.shiftKey && !slashMatch) {
                e.preventDefault()
                handleSubmit(e as any)
              }
            }}
            style={{ maxHeight: '160px', overflowY: 'auto' }}
          />
          {/* Static AI hint preview, shown only when textbox is empty AND there's a suggestion. */}
          {!body.trim() && !slashMatch && aiHint && aiHint.trim().length > 0 && (
            <button
              type="button"
              onClick={acceptAiHint}
              className="mt-1 w-full text-left px-2 py-1 rounded text-ui-caption text-slate-500 hover:bg-slate-50 transition flex items-center gap-2"
              title="Accept this AI suggestion"
              aria-label="Accept AI suggestion"
            >
              <span className="inline-flex items-center px-1 rounded bg-brand-100 text-brand-700 text-[10px] font-semibold tracking-wide">
                AI
              </span>
              <span className="truncate flex-1">{aiHint}</span>
              <kbd className="text-[10px] border border-slate-200 rounded px-1 py-0">Tab</kbd>
            </button>
          )}
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className="hidden"
            id="file-upload"
          />
          <label
            htmlFor="file-upload"
            className="p-2 text-slate-500 hover:text-slate-700 cursor-pointer rounded hover:bg-slate-100 transition"
            title="Attach file"
            aria-label="Attach file"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05 12.25 20.24a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66L9.41 17.42a2 2 0 0 1-2.83-2.83l8.49-8.49" />
            </svg>
          </label>

          <button
            type="submit"
            className={`px-3 py-2 rounded-lg text-ui-body-sm font-medium transition flex items-center justify-center ${
              loading || (!body.trim() && files.length === 0)
                ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                : 'bg-brand-500 text-white hover:bg-brand-600'
            }`}
            disabled={loading || (!body.trim() && files.length === 0)}
            title="Send message (Enter)"
            aria-label="Send message"
          >
            {loading ? (
              <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2 11 13M22 2l-7 20-4-9-9-4Z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </form>
  )
}

export default SendMessageForm
