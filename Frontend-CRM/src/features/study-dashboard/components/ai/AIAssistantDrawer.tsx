/*
 * Floating AI assistant for the study dashboard.
 *
 * - Bottom-right launcher button toggles a slide-in panel.
 * - User types a natural-language question; backend returns an AssistantResponse
 *   (status / narrative / sql / chart / data).
 * - Each AI turn is rendered as a preview AIInsightCard inside the drawer.
 * - "Pin to dashboard" persists the response to localStorage and dispatches a
 *   `study-dashboard:pin` window event so Section10MyInsights picks it up.
 *
 * Pattern intentionally mirrors FloatingAskMeAnything.tsx but is restyled with
 * the mockup CSS tokens so it visually belongs to the CTMS dashboard.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { askAssistant } from '../../services/studyDashboard.api'
import { useSelectedStudy } from '../../context/SelectedStudyContext'
import type { AssistantHistoryTurn, AssistantResponse, PinnedInsight } from '../../types'
import AIInsightCard from './AIInsightCard'

const PIN_STORAGE_KEY = 'study-dashboard.pinned-insights.v1'
const PIN_EVENT = 'study-dashboard:pin'

// Curated starter questions. These are deliberately phrased to map cleanly to
// real columns in the SDTM schema so the LLM produces a chart on the first try.
const SUGGESTED_QUESTIONS: { label: string; q: string; emoji: string }[] = [
  { emoji: '⚠️',  label: 'AE by severity grade',         q: 'How many adverse events at each CTCAE toxicity grade?' },
  { emoji: '👥', label: 'Subjects per arm',              q: 'Show subject count by treatment arm.' },
  { emoji: '🩺', label: 'Top 10 AE preferred terms',     q: 'What are the top 10 preferred terms for adverse events?' },
  { emoji: '📋', label: 'Deviations by category',        q: 'Break down protocol deviations by category.' },
  { emoji: '💀', label: 'Fatal AEs',                     q: 'How many adverse events resulted in death?' },
  { emoji: '🚪', label: 'Discontinuation reasons',       q: 'Show the top reasons subjects discontinued the study.' },
  { emoji: '📅', label: 'Enrolment by month',            q: 'Show monthly enrolment counts over time.' },
  { emoji: '🏥', label: 'Subjects per site',             q: 'How many subjects are enrolled per site?' },
]

interface DrawerTurn {
  id: string
  question: string
  response: AssistantResponse | null
  loading: boolean
  error?: string
  pinned?: boolean
}

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

function loadPinned(): PinnedInsight[] {
  try {
    const raw = localStorage.getItem(PIN_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function savePinned(items: PinnedInsight[]): void {
  try {
    localStorage.setItem(PIN_STORAGE_KEY, JSON.stringify(items))
  } catch {
    /* localStorage may be full or disabled — ignore */
  }
}

const AIAssistantDrawer: React.FC = () => {
  const { selectedStudy } = useSelectedStudy()
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [turns, setTurns] = useState<DrawerTurn[]>([])
  const scrollerRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  // Close on Escape.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  // Autoscroll on new turn.
  useEffect(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight
    }
  }, [turns])

  // Focus input on open.
  useEffect(() => {
    if (open) {
      // small delay so the panel is mounted before we focus
      const t = window.setTimeout(() => inputRef.current?.focus(), 60)
      return () => window.clearTimeout(t)
    }
  }, [open])

  const submitQuestion = useCallback(
    async (rawQuestion: string) => {
      const q = rawQuestion.trim()
      if (!q) return

      const turnId = uid()
      setTurns((prev) => [...prev, { id: turnId, question: q, response: null, loading: true }])
      setInput('')

      // Build history: every prior turn that succeeded (drop loading/errored).
      const history: AssistantHistoryTurn[] = []
      turns.forEach((t) => {
        if (!t.response || t.response.status !== 'ok') return
        history.push({ role: 'user', content: t.question })
        if (t.response.narrative) history.push({ role: 'assistant', content: t.response.narrative })
      })

      try {
        const response = await askAssistant(
          q,
          history,
          selectedStudy.source === 'registry' ? selectedStudy.studyId : undefined,
        )
        setTurns((prev) =>
          prev.map((t) => (t.id === turnId ? { ...t, response, loading: false } : t)),
        )
      } catch (e: any) {
        const msg = e?.response?.data?.detail ?? e?.message ?? 'Request failed'
        setTurns((prev) =>
          prev.map((t) => (t.id === turnId ? { ...t, loading: false, error: String(msg) } : t)),
        )
      }
    },
    [turns, selectedStudy],
  )

  const handleSubmit = useCallback(() => submitQuestion(input), [input, submitQuestion])

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSubmit()
    }
  }

  const handlePin = useCallback((turn: DrawerTurn) => {
    if (!turn.response || turn.response.status !== 'ok') return
    const insight: PinnedInsight = {
      id: uid(),
      question: turn.question,
      pinned_at: new Date().toISOString(),
      response: turn.response,
    }
    const next = [...loadPinned(), insight]
    savePinned(next)
    window.dispatchEvent(new CustomEvent(PIN_EVENT, { detail: insight }))
    setTurns((prev) => prev.map((t) => (t.id === turn.id ? { ...t, pinned: true } : t)))
  }, [])

  return (
    <>
      {/* Launcher */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? 'Close AI assistant' : 'Open AI assistant'}
        title="AI assistant — turn the dashboard dynamic"
        style={{
          // Stacked above the global "Ask Me Anything" launcher (which sits at
          // bottom-5 right-5 = ~20px and is 56px tall). 88 = 20 + 56 + 12 gap.
          position: 'fixed',
          bottom: 88,
          right: 20,
          zIndex: 320,
          height: 52,
          width: 52,
          borderRadius: '50%',
          border: 0,
          color: '#fff',
          cursor: 'pointer',
          background: 'linear-gradient(135deg, #185FA5 0%, #0F6E56 100%)',
          boxShadow: '0 10px 28px rgba(24, 95, 165, 0.35)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {open ? (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        ) : (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 8V4H8" />
            <rect width="16" height="12" x="4" y="8" rx="2" />
            <path d="M2 14h2" />
            <path d="M20 14h2" />
            <path d="M15 13v2" />
            <path d="M9 13v2" />
          </svg>
        )}
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label="AI assistant"
          style={{
            // Sits just above the dashboard-AI launcher (bottom 88 + 52 + 12 gap = 152).
            position: 'fixed',
            bottom: 152,
            right: 20,
            zIndex: 320,
            width: 'min(440px, calc(100vw - 40px))',
            height: 'min(660px, calc(100vh - 180px))',
            background: 'var(--color-background-primary)',
            borderRadius: 12,
            border: '0.5px solid var(--color-border-secondary)',
            boxShadow: '0 24px 48px rgba(0,0,0,0.18)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            color: 'var(--color-text-primary)',
            fontFamily: 'inherit',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '10px 14px',
              background: 'linear-gradient(90deg, #185FA5 0%, #0F6E56 100%)',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>Dashboard AI assistant</span>
              <span style={{ fontSize: 10, opacity: 0.85 }}>
                Ask in natural language. Pin charts to Section 10.
              </span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close"
              style={{
                background: 'rgba(255,255,255,0.15)',
                border: 0,
                color: '#fff',
                borderRadius: 4,
                padding: 4,
                cursor: 'pointer',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            </button>
          </div>

          {/* Conversation */}
          <div
            ref={scrollerRef}
            style={{
              flex: 1,
              minHeight: 0,
              overflowY: 'auto',
              padding: 12,
              background: 'var(--color-background-secondary)',
            }}
          >
            {turns.length === 0 ? (
              <EmptyState onPick={(q) => void submitQuestion(q)} />
            ) : (
              turns.map((t) => (
                <DrawerTurnView key={t.id} turn={t} onPin={() => handlePin(t)} />
              ))
            )}
          </div>

          {/* Composer */}
          <div
            style={{
              padding: 10,
              borderTop: '0.5px solid var(--color-border-tertiary)',
              background: 'var(--color-background-primary)',
            }}
          >
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="e.g. show AE count by severity grade"
              rows={2}
              style={{
                width: '100%',
                resize: 'none',
                padding: 8,
                fontSize: 12,
                fontFamily: 'inherit',
                border: '0.5px solid var(--color-border-tertiary)',
                borderRadius: 6,
                outline: 'none',
                background: 'var(--color-background-primary)',
                color: 'var(--color-text-primary)',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
              <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>
                Enter to send · Shift+Enter for newline
              </span>
              <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={!input.trim()}
                style={{
                  padding: '5px 12px',
                  fontSize: 12,
                  fontWeight: 500,
                  border: 0,
                  borderRadius: 5,
                  cursor: input.trim() ? 'pointer' : 'not-allowed',
                  background: input.trim() ? '#185FA5' : 'var(--color-background-tertiary)',
                  color: input.trim() ? '#fff' : 'var(--color-text-tertiary)',
                }}
              >
                Send
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}

const EmptyState: React.FC<{ onPick: (question: string) => void }> = ({ onPick }) => {
  const { selectedStudy } = useSelectedStudy()
  return (
  <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
    <p style={{ margin: '0 0 10px' }}>
      Ask anything that can be answered from{' '}
      <code>{selectedStudy.databaseName ?? selectedStudy.studyName}</code>. Tap a card to try one:
    </p>
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
        gap: 6,
      }}
    >
      {SUGGESTED_QUESTIONS.map((s) => (
        <button
          key={s.label}
          type="button"
          onClick={() => onPick(s.q)}
          title={s.q}
          style={{
            textAlign: 'left',
            padding: '8px 10px',
            borderRadius: 6,
            border: '0.5px solid var(--color-border-tertiary)',
            background: 'var(--color-background-primary)',
            cursor: 'pointer',
            color: 'var(--color-text-primary)',
            fontSize: 11,
            lineHeight: 1.35,
            display: 'flex',
            flexDirection: 'column',
            gap: 3,
            transition: 'border-color 0.15s, background 0.15s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'var(--color-border-secondary)'
            e.currentTarget.style.background = 'var(--color-background-tertiary)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--color-border-tertiary)'
            e.currentTarget.style.background = 'var(--color-background-primary)'
          }}
        >
          <span style={{ fontSize: 13 }}>
            <span style={{ marginRight: 6 }}>{s.emoji}</span>
            <span style={{ fontWeight: 600 }}>{s.label}</span>
          </span>
          <span style={{ color: 'var(--color-text-secondary)' }}>{s.q}</span>
        </button>
      ))}
    </div>
    <p style={{ margin: '12px 0 0', fontSize: 11 }}>
      If the data isn't in the schema, the assistant says so instead of guessing.
    </p>
  </div>
  )
}

const DrawerTurnView: React.FC<{ turn: DrawerTurn; onPin: () => void }> = ({ turn, onPin }) => {
  return (
    <div style={{ marginBottom: 12 }}>
      {/* Question bubble */}
      <div
        style={{
          background: 'var(--color-background-primary)',
          padding: '6px 10px',
          borderRadius: 6,
          fontSize: 12,
          fontWeight: 500,
          marginBottom: 6,
          border: '0.5px solid var(--color-border-tertiary)',
        }}
      >
        {turn.question}
      </div>

      {turn.loading ? (
        <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', padding: '4px 2px' }}>
          Thinking…
        </div>
      ) : turn.error ? (
        <div className="cc" style={{ borderLeft: '3px solid var(--color-text-danger)' }}>
          <div className="ct" style={{ color: 'var(--color-text-danger)' }}>Error</div>
          <p style={{ margin: 0, fontSize: 12 }}>{turn.error}</p>
        </div>
      ) : turn.response ? (
        <>
          <AIInsightCard response={turn.response} compact />
          {turn.response.status === 'ok' ? (
            <div style={{ marginTop: 6, textAlign: 'right' }}>
              <button
                type="button"
                onClick={onPin}
                disabled={turn.pinned}
                style={{
                  fontSize: 11,
                  padding: '4px 10px',
                  border: '0.5px solid var(--color-border-secondary)',
                  borderRadius: 4,
                  cursor: turn.pinned ? 'default' : 'pointer',
                  background: turn.pinned ? 'var(--color-background-success)' : 'var(--color-background-primary)',
                  color: turn.pinned ? 'var(--color-text-success)' : 'var(--color-text-primary)',
                }}
              >
                {turn.pinned ? '✓ Pinned to dashboard' : '📌 Pin to dashboard'}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

export default AIAssistantDrawer
