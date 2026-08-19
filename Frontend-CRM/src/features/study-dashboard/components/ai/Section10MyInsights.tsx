/*
 * Section 10 — "My AI Insights".
 *
 * Renders all pinned insights stored in localStorage. Listens to the
 * `study-dashboard:pin` custom event so it updates instantly when the drawer
 * pins a new card. Each card has a remove (×) button and an in-place card
 * rendered by AIInsightCard.
 */
import React, { useCallback, useEffect, useState } from 'react'
import type { PinnedInsight } from '../../types'
import AIInsightCard from './AIInsightCard'

const PIN_STORAGE_KEY = 'study-dashboard.pinned-insights.v1'
const PIN_EVENT = 'study-dashboard:pin'
const UNPIN_EVENT = 'study-dashboard:unpin'

function readPinned(): PinnedInsight[] {
  try {
    const raw = localStorage.getItem(PIN_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writePinned(items: PinnedInsight[]): void {
  try {
    localStorage.setItem(PIN_STORAGE_KEY, JSON.stringify(items))
  } catch {
    /* ignore */
  }
}

const Section10MyInsights: React.FC = () => {
  const [items, setItems] = useState<PinnedInsight[]>(() => readPinned())

  useEffect(() => {
    const onPin = (e: Event) => {
      const detail = (e as CustomEvent<PinnedInsight>).detail
      if (!detail) return
      setItems((prev) => [...prev, detail])
    }
    const onUnpin = (e: Event) => {
      const id = (e as CustomEvent<string>).detail
      setItems((prev) => prev.filter((p) => p.id !== id))
    }
    // localStorage changes from other tabs
    const onStorage = (e: StorageEvent) => {
      if (e.key === PIN_STORAGE_KEY) setItems(readPinned())
    }
    window.addEventListener(PIN_EVENT, onPin)
    window.addEventListener(UNPIN_EVENT, onUnpin)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(PIN_EVENT, onPin)
      window.removeEventListener(UNPIN_EVENT, onUnpin)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  const remove = useCallback((id: string) => {
    setItems((prev) => {
      const next = prev.filter((p) => p.id !== id)
      writePinned(next)
      return next
    })
  }, [])

  const clearAll = useCallback(() => {
    if (!confirm('Remove all pinned insights?')) return
    setItems([])
    writePinned([])
  }, [])

  return (
    <section className="sec" id="d10">
      <h3>
        <span className="num">10</span> My AI insights
        <span className="live-badge">Live · pinned by you</span>
      </h3>
      <p className="sub">
        Charts and tables added via the AI assistant in the bottom-right. Stored locally in your
        browser.
      </p>

      {items.length === 0 ? (
        <div className="cc">
          <div className="ct">Nothing pinned yet</div>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--color-text-secondary)' }}>
            Click the floating button at the bottom-right, ask a question, then press
            <strong> Pin to dashboard </strong>
            on any answer to add it here.
          </p>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {items.map((p) => (
              <PinnedCard key={p.id} insight={p} onRemove={() => remove(p.id)} />
            ))}
          </div>
          <div style={{ marginTop: 8, textAlign: 'right' }}>
            <button
              type="button"
              onClick={clearAll}
              style={{
                fontSize: 11,
                padding: '3px 8px',
                background: 'transparent',
                color: 'var(--color-text-secondary)',
                border: '0.5px solid var(--color-border-tertiary)',
                borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              Clear all
            </button>
          </div>
        </>
      )}
    </section>
  )
}

const PinnedCard: React.FC<{ insight: PinnedInsight; onRemove: () => void }> = ({
  insight,
  onRemove,
}) => {
  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={onRemove}
        aria-label="Remove insight"
        title="Remove"
        style={{
          position: 'absolute',
          top: 6,
          right: 8,
          zIndex: 1,
          background: 'transparent',
          border: '0.5px solid var(--color-border-tertiary)',
          color: 'var(--color-text-secondary)',
          width: 22,
          height: 22,
          borderRadius: '50%',
          cursor: 'pointer',
          fontSize: 14,
          lineHeight: 1,
          padding: 0,
        }}
      >
        ×
      </button>
      <div
        style={{
          fontSize: 11,
          color: 'var(--color-text-tertiary)',
          marginBottom: 4,
          fontStyle: 'italic',
        }}
      >
        Q: {insight.question}
      </div>
      <AIInsightCard response={insight.response} />
    </div>
  )
}

export default Section10MyInsights
