import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, ChevronRight, Loader2, Check, ArrowDown, Sparkles, Brain, Trash2, Eye, EyeOff, Maximize2, Minimize2, Pencil, RotateCcw, X } from 'lucide-react'
import { useStudySite } from '@/contexts/StudySiteContext'
import { useAuth } from '@/contexts/AuthContext'
import {
  decideAssistantAction,
  openAssistantStream,
  sendAssistantMessage,
  fetchWelcomeBack,
  listMemories,
  editMemory,
  excludeMemory,
  deleteMemory,
  type AssistantEvent,
  type WelcomeBack,
  type MemoryItem,
} from '../services/assistantClient'
import { BlockRenderer, actionIcon } from '../blocks/Blocks'
import type { Block, BlockHandlers } from '../blocks/types'
import { catalogForBackend, getScreen } from '../blocks/screenCatalog'
import { toursForBackend } from '../demo/tours'
import { runTour } from '../demo/runTour'
import { entitiesForBackend, getEntity } from '../demo/entities'
import { FORMS, getForm, formsForBackend } from '../demo/forms'

type TraceStep = { command: string; label: string; status: 'running' | 'ok' | 'warn' }
type UserTurn = { role: 'user'; text: string; at: number }
type AssistantTurn = { role: 'assistant'; blocks: Block[]; trace: TraceStep[]; pending: boolean; at: number }
type Turn = UserTurn | AssistantTurn

const PANEL_W = 400 // px — default panel width (user-resizable between MIN/MAX)
const PANEL_MIN_W = 340
const PANEL_MAX_W = 760

type Starter = { label: string; message: string; prefill?: boolean }

const OPEN_STARTER: Starter = { label: 'Open…', message: 'Open ', prefill: true }

// Context-aware starter chips, keyed off the current screen; generic fallback.
function startersFor(mode?: string): Starter[] {
  switch (mode) {
    case 'conversations':
      return [
        { label: 'Summarize this inbox', message: 'Summarize my conversations' },
        { label: 'Start a conversation', message: 'Create a conversation' },
        OPEN_STARTER,
      ]
    case 'threads':
      return [
        { label: 'Summarize my threads', message: 'Summarize my conversations' },
        { label: 'Start a conversation', message: 'Create a conversation' },
        OPEN_STARTER,
      ]
    case 'tasks':
      return [
        { label: 'What needs attention?', message: 'Summarize my tasks' },
        { label: 'Create a task', message: 'Create a task' },
        OPEN_STARTER,
      ]
    case 'dashboard':
    case 'study-setup':
    case 'site-profile':
    case 'site-status':
    case 'site-staff-details':
    case 'monitoring':
    case 'documents':
      return [
        { label: 'What needs attention?', message: 'Summarize my tasks' },
        { label: 'Create a task', message: 'Create a task' },
        OPEN_STARTER,
      ]
    default:
      return [
        { label: 'Summarize my studies', message: 'Summarize my studies' },
        { label: 'Create a task', message: 'Create a task' },
        OPEN_STARTER,
      ]
  }
}

// React controlled inputs ignore a raw `el.value = x`; set via the native value
// setter then dispatch input/change so React's onChange fires and state updates.
function setNativeValue(el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, value: string) {
  const proto =
    el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
  setter?.call(el, value)
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
}

// Is this element actually visible on screen right now (in the viewport, rendered)?
function isOnScreen(el: Element | null): boolean {
  if (!el) return false
  const he = el as HTMLElement
  const style = window.getComputedStyle(he)
  if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false
  const r = he.getBoundingClientRect()
  const vh = window.innerHeight || document.documentElement.clientHeight
  const vw = window.innerWidth || document.documentElement.clientWidth
  if (r.width < 1 || r.height < 1) return false
  return r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw
}

/** FILL-ONLY (sacred rule 2) + on-screen-only (sacred rule 1): populate a
 *  registered form's fields that are CURRENTLY VISIBLE, by data-testid. Never
 *  clicks submit/save/sign. Off-screen fields are skipped and reported so the
 *  console can ask the user to scroll/reveal them. */
function fillForm(
  formId: string,
  fields: { key: string; value: string }[],
): { filled: string[]; offscreen: string[]; formLabel: string; submitLabel: string; formPresent: boolean } {
  const form = getForm(formId)
  if (!form) return { filled: [], offscreen: [], formLabel: formId || 'form', submitLabel: 'Submit', formPresent: false }
  const present = !!document.querySelector(`[data-testid="${form.formTestid}"]`)
  if (!present) return { filled: [], offscreen: [], formLabel: form.label, submitLabel: form.submitLabel, formPresent: false }
  const filled: string[] = []
  const offscreen: string[] = []
  for (const { key, value } of fields) {
    const def = form.fields.find((f) => f.key === key) // whitelist: known fields only
    if (!def) continue
    const el = document.querySelector(`[data-testid="${def.testid}"]`) as
      | HTMLInputElement
      | HTMLTextAreaElement
      | HTMLSelectElement
      | null
    if (!el || !isOnScreen(el)) {
      offscreen.push(def.label) // present-but-off-screen OR on a later step
      continue
    }
    setNativeValue(el, value ?? '')
    filled.push(def.label)
  }
  return { filled, offscreen, formLabel: form.label, submitLabel: form.submitLabel, formPresent: true }
}

/** Per-turn snapshot of which registered form(s) are on screen and which of their
 *  fields are visible now vs off-screen — so Orbit fills what's visible and asks
 *  the user to reveal the rest (over-the-shoulder loop). Sent as `form_view`. */
function captureFormView(): { id: string; label: string; visible_fields: string[]; hidden_fields: string[] }[] {
  const out: { id: string; label: string; visible_fields: string[]; hidden_fields: string[] }[] = []
  for (const form of FORMS) {
    if (!document.querySelector(`[data-testid="${form.formTestid}"]`)) continue // form not on screen
    const visible: string[] = []
    const hidden: string[] = []
    for (const f of form.fields) {
      const el = document.querySelector(`[data-testid="${f.testid}"]`)
      if (el && isOnScreen(el)) visible.push(f.key)
      else hidden.push(f.key) // off-screen (scroll) or absent (later step)
    }
    out.push({ id: form.id, label: form.label, visible_fields: visible, hidden_fields: hidden })
  }
  return out
}

// Live on-screen read (sacred rule 1): capture ONLY the rendered content that is
// currently VISIBLE in the viewport — never hidden DOM, never data fetched-but-not-
// shown. Orbit sees exactly what the user sees; if it's off-screen, Orbit must ask
// the user to scroll/reveal. Excludes the Orbit console itself.
function captureVisibleText(): { text: string; more_below: boolean; more_above: boolean } {
  try {
    const vh = window.innerHeight || document.documentElement.clientHeight
    const vw = window.innerWidth || document.documentElement.clientWidth
    const panel = document.querySelector('[aria-label="Orbit assistant console"]')
    const launcher = document.querySelector('[aria-label="Open Orbit assistant"]')
    const parts: string[] = []
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT)
    let node = walker.nextNode() as HTMLElement | null
    while (node) {
      const el = node
      node = walker.nextNode() as HTMLElement | null
      if (panel?.contains(el) || launcher?.contains(el)) continue
      const style = window.getComputedStyle(el)
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) continue
      const rect = el.getBoundingClientRect()
      // Must intersect the viewport (currently on screen), with real size.
      if (rect.width < 1 || rect.height < 1) continue
      if (rect.bottom <= 0 || rect.top >= vh || rect.right <= 0 || rect.left >= vw) continue
      // Only this element's DIRECT text (avoids duplicating parent + child text).
      const direct = Array.from(el.childNodes)
        .filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => (n.textContent || '').replace(/\s+/g, ' ').trim())
        .filter(Boolean)
        .join(' ')
      if (direct) parts.push(direct)
    }
    const text = parts.join('\n').replace(/\n{3,}/g, '\n\n').slice(0, 6000)
    const doc = document.scrollingElement || document.documentElement
    const more_below = doc.scrollHeight - (doc.scrollTop + vh) > 40
    const more_above = doc.scrollTop > 40
    return { text, more_below, more_above }
  } catch {
    return { text: '', more_below: false, more_above: false }
  }
}

// Read-after-render: wait for the app's DOM to go quiet before capturing, so a
// data-heavy screen (dashboard) that is still fetching/rendering isn't snapshotted
// half-empty. Mutations inside the Orbit console itself are ignored (appending the
// user's message re-renders the panel and must not reset the quiet timer).
function waitForDomQuiet(quietMs = 250, maxMs = 1500): Promise<void> {
  return new Promise((resolve) => {
    const panel = document.querySelector('[aria-label="Orbit assistant console"]')
    const launcher = document.querySelector('[aria-label="Open Orbit assistant"]')
    let quietTimer: ReturnType<typeof setTimeout>
    let obs: MutationObserver | null = null
    const done = () => {
      obs?.disconnect()
      clearTimeout(quietTimer)
      clearTimeout(maxTimer)
      resolve()
    }
    const maxTimer = setTimeout(done, maxMs) // never stall a message past this
    try {
      obs = new MutationObserver((mutations) => {
        const outside = mutations.some((m) => {
          const t = m.target as Node
          return !(panel?.contains(t) || launcher?.contains(t))
        })
        if (outside) {
          clearTimeout(quietTimer)
          quietTimer = setTimeout(done, quietMs)
        }
      })
      obs.observe(document.body, { childList: true, subtree: true, characterData: true })
      quietTimer = setTimeout(done, quietMs)
    } catch {
      done()
    }
  })
}

/** Settled on-screen capture: wait for render quiet, capture; if the screen is
 *  still empty (late fetch), retry ONCE after a short delay. Still visible-only —
 *  this changes WHEN we look, never WHAT we're allowed to see. */
async function captureVisibleTextSettled(): Promise<{ text: string; more_below: boolean; more_above: boolean }> {
  await waitForDomQuiet()
  let snap = captureVisibleText()
  if (!snap.text.trim()) {
    await new Promise((r) => setTimeout(r, 600))
    snap = captureVisibleText()
  }
  return snap
}

function buildScreen(selectedStudyId: string | null, selectedSiteId: string | null): string {
  try {
    const path = window.location.pathname + window.location.hash
    const title = document.title
    const base = title ? `${title} — ${path}` : path
    const study = selectedStudyId ? `study selected: ${selectedStudyId}` : 'no study selected'
    const site = selectedSiteId ? `site selected: ${selectedSiteId}` : 'no site selected'
    return `${base} (${study}; ${site})`
  } catch {
    return ''
  }
}

/** One-line summary of an assistant turn for the collapsed history rail. */
function summarizeAssistant(t: AssistantTurn): string {
  const b = t.blocks
  const rl = b.find((x) => x.type === 'record_list') as any
  if (rl) return `${rl.records.length} ${rl.record_type}${rl.records.length === 1 ? '' : 's'}`
  const sr = b.find((x) => x.type === 'stat_row') as any
  if (sr) return sr.stats.map((s: any) => `${s.value} ${s.label}`).join(' · ')
  const rc = b.find((x) => x.type === 'record_card') as any
  if (rc) return rc.title
  const ch = b.find((x) => x.type === 'chart') as any
  if (ch) return ch.title || 'Chart'
  const notice = b.find((x) => x.type === 'notice') as any
  if (notice) return String(notice.message).slice(0, 50)
  const help = b.find((x) => x.type === 'help_answer')
  if (help) return 'Help answer'
  const conf = b.find((x) => x.type === 'confirmation')
  if (conf) return 'Confirmation'
  const text = b.find((x) => x.type === 'text') as any
  if (text) return String(text.text || '').replace(/\s+/g, ' ').slice(0, 60)
  return t.pending ? 'Working…' : 'Response'
}

type Props = { onNavigate?: (mode: string) => void; currentMode?: string }

const AssistantWidget: React.FC<Props> = ({ onNavigate, currentMode }) => {
  const navigate = useNavigate()
  const { setLastTab, setLastSubTab, setSelectedStudyId, setSelectedSiteId, selectedStudyId, selectedSiteId, studies, sites } =
    useStudySite()
  const { user } = useAuth()

  const [open, setOpen] = useState(false)
  // Mirror of `open` for the (stable) SSE event handler: side-effectful events
  // that take over the screen must know whether the console is even visible.
  const openRef = useRef(false)
  useEffect(() => { openRef.current = open }, [open])
  const [connected, setConnected] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [resolved, setResolved] = useState<Set<string>>(new Set())
  // Which way each confirmation went (true=approved) — drives the stamped slip.
  const [decisions, setDecisions] = useState<Map<string, boolean>>(new Map())
  const [expandedHistory, setExpandedHistory] = useState<Set<number>>(new Set())
  // Orbit derived memory: welcome-back payload (fetched once at open) + controls panel.
  const [welcome, setWelcome] = useState<WelcomeBack | null>(null)
  const [showMemory, setShowMemory] = useState(false)
  // Living glass: has the conversation scrolled? (header hairline/shadow deepen)
  const [scrolled, setScrolled] = useState(false)
  // Ergonomics: user-resizable width (persisted), focus mode, live drag flag.
  const [panelW, setPanelW] = useState<number>(() => {
    try {
      const saved = Number(localStorage.getItem('orbit-panel-w'))
      return Number.isFinite(saved) && saved >= PANEL_MIN_W && saved <= PANEL_MAX_W ? saved : PANEL_W
    } catch {
      return PANEL_W
    }
  })
  const [wide, setWide] = useState(false)
  const [resizing, setResizing] = useState(false)
  // Minimized completion: a turn that finishes while the console is closed
  // flips the launcher pill to "Ready" until the panel is opened — an answer
  // never lands silently behind a closed panel.
  const [unseenReady, setUnseenReady] = useState(false)
  // Watch mode (off by default): during an active read/fill loop, auto-send
  // "continue" when the user settles after revealing new content — no typed
  // "continue" needed. Auto-advance ONLY: it never adds commentary or actions.
  const [watch, setWatch] = useState(false)
  // Confirm-before-auto-off: "Looks like we're done — turn Watch off?"
  const [watchPrompt, setWatchPrompt] = useState(false)
  // Last screen snapshot actually SENT (so Watch only continues on NEW content).
  const lastSnapshotRef = useRef<string>('')
  const lastMoreBelowRef = useRef<boolean>(true)
  // Watch whisper: when Watch last auto-continued + how many registered form
  // fields were below the fold at the last send (from the same per-turn capture).
  const [lastContinueAt, setLastContinueAt] = useState<number | null>(null)
  const [hiddenBelow, setHiddenBelow] = useState(0)

  const sessionIdRef = useRef<string>(
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `sess-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  )
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // Context header labels.
  const studyName = studies.find((s) => s.id === selectedStudyId)?.name || (selectedStudyId ? 'Study' : null)
  const siteName =
    sites.find((s) => s.id === selectedSiteId || (s as any).site_id === selectedSiteId)?.name ||
    (selectedSiteId ? 'Site' : null)
  const userName = user?.name || user?.email || 'You'

  const navRef = useRef<(screen: string, studyId?: string | null, siteId?: string | null) => void>(() => {})
  navRef.current = (screen, studyId, siteId) => {
    const entry = getScreen(screen)
    if (!entry) return
    if (studyId) setSelectedStudyId(studyId)
    if (siteId) setSelectedSiteId(siteId)
    const { target } = entry
    if (target.tab) setLastTab(`study-setup:${target.tab}`)
    // Deep-link a sub-view inside the tab (e.g. Clause Library) — the parent tab
    // component reads lastSubTab and activates it.
    if (target.tab && target.subtab) setLastSubTab(`${target.tab}:${target.subtab}`)
    if (target.mode) onNavigate?.(target.mode)
    else if (target.path) navigate(target.path)
  }

  // Open a specific record by type+id (kept in a ref so handleEvent stays stable).
  const entityRef = useRef<(type: string, id: string) => void>(() => {})
  entityRef.current = (type, id) => {
    const def = getEntity(type)
    if (!def || !id) return
    const o = def.open
    if (o.url) {
      navigate(o.url(id))
      return
    }
    if (o.select === 'study') {
      setSelectedStudyId(id)
      if (o.screen) navRef.current(o.screen)
      return
    }
    if (o.select === 'site') {
      setSelectedSiteId(id)
      if (o.screen) navRef.current(o.screen)
      return
    }
    if (o.event) {
      // Navigate first, then dispatch the record-select event. The destination
      // screen may mount lazily, so re-dispatch once after a beat — listeners
      // treat it idempotently (select the same record twice = same result).
      if (o.screen) navRef.current(o.screen)
      const fire = () => window.dispatchEvent(new CustomEvent(o.event as string, { detail: { id } }))
      fire()
      setTimeout(fire, 700)
      return
    }
    if (o.screen) navRef.current(o.screen)
  }

  const updateActive = useCallback((fn: (t: AssistantTurn) => AssistantTurn) => {
    setTurns((prev) => {
      const copy = [...prev]
      const last = copy[copy.length - 1]
      if (last && last.role === 'assistant') copy[copy.length - 1] = fn(last)
      return copy
    })
  }, [])

  // Watchdog food: when the last SSE event arrived (any type).
  const lastEventAtRef = useRef<number>(Date.now())

  const handleEvent = useCallback(
    (e: AssistantEvent) => {
      // `ready` is a CONNECTION event (sent on every reconnect), not turn
      // progress — if it fed the watchdog, a flapping SSE connection would
      // reset the 60s leash forever and a lost `done` would spin "Working"
      // indefinitely. Only real turn events count as watchdog food.
      if (e.type !== 'ready') lastEventAtRef.current = Date.now()
      switch (e.type) {
        case 'ready':
          setConnected(true)
          return
        case 'navigate':
          if (typeof e.screen === 'string') {
            navRef.current(e.screen, (e.study_id as string) ?? null, (e.site_id as string) ?? null)
          }
          return
        case 'demo':
          if (e.mode === 'tour' && typeof e.recipe === 'string') {
            const recipe = e.recipe
            if (openRef.current && !document.hidden) {
              void runTour(recipe, (screen) => navRef.current(screen))
            } else {
              // The console is minimized (or the tab is hidden) — a tour taking
              // over the screen unprompted is hijacking, not helping. Park it as
              // an explicit opt-in chip in the answer; tapping it re-requests the
              // tour with the panel open, and THEN it runs.
              updateActive((t) => ({
                ...t,
                blocks: [
                  ...t.blocks,
                  {
                    type: 'choice_chips',
                    question: 'I have a guided tour ready — run it now?',
                    options: [{ label: '▶ Start the tour', message: `show me the ${recipe} tour` }],
                  } as Block,
                ],
              }))
            }
          }
          return
        case 'open_entity':
          if (typeof e.entity_type === 'string' && typeof e.id === 'string') {
            entityRef.current(e.entity_type, e.id)
          }
          return
        case 'fill_form': {
          // Sacred rules 1+2: fill only fields VISIBLE on screen; never submit/save/sign.
          const res = fillForm(e.form as string, (e.fields as { key: string; value: string }[]) || [])
          let message: string
          let kind: 'info' | 'warning' = 'info'
          if (!res.formPresent) {
            kind = 'warning'
            message = `I don't see the ${res.formLabel} on screen. Open it first, then ask me to fill it.`
          } else if (res.filled.length === 0) {
            kind = 'warning'
            message = res.offscreen.length
              ? `The ${res.offscreen.join(', ')} field(s) aren't visible yet — scroll to them (or go to that step) and say “continue,” and I'll fill them.`
              : `There was nothing visible to fill on the ${res.formLabel}.`
          } else {
            message = `Filled ${res.filled.join(', ')} on the ${res.formLabel}.`
            if (res.offscreen.length) {
              message += ` I couldn't reach ${res.offscreen.join(', ')} (not on screen) — scroll to reveal them and say “continue.”`
            }
            message += ` Review it and click “${res.submitLabel}” yourself to save — I won't submit it for you.`
          }
          updateActive((t) => ({ ...t, blocks: [...t.blocks, { type: 'notice', kind, message } as Block] }))
          return
        }
        case 'block':
          if (e.block) updateActive((t) => ({ ...t, blocks: [...t.blocks, e.block as Block] }))
          return
        case 'step':
          updateActive((t) => ({
            ...t,
            trace: [...t.trace, { command: (e.command as string) || '', label: (e.label as string) || 'Working…', status: 'running' }],
          }))
          return
        case 'step_result': {
          const st = e.status
          const ok = st === 'ok' || (typeof st === 'number' && st >= 200 && st < 300)
          updateActive((t) => {
            const trace = [...t.trace]
            for (let i = trace.length - 1; i >= 0; i--) {
              if (trace[i].command === e.command && trace[i].status === 'running') {
                trace[i] = { ...trace[i], status: ok ? 'ok' : 'warn' }
                break
              }
            }
            return { ...t, trace }
          })
          return
        }
        case 'token':
          updateActive((t) => {
            const blocks = [...t.blocks]
            const lb = blocks[blocks.length - 1] as any
            if (lb && lb.type === 'text') blocks[blocks.length - 1] = { type: 'text', text: (lb.text || '') + (e.text || '') }
            else blocks.push({ type: 'text', text: (e.text as string) || '' })
            return { ...t, blocks }
          })
          return
        case 'done':
          setStreaming(false)
          updateActive((t) => ({ ...t, pending: false }))
          return
        case 'error':
          setStreaming(false)
          updateActive((t) => ({
            ...t,
            pending: false,
            blocks: [...t.blocks, { type: 'notice', kind: 'error', message: (e.message as string) || 'Something went wrong.' }],
          }))
          return
        default:
          return
      }
    },
    [updateActive],
  )

  // SSE with AUTO-RECONNECT. In production a proxy/LB can buffer or drop the
  // stream mid-turn (local never sees this); the server-side session queue
  // survives a disconnect, so reconnecting drains any missed events (including
  // the `done` that unsticks the turn). Backoff 1s→16s, reset after a healthy
  // (>10s) connection.
  // Stays connected while EITHER the panel is open OR a turn is in flight —
  // closing the console mid-turn must not orphan the `done` event, or the
  // minimized launcher pill would say "Working…" forever instead of "Ready".
  const shouldStream = open || streaming
  useEffect(() => {
    if (!shouldStream) return
    const controller = new AbortController()
    setConnected(false)
    const run = async () => {
      let attempt = 0
      while (!controller.signal.aborted) {
        const startedAt = Date.now()
        try {
          await openAssistantStream(sessionIdRef.current, handleEvent, controller.signal)
          // Stream closed without an exception (server/proxy ended it) — fall
          // through to reconnect; the session queue holds anything we missed.
        } catch (err) {
          if (controller.signal.aborted) return
          // eslint-disable-next-line no-console
          console.error('assistant stream error:', err)
        }
        if (controller.signal.aborted) return
        setConnected(false)
        if (Date.now() - startedAt > 10_000) attempt = 0 // long-lived → healthy; restart backoff
        attempt += 1
        await new Promise((r) => setTimeout(r, Math.min(16_000, 1_000 * 2 ** Math.min(attempt - 1, 4))))
      }
    }
    void run()
    return () => controller.abort()
  }, [shouldStream, handleEvent])

  // Honest status: while a confirmation card is pending, Orbit is waiting on the
  // USER, not working — say so instead of a misleading spinner. (Also feeds the
  // launcher badge and the stuck-turn watchdog below.)
  const lastTurn = turns[turns.length - 1]
  const awaitingApproval =
    streaming &&
    lastTurn?.role === 'assistant' &&
    (lastTurn as AssistantTurn).blocks.some((b: any) => b.type === 'confirmation' && !resolved.has(b.token))

  // Stuck-turn watchdog: if a turn is in flight and no SSE event has arrived
  // for 60s (legit model rounds stream something well within that), assume the
  // tail of the stream was lost (proxy buffer / dropped connection) and unstick
  // the panel with an honest notice instead of spinning "Working" forever.
  // Mirrors the server's never-silent rule on the client side.
  // While an approval card is pending we are legitimately idle — but not
  // forever: the server resolves the wait at 300s, so a 330s leash (timeout +
  // slack) still rescues the panel if those terminal events got lost or the
  // backend restarted mid-wait.
  useEffect(() => {
    if (!streaming) return
    lastEventAtRef.current = Date.now()
    const leash = awaitingApproval ? 330_000 : 60_000
    const t = setInterval(() => {
      if (Date.now() - lastEventAtRef.current > leash) {
        setStreaming(false)
        updateActive((turn) => ({
          ...turn,
          pending: false,
          blocks: [
            ...turn.blocks,
            {
              type: 'notice',
              kind: 'warning',
              message:
                "I lost the connection tail on that reply — what you see may be incomplete. If something looks unfinished, just ask again.",
            } as Block,
          ],
        }))
      }
    }, 5_000)
    return () => clearInterval(t)
  }, [streaming, awaitingApproval, updateActive])

  const scrollToLatest = useCallback(() => {
    const reduce = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    endRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' })
  }, [])
  useEffect(() => {
    scrollToLatest()
  }, [turns, scrollToLatest])

  useEffect(() => {
    if (!open) return
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  // Fetch the welcome-back payload once per open. A fresh user gets returning=false
  // (no fake greeting); the "what needs attention" number is deliberately NOT here —
  // that stays a live/guarded fetch elsewhere, never remembered.
  useEffect(() => {
    if (!open || welcome) return
    let cancelled = false
    fetchWelcomeBack().then((w) => {
      if (!cancelled) setWelcome(w)
    })
    return () => {
      cancelled = true
    }
  }, [open, welcome])

  // Effective width: focus mode stretches toward MAX (bounded by the viewport);
  // otherwise the user's dragged width applies.
  const effW = wide
    ? Math.min(PANEL_MAX_W, (typeof window !== 'undefined' ? window.innerWidth : 1280) - 48)
    : panelW

  // Persist the dragged width across sessions.
  useEffect(() => {
    try {
      localStorage.setItem('orbit-panel-w', String(panelW))
    } catch {
      /* storage unavailable — width just won't persist */
    }
  }, [panelW])

  // Streaming → done while closed sets the unseen-ready flag; opening clears it.
  const wasStreamingRef = useRef(false)
  useEffect(() => {
    if (wasStreamingRef.current && !streaming && !open) setUnseenReady(true)
    wasStreamingRef.current = streaming
  }, [streaming, open])
  useEffect(() => {
    if (open) setUnseenReady(false)
  }, [open])

  // Global shortcut: Ctrl/Cmd+J toggles the console from anywhere (Cmd+K is
  // the app's CommandPalette, so Orbit takes the "toggle panel" convention).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'j') {
        e.preventDefault()
        setOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Dock (don't overlay): while open on a wide screen, reserve space so the app
  // content sits BESIDE the panel and stays fully clickable. On narrow screens
  // fall back to an overlay (the user closes it to navigate). Cleaned up on close.
  useEffect(() => {
    if (!open) return
    // App content glides when toggling focus mode, but tracks the pointer
    // 1:1 while dragging (a transition there would feel like rubber-banding).
    document.body.style.transition = resizing ? '' : 'padding-right .3s ease'
    const apply = () => {
      // Reserve panel width + the docked card's right/left gaps so app content
      // sits beside it and stays clickable.
      document.body.style.paddingRight = window.innerWidth >= 1024 ? `${effW + 24}px` : ''
    }
    apply()
    window.addEventListener('resize', apply)
    return () => {
      window.removeEventListener('resize', apply)
      document.body.style.paddingRight = ''
      document.body.style.transition = ''
    }
  }, [open, effW, resizing])

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim()
      if (!text || streaming) return
      const now = Date.now()
      setTurns((prev) => [...prev, { role: 'user', text, at: now }, { role: 'assistant', blocks: [], trace: [], pending: true, at: now }])
      setStreaming(true)
      try {
        // Read-after-render: settle (+ one empty retry) BEFORE snapshotting, so a
        // still-loading screen isn't captured half-empty. Form visibility is
        // captured at the same settled moment for consistency.
        const screenView = await captureVisibleTextSettled()
        // Remember what was sent so Watch mode only auto-continues on NEW content.
        lastSnapshotRef.current = screenView.text
        lastMoreBelowRef.current = screenView.more_below
        const formView = captureFormView()
        setHiddenBelow(formView.reduce((a, f) => a + f.hidden_fields.length, 0))
        await sendAssistantMessage(
          sessionIdRef.current,
          text,
          buildScreen(selectedStudyId, selectedSiteId),
          catalogForBackend(),
          { study_id: selectedStudyId, site_id: selectedSiteId },
          toursForBackend(),
          entitiesForBackend(),
          currentMode, // clean current-screen key for structured screen-read
          formsForBackend(), // fillable-forms whitelist for fill_form
          screenView, // live on-screen read: only what's visible now (settled)
          formView, // which form fields are visible now (fill-loop)
        )
      } catch {
        setStreaming(false)
        updateActive((t) => ({ ...t, pending: false, blocks: [...t.blocks, { type: 'notice', kind: 'error', message: 'Could not reach the assistant.' }] }))
      }
    },
    [streaming, selectedStudyId, selectedSiteId, updateActive],
  )

  const decide = useCallback(
    async (token: string, approve: boolean) => {
      setResolved((prev) => new Set(prev).add(token))
      setDecisions((prev) => new Map(prev).set(token, approve))
      try {
        await decideAssistantAction(sessionIdRef.current, token, approve)
      } catch {
        updateActive((t) => ({ ...t, pending: false, blocks: [...t.blocks, { type: 'notice', kind: 'error', message: 'Could not submit your decision.' }] }))
      }
    },
    [updateActive],
  )

  // ---- Watch mode: settle-triggered auto-continue (auto-advance ONLY) ----
  // "Active loop" = the last finished assistant turn read the screen or filled a
  // form — exactly the loops where Orbit asks the user to scroll and say
  // "continue". Watch never fires outside one, so it can't add commentary or
  // start new actions; it only replaces the typed "continue".
  const inActiveLoop = () => {
    const last = [...turns].reverse().find((t) => t.role === 'assistant') as AssistantTurn | undefined
    if (!last || last.pending) return false
    return last.trace.some((s) => s.command === 'read_screen' || s.command === 'fill_form')
  }

  // Ref-held (navRef pattern) so the scroll listener always sees fresh state.
  const autoContinueRef = useRef<() => void>(() => {})
  autoContinueRef.current = () => {
    if (!watch || streaming || watchPrompt || !open) return
    if (!inActiveLoop()) return
    // Only continue when NEW content is actually visible (sacred rule 1 intact:
    // this peeks at the same visible-only capture the read itself uses).
    const snap = captureVisibleText()
    if (!snap.text.trim()) return
    if (snap.text === lastSnapshotRef.current) return // nothing new revealed yet
    setLastContinueAt(Date.now())
    void send('continue')
  }

  // Trigger on the user SETTLING (stopped scrolling, debounced) — never on every
  // scroll tick. Scrolls inside the Orbit console itself are ignored. `capture`
  // is required because scroll events don't bubble from inner containers.
  useEffect(() => {
    if (!watch || !open) return
    let timer: ReturnType<typeof setTimeout> | undefined
    const onScroll = (e: Event) => {
      if (panelRef.current?.contains(e.target as Node)) return
      clearTimeout(timer)
      timer = setTimeout(() => autoContinueRef.current(), 800)
    }
    window.addEventListener('scroll', onScroll, { capture: true, passive: true })
    return () => {
      clearTimeout(timer)
      window.removeEventListener('scroll', onScroll, { capture: true })
    }
  }, [watch, open])

  // Confirm-before-auto-off: when a watched loop's turn finishes and the last
  // sent snapshot had nothing left below the fold, ASK — never silently switch
  // Watch off (and never keep it on without the user's say-so).
  const prevStreamingRef = useRef(false)
  useEffect(() => {
    if (prevStreamingRef.current && !streaming && watch && inActiveLoop() && lastMoreBelowRef.current === false) {
      setWatchPrompt(true)
    }
    prevStreamingRef.current = streaming
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming, watch, turns])

  const openRecord = useCallback(
    (recordType: string, id?: string) => {
      if (!id) return
      if (recordType === 'conversation') {
        onNavigate?.('conversations')
        window.dispatchEvent(new CustomEvent('crm:select-conversation', { detail: { id } }))
      } else if (recordType === 'study') {
        setSelectedStudyId(id)
        onNavigate?.('dashboard')
      } else if (recordType === 'task') {
        onNavigate?.('tasks')
        // Open the specific task's detail; re-fire once for a lazily-mounted tab.
        const fire = () => window.dispatchEvent(new CustomEvent('crm:select-task', { detail: { id } }))
        fire()
        setTimeout(fire, 700)
      } else if (recordType === 'agreement') {
        setLastTab('study-setup:agreements')
        onNavigate?.('study-setup')
      }
    },
    [onNavigate, setSelectedStudyId, setLastTab],
  )

  const handlers: BlockHandlers = {
    onSend: (m) => void send(m),
    onOpenRecord: openRecord,
    onDecide: (t, a) => void decide(t, a),
    resolvedTokens: resolved,
    decisions,
    busy: streaming,
  }

  // Short clock time for the history rail (e.g. "14:32").
  const timeOf = (at?: number) =>
    at ? new Date(at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''

  // "conversations" → "Conversations" for the context chip.
  const screenLabel = (currentMode || '')
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())

  const submitInput = () => {
    const text = input
    setInput('')
    void send(text)
  }

  const handleStarter = (s: Starter) => {
    if (s.prefill) {
      setInput(s.message)
      inputRef.current?.focus()
    } else {
      void send(s.message)
    }
  }

  const starters = startersFor(currentMode)

  // ONE continuous stream: everything scrolls together. Turns before the live
  // user+assistant pair render inline-collapsed (a one-line summary in place) so
  // the past stays scannable without splitting the panel into two zones.
  const activeStart = Math.max(0, turns.length - (turns[turns.length - 1]?.role === 'assistant' ? 2 : 1))

  // Liquid glass: starters are frosted glass pills (matches the panel material).
  const chipClass =
    'rounded-full bg-white/55 px-2.5 py-1 text-ui-body-sm font-medium text-brand-700 ring-1 ring-white/60 ' +
    'shadow-sm backdrop-blur-sm transition hover:bg-white/80 hover:shadow active:scale-95 ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 disabled:opacity-40'

  // ── Draggable launcher ────────────────────────────────────────────────
  // The closed-panel launcher can be dragged anywhere on screen (mouse or
  // touch); the spot persists across sessions. While dragging, position is
  // written straight onto the element's style — React re-renders only once,
  // on release, so a drag costs nothing beyond the compositor.
  const LAUNCHER_MARGIN = 8
  const [launcherPos, setLauncherPos] = useState<{ x: number; y: number } | null>(() => {
    try {
      const p = JSON.parse(localStorage.getItem('orbit-launcher-pos') || 'null')
      return Number.isFinite(p?.x) && Number.isFinite(p?.y) ? { x: p.x, y: p.y } : null
    } catch {
      return null
    }
  })
  const launcherRef = useRef<HTMLButtonElement | null>(null)
  const launcherDragRef = useRef<{
    id: number; startX: number; startY: number; origX: number; origY: number
    moved: boolean; lastX: number; lastY: number; raf: number
  } | null>(null)
  const suppressLauncherClickRef = useRef(false)

  const clampLauncher = useCallback((x: number, y: number, w: number, h: number) => ({
    x: Math.min(Math.max(x, LAUNCHER_MARGIN), Math.max(LAUNCHER_MARGIN, window.innerWidth - w - LAUNCHER_MARGIN)),
    y: Math.min(Math.max(y, LAUNCHER_MARGIN), Math.max(LAUNCHER_MARGIN, window.innerHeight - h - LAUNCHER_MARGIN)),
  }), [])

  const commitLauncherPos = useCallback((pos: { x: number; y: number }) => {
    setLauncherPos(pos)
    try { localStorage.setItem('orbit-launcher-pos', JSON.stringify(pos)) } catch { /* storage unavailable */ }
  }, [])

  // Keep a saved spot on-screen when the window shrinks or the launcher grows
  // into its status pill (streaming/approval) near an edge.
  useEffect(() => {
    if (!launcherPos) return
    const reclamp = () => {
      const el = launcherRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const c = clampLauncher(launcherPos.x, launcherPos.y, r.width, r.height)
      if (c.x !== launcherPos.x || c.y !== launcherPos.y) commitLauncherPos(c)
    }
    reclamp()
    window.addEventListener('resize', reclamp)
    return () => window.removeEventListener('resize', reclamp)
  }, [launcherPos, streaming, awaitingApproval, unseenReady, clampLauncher, commitLauncherPos])

  const onLauncherPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return
    const r = e.currentTarget.getBoundingClientRect()
    launcherDragRef.current = {
      id: e.pointerId, startX: e.clientX, startY: e.clientY, origX: r.left, origY: r.top,
      moved: false, lastX: r.left, lastY: r.top, raf: 0,
    }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onLauncherPointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const d = launcherDragRef.current
    if (!d || e.pointerId !== d.id) return
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    if (!d.moved) {
      if (Math.hypot(dx, dy) < 5) return // still a click, not a drag
      d.moved = true
      // "Picked up": the button's transition-all would ease every left/top
      // write and rubber-band behind the cursor — kill it for the drag, and
      // lift the button slightly (inline transform also beats active:scale-95).
      const el = e.currentTarget
      el.style.transition = 'none'
      el.style.cursor = 'grabbing'
      el.style.transform = 'scale(1.06)'
    }
    d.lastX = d.origX + dx
    d.lastY = d.origY + dy
    // Coalesce moves to one style write per frame — pointer events can fire far
    // faster than the display refreshes.
    if (!d.raf) {
      d.raf = requestAnimationFrame(() => {
        d.raf = 0
        const el = launcherRef.current
        if (!el || launcherDragRef.current !== d) return
        const { x, y } = clampLauncher(d.lastX, d.lastY, el.offsetWidth, el.offsetHeight)
        el.style.left = `${x}px`
        el.style.top = `${y}px`
        el.style.right = 'auto'
        el.style.bottom = 'auto'
      })
    }
  }
  const onLauncherPointerUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    const d = launcherDragRef.current
    if (!d || e.pointerId !== d.id) return
    launcherDragRef.current = null
    if (d.raf) cancelAnimationFrame(d.raf)
    try { e.currentTarget.releasePointerCapture(d.id) } catch { /* already released */ }
    const el = e.currentTarget
    // Restore the class-driven transition/cursor/hover transforms BEFORE
    // measuring, so the committed rect isn't skewed by the pick-up scale.
    el.style.transition = ''
    el.style.cursor = ''
    el.style.transform = ''
    if (!d.moved) return
    suppressLauncherClickRef.current = true // a drag must not open the panel
    const { x, y } = clampLauncher(d.lastX, d.lastY, el.offsetWidth, el.offsetHeight)
    commitLauncherPos({ x, y })
  }

  // ── Orbit's mood (drives the buddy character's expression) ───────────
  // waiting → an approval is blocked on the user; thinking → a turn is running;
  // excited/sad → the finished (still unseen) answer succeeded or errored;
  // otherwise idle. Once the answer is seen the buddy settles back to idle.
  const lastAssistantTurn = [...turns].reverse().find((t) => t.role === 'assistant') as AssistantTurn | undefined
  const lastTurnErrored =
    !!lastAssistantTurn && !lastAssistantTurn.pending &&
    lastAssistantTurn.blocks.some((b) => b.type === 'notice' && (b as { kind?: string }).kind === 'error')
  const buddyMood: BuddyMood = awaitingApproval
    ? 'waiting'
    : streaming
      ? 'thinking'
      : unseenReady
        ? (lastTurnErrored ? 'sad' : 'excited')
        : 'idle'

  // ── Gaze tracking: the buddy's pupils follow the cursor ──────────────
  // Active only while the launcher is visible AND the mood is idle (the other
  // moods own the eyes — thinking scans, sad looks down…). Zero-load design:
  // one passive pointermove listener, at most ONE style write per animation
  // frame, pupils + bounding rect cached (no per-event DOM queries or layout
  // reads), no React state. After ~4s without mouse movement the inline
  // override is cleared so the CSS wander/eye-roll personality resumes.
  // Skipped entirely under prefers-reduced-motion; mood changes re-run the
  // effect, whose cleanup clears any inline gaze so mood CSS wins again.
  useEffect(() => {
    if (open || buddyMood !== 'idle') return
    if (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    let pupils: SVGElement[] = []
    let rect: DOMRect | null = null
    let rectAt = 0
    let lastX = 0
    let lastY = 0
    let raf = 0
    let settleTimer = 0

    const getPupils = (): SVGElement[] => {
      if (!pupils.length || !pupils[0].isConnected) {
        pupils = launcherRef.current
          ? (Array.from(launcherRef.current.querySelectorAll('.orbit-b-pupil')) as SVGElement[])
          : []
      }
      return pupils
    }
    const clearGaze = () => {
      for (const p of getPupils()) {
        p.style.animation = ''
        p.style.transition = ''
        p.style.transform = ''
      }
    }
    const apply = () => {
      raf = 0
      const el = launcherRef.current
      if (!el) return
      const now = Date.now()
      if (!rect || now - rectAt > 1000) {
        rect = el.getBoundingClientRect()
        rectAt = now
      }
      const dx = lastX - (rect.left + rect.width / 2)
      const dy = lastY - (rect.top + rect.height / 2)
      const dist = Math.hypot(dx, dy) || 1
      // Pupils have ~2.2px of travel; use it fully once the cursor is a bit away.
      const reach = 2.2 * Math.min(1, dist / 90)
      const tx = ((dx / dist) * reach).toFixed(2)
      const ty = ((dy / dist) * reach).toFixed(2)
      for (const p of getPupils()) {
        p.style.animation = 'none' // suspend the CSS wander while actively watching
        p.style.transition = 'transform .12s ease-out'
        p.style.transform = `translate(${tx}px, ${ty}px)`
      }
      window.clearTimeout(settleTimer)
      settleTimer = window.setTimeout(clearGaze, 4000)
    }
    const onMove = (e: PointerEvent) => {
      lastX = e.clientX
      lastY = e.clientY
      if (!raf) raf = requestAnimationFrame(apply)
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => {
      window.removeEventListener('pointermove', onMove)
      if (raf) cancelAnimationFrame(raf)
      window.clearTimeout(settleTimer)
      clearGaze()
    }
  }, [open, buddyMood])

  return (
    <>
      <OrbitStyles />
      {/* Launcher (hidden while the console is open — the header has a close button) */}
      {!open && (
        <button
          ref={launcherRef}
          type="button"
          onClick={() => {
            // A drag that ends on the button fires a click too — swallow it.
            if (suppressLauncherClickRef.current) { suppressLauncherClickRef.current = false; return }
            setOpen(true)
          }}
          onPointerDown={onLauncherPointerDown}
          onPointerMove={onLauncherPointerMove}
          onPointerUp={onLauncherPointerUp}
          onPointerCancel={onLauncherPointerUp}
          aria-label={
            awaitingApproval
              ? 'Open Orbit assistant — an action is waiting for your approval'
              : streaming
                ? 'Open Orbit assistant — working on your last request'
                : unseenReady
                  ? 'Open Orbit assistant — your answer is ready'
                  : 'Open Orbit assistant'
          }
          title={
            awaitingApproval
              ? 'Orbit — an action is waiting for your approval (Ctrl+J)'
              : streaming
                ? 'Orbit — working on it… (Ctrl+J)'
                : unseenReady
                  ? 'Orbit — your answer is ready (Ctrl+J)'
                  : 'Orbit (Ctrl+J) — drag to move'
          }
          className="fixed bottom-4 right-4 z-[300] flex flex-col items-center border-0 bg-transparent p-0 cursor-grab rounded-3xl transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/50"
          // touch-action:none lets touch drags reach our pointer handlers instead
          // of scrolling the page. A dragged position overrides bottom/right-4.
          style={
            launcherPos
              ? { left: launcherPos.x, top: launcherPos.y, right: 'auto', bottom: 'auto', touchAction: 'none' }
              : { touchAction: 'none' }
          }
        >
          {/* Live-status speech bubble — closing the panel never hides that Orbit
              is working, blocked on approval, or done. */}
          {(streaming || awaitingApproval || unseenReady) && (
            <span className="orbit-block-in mb-1.5 inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-white/95 px-2.5 py-1 text-ui-caption font-semibold text-brand-700 shadow-card ring-1 ring-black/5">
              {awaitingApproval ? (
                'Waiting for you'
              ) : streaming ? (
                'On it…'
              ) : (
                <>
                  <Check size={12} className="shrink-0" /> Ready!
                </>
              )}
            </span>
          )}
          <span className="relative">
            <OrbitBuddy mood={buddyMood} />
            {/* A pending approval must never wait invisibly behind a closed panel. */}
            {awaitingApproval && (
              <span className="absolute -right-1 top-0 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-warning-500 px-1 text-[10px] font-bold text-white ring-2 ring-white orbit-blink">
                1
              </span>
            )}
          </span>
        </button>
      )}

      {open && (
        <div
          ref={panelRef}
          className={`fixed top-3 right-3 bottom-3 z-[300] max-w-[calc(100vw-1.5rem)] orbit-glass orbit-panel-in rounded-[28px] flex flex-col font-primary overflow-hidden ${
            resizing ? '' : 'transition-[width] duration-300'
          }`}
          style={{ width: effW }}
          role="complementary"
          aria-label="Orbit assistant console"
          onMouseMove={(e) => {
            // Living glass: the specular sheen follows the pointer (CSS vars only —
            // no re-render). The sheen layer below reads --mx/--my.
            const r = e.currentTarget.getBoundingClientRect()
            e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`)
            e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`)
          }}
        >
          {/* Living-glass layers: slow-drifting brand aurora + mouse-following
              specular sheen. Pointer-transparent, painted behind the content
              (the header/body/footer are position:relative and thus above). */}
          <div className="orbit-aurora pointer-events-none absolute inset-0" aria-hidden="true" />
          <div className="orbit-sheen pointer-events-none absolute inset-0" aria-hidden="true" />

          {/* Drag-to-resize handle on the left edge (arrow keys work too). The
              panel is right-docked, so dragging LEFT grows it. */}
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize Orbit panel (drag, or use arrow keys)"
            tabIndex={0}
            className="group/rz absolute inset-y-0 left-0 z-20 w-2 cursor-ew-resize focus-visible:outline-none"
            onPointerDown={(e) => {
              e.preventDefault()
              setWide(false)
              setResizing(true)
              document.body.style.userSelect = 'none'
              const onMove = (ev: PointerEvent) => {
                const w = Math.round(window.innerWidth - ev.clientX - 12)
                setPanelW(Math.min(PANEL_MAX_W, Math.max(PANEL_MIN_W, w)))
              }
              const onUp = () => {
                setResizing(false)
                document.body.style.userSelect = ''
                window.removeEventListener('pointermove', onMove)
                window.removeEventListener('pointerup', onUp)
              }
              window.addEventListener('pointermove', onMove)
              window.addEventListener('pointerup', onUp)
            }}
            onKeyDown={(e) => {
              if (e.key === 'ArrowLeft') setPanelW((w) => Math.min(PANEL_MAX_W, w + 16))
              if (e.key === 'ArrowRight') setPanelW((w) => Math.max(PANEL_MIN_W, w - 16))
            }}
          >
            <span className="absolute inset-y-0 left-0.5 w-[3px] rounded-full bg-brand-400/0 transition-colors group-hover/rz:bg-brand-400/50 group-focus-visible/rz:bg-brand-500/70" />
          </div>
          {/* Region A — context header. Liquid-glass band: brand teal→green tint
              floating on the frosted panel, sealed with a hairline light border. */}
          <header
            className={`relative shrink-0 border-b px-4 pt-3 pb-2.5 transition-all duration-300 ${
              scrolled ? 'border-white/70 shadow-[0_6px_18px_-8px_rgba(13,45,70,0.22)]' : 'border-white/50'
            }`}
            style={{
              background:
                'linear-gradient(135deg, rgba(22,138,173,0.14) 0%, rgba(255,255,255,0.12) 55%, rgba(118,200,147,0.12) 100%)',
            }}
          >
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-dizzaroo-gradient text-white shadow-sm">
                <Sparkles className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-serif text-lg leading-none text-gray-900">
                  Orbit
                  <span className="mt-1 block h-0.5 w-8 rounded-full bg-brand-500" />
                </div>
                <div className="mt-1.5 truncate text-ui-caption text-gray-500">
                  {[studyName, siteName, userName].filter(Boolean).join('  ·  ')}
                </div>
              </div>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-ui-caption ${
                  awaitingApproval
                    ? 'bg-warning-50 text-warning-600'
                    : streaming
                      ? 'bg-brand-50 text-brand-700'
                      : connected
                        ? 'bg-accent-50 text-accent-600'
                        : 'bg-gray-100 text-gray-500'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    awaitingApproval
                      ? 'bg-warning-500'
                      : streaming
                        ? 'bg-brand-500 orbit-blink'
                        : connected
                          ? 'bg-accent-500'
                          : 'bg-gray-400'
                  }`}
                />
                {awaitingApproval ? 'Waiting for you' : streaming ? 'Working' : connected ? 'Ready' : 'Connecting…'}
              </span>
              {watch ? (
                <button
                  type="button"
                  onClick={() => {
                    setWatch(false)
                    setWatchPrompt(false)
                  }}
                  aria-label="Watching — click to stop"
                  aria-pressed="true"
                  title="Watching: auto-continuing as you scroll. Click to stop."
                  className="ml-0.5 inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2 py-0.5 text-ui-caption font-medium text-brand-700 ring-1 ring-brand-200 hover:bg-brand-100"
                >
                  <Eye className="h-3 w-3 orbit-blink" /> Watching
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setWatch(true)}
                  aria-label="Turn on Watch mode (auto-continue while you scroll)"
                  aria-pressed="false"
                  title="Watch: auto-continue reads/fills as you scroll (off by default)"
                  className="ml-0.5 rounded-lg p-1 text-gray-400 transition hover:bg-white/60 hover:text-brand-600 active:scale-90"
                >
                  <Eye className="h-[18px] w-[18px]" />
                </button>
              )}
              <button
                type="button"
                onClick={() => setWide((v) => !v)}
                aria-label={wide ? 'Exit focus mode' : 'Focus mode (wider panel)'}
                aria-pressed={wide}
                title={wide ? 'Exit focus mode' : 'Focus mode — widen the panel'}
                className="ml-0.5 rounded-lg p-1 text-gray-400 transition hover:bg-white/60 hover:text-brand-600 active:scale-90"
              >
                {wide ? <Minimize2 className="h-[18px] w-[18px]" /> : <Maximize2 className="h-[18px] w-[18px]" />}
              </button>
              <button
                type="button"
                onClick={() => setShowMemory(true)}
                aria-label="What Orbit remembers"
                title="What Orbit remembers"
                className="ml-0.5 rounded-lg p-1 text-gray-400 transition hover:bg-white/60 hover:text-brand-600 active:scale-90"
              >
                <Brain className="h-[18px] w-[18px]" />
              </button>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="ml-0.5 rounded-lg p-1 text-gray-400 transition hover:bg-white/60 hover:text-gray-700 active:scale-90">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
              </button>
            </div>
          </header>

          {/* The conversation — ONE continuous stream (aria-live announces streamed
              replies). Past turns fold to a quiet one-liner in place; the live turn
              is simply the bottom of the stream. */}
          {/* Soft layered brand wash floating on the frosted glass (no opaque base —
              the blurred app behind shows through) so cards float with depth. */}
          <div
            className="relative flex-1 overflow-y-auto px-3 py-3 space-y-2"
            aria-live="polite"
            onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 8)}
            style={{
              background:
                'radial-gradient(at 0% 0%, rgba(22,138,173,0.07) 0px, transparent 55%), ' +
                'radial-gradient(at 100% 30%, rgba(118,200,147,0.06) 0px, transparent 50%), ' +
                'radial-gradient(at 50% 100%, rgba(30,115,190,0.05) 0px, transparent 60%)',
            }}
          >
            {turns.length === 0 && <OrbitHero starters={starters} onStarter={handleStarter} welcome={welcome} />}
            {turns.map((t, i) => {
              const isActive = i >= activeStart
              const isExpanded = expandedHistory.has(i)

              // ---- Past user message: smaller, muted bubble + hover "ask again".
              if (t.role === 'user' && !isActive) {
                return (
                  <div key={i} className="group/urow flex items-center justify-end gap-1">
                    <button
                      type="button"
                      disabled={streaming}
                      onClick={() => void send(t.text)}
                      aria-label="Ask this again"
                      title="Ask this again"
                      className="shrink-0 rounded p-1 text-gray-300 opacity-0 transition-opacity group-hover/urow:opacity-100 focus-visible:opacity-100 motion-reduce:opacity-100 hover:bg-brand-50 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 disabled:opacity-30"
                    >
                      <RotateCcw size={12} />
                    </button>
                    <div className="max-w-[85%] rounded-md bg-brand-100/70 px-2.5 py-1 text-ui-body-sm text-brand-700/80 whitespace-pre-wrap break-words">
                      {t.text}
                    </div>
                  </div>
                )
              }

              // ---- Live user message: full-weight bubble.
              if (t.role === 'user') {
                return (
                  <div key={i} className="flex justify-end orbit-block-in">
                    <div className="max-w-[88%] rounded-lg rounded-br-sm bg-brand-500/85 backdrop-blur-sm ring-1 ring-white/25 px-3 py-1.5 text-ui-body text-white shadow-sm whitespace-pre-wrap break-words">
                      {t.text}
                    </div>
                  </div>
                )
              }

              // ---- Past Orbit turn, folded: one quiet line in the stream.
              if (!isActive && !isExpanded) {
                return (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setExpandedHistory((prev) => new Set(prev).add(i))}
                    className="flex w-full items-center gap-1.5 rounded-md px-1 py-0.5 text-left hover:bg-brand-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
                    aria-expanded={false}
                  >
                    <ChevronRight size={13} className="shrink-0 text-gray-300" />
                    <span className="shrink-0 text-ui-caption font-semibold uppercase tracking-wide text-brand-600">Orbit</span>
                    <span className="truncate text-ui-body-sm text-gray-500">{summarizeAssistant(t)}</span>
                    <span className="ml-auto shrink-0 text-ui-caption tabular-nums text-gray-300">{timeOf(t.at)}</span>
                  </button>
                )
              }

              // ---- Past Orbit turn, unfolded (re-collapsible) — or the live turn.
              return (
                <div key={i} className="space-y-2">
                  {!isActive && (
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedHistory((prev) => {
                          const n = new Set(prev)
                          n.delete(i)
                          return n
                        })
                      }
                      className="flex w-full items-center gap-1.5 rounded-md px-1 py-0.5 text-left hover:bg-brand-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
                      aria-expanded
                    >
                      <ChevronDown size={13} className="shrink-0 text-gray-400" />
                      <span className="shrink-0 text-ui-caption font-semibold uppercase tracking-wide text-brand-600">Orbit</span>
                      <span className="ml-auto shrink-0 text-ui-caption tabular-nums text-gray-300">{timeOf(t.at)}</span>
                    </button>
                  )}
                  {isActive && (t.trace.length > 0 || t.pending) && <TraceView trace={t.trace} pending={t.pending} />}
                  {t.blocks.map((block, j) =>
                    isActive ? (
                      // Blocks rise in with a small cascade (CSS-only; runs once on
                      // mount; disabled under prefers-reduced-motion in OrbitStyles).
                      <div key={j} className="orbit-block-in" style={{ animationDelay: `${Math.min(j, 6) * 45}ms` }}>
                        <BlockRenderer block={block} h={handlers} />
                      </div>
                    ) : (
                      <BlockRenderer key={j} block={block} h={handlers} />
                    ),
                  )}
                </div>
              )
            })}
            <div ref={endRef} />
            {activeStart > 0 && (
              <button
                type="button"
                onClick={scrollToLatest}
                className="sticky bottom-1 ml-auto flex items-center gap-1 rounded-full bg-brand-500/80 backdrop-blur-sm ring-1 ring-white/30 text-white px-2.5 py-1 text-ui-caption shadow-card hover:bg-brand-600/90"
                aria-label="Jump to latest"
              >
                <ArrowDown size={12} /> Latest
              </button>
            )}
          </div>

          {/* Region D — command bar (glass band matching the header so the shell
              bookends read as one sheet of frosted glass) */}
          <div
            className="relative shrink-0 border-t border-white/50 p-3"
            style={{
              background:
                'linear-gradient(135deg, rgba(255,255,255,0.30) 0%, rgba(22,138,173,0.07) 60%, rgba(118,200,147,0.07) 100%)',
            }}
          >
            {/* Trust line: what a screen-read would see right now (visible-only,
                made visible) + the Watch whisper when Watch is on. */}
            {(screenLabel || watch) && (
              <div className="mb-1.5 flex items-center justify-between gap-2 text-ui-caption text-gray-400">
                {screenLabel ? (
                  <span className="inline-flex min-w-0 items-center gap-1 truncate">
                    <Eye size={11} className="shrink-0 text-gray-300" />
                    Looking at: {screenLabel}
                    {studyName ? ` · ${studyName}` : ''}
                  </span>
                ) : (
                  <span />
                )}
                {watch && (
                  <span className="shrink-0 text-brand-600/80">
                    watching
                    {lastContinueAt ? ` · continued ${timeOf(lastContinueAt)}` : ''}
                    {hiddenBelow > 0 ? ` · ${hiddenBelow} field${hiddenBelow === 1 ? '' : 's'} below the fold` : ''}
                  </span>
                )}
              </div>
            )}
            {watchPrompt && (
              <div className="mb-2 flex items-center gap-2 rounded-md border border-brand-200 border-l-4 border-l-brand-400 bg-brand-50/60 px-3 py-2" role="status">
                <Eye className="h-4 w-4 shrink-0 text-brand-600" />
                <span className="flex-1 text-ui-body-sm text-gray-700">Looks like we're done here — turn Watch off?</span>
                <button
                  type="button"
                  onClick={() => {
                    setWatch(false)
                    setWatchPrompt(false)
                  }}
                  className="rounded-md bg-brand-500 px-2.5 py-1 text-ui-caption font-medium text-white hover:bg-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
                >
                  Turn off
                </button>
                <button
                  type="button"
                  onClick={() => setWatchPrompt(false)}
                  className="py-1 text-ui-caption font-medium text-gray-600 underline decoration-gray-300 underline-offset-2 hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 rounded-sm"
                >
                  Keep watching
                </button>
              </div>
            )}
            {turns.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {starters.map((c) => {
                  const Icon = actionIcon(`${c.label} ${c.message}`)
                  return (
                    <button key={c.label} type="button" disabled={streaming && !c.prefill} onClick={() => handleStarter(c)} className={`inline-flex items-center gap-1 ${chipClass}`}>
                      <Icon size={12} className="shrink-0" />
                      {c.label}
                    </button>
                  )
                })}
              </div>
            )}
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submitInput()
                  }
                }}
                rows={1}
                placeholder="Ask Orbit anything…"
                className="flex-1 resize-none border-0 border-b border-gray-300 bg-transparent px-1 py-2 text-ui-body text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-b-2 focus:border-brand-500 max-h-32"
              />
              <button
                type="button"
                onClick={submitInput}
                disabled={streaming || !input.trim()}
                aria-label="Send"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-dizzaroo-gradient text-white shadow-sm ring-1 ring-white/40 transition-transform hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 disabled:opacity-40 disabled:hover:scale-100"
              >
                {streaming ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></svg>
                )}
              </button>
            </div>
          </div>

          {/* Memory controls overlay — view / edit / exclude / delete what Orbit remembers */}
          {showMemory && <MemoryPanel onClose={() => setShowMemory(false)} />}
        </div>
      )}
    </>
  )
}

/** Compact live working trace: steps while running, collapses to a summary line. */
const TraceView: React.FC<{ trace: TraceStep[]; pending: boolean }> = ({ trace, pending }) => {
  const [expanded, setExpanded] = useState(false)
  if (trace.length === 0 && pending) {
    // iMessage-style typing indicator on a small glass pill.
    return (
      <div className="inline-flex items-center gap-2 rounded-full bg-white/60 px-3 py-1.5 ring-1 ring-white/60 shadow-sm backdrop-blur-sm">
        <span className="flex items-center gap-1" aria-hidden="true">
          <span className="orbit-dot h-1.5 w-1.5 rounded-full bg-brand-500" />
          <span className="orbit-dot h-1.5 w-1.5 rounded-full bg-brand-500" style={{ animationDelay: '.15s' }} />
          <span className="orbit-dot h-1.5 w-1.5 rounded-full bg-brand-500" style={{ animationDelay: '.3s' }} />
        </span>
        <span className="text-ui-caption text-gray-500">Thinking…</span>
      </div>
    )
  }
  const done = !pending
  if (done && !expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="flex items-center gap-1.5 text-ui-caption text-gray-500 hover:text-gray-700"
      >
        <Check size={13} className="text-accent-600" />
        <span className="truncate">{trace.map((s) => s.label.replace(/…$/, '')).join(' · ')}</span>
      </button>
    )
  }
  return (
    <div className="border-l-2 border-brand-200 pl-2.5 py-0.5 space-y-1">
      {trace.map((s, i) => (
        <div key={i} className="flex items-center gap-1.5 text-ui-caption text-gray-600">
          {s.status === 'running' ? (
            <Loader2 size={12} className="animate-spin text-brand-500" />
          ) : s.status === 'ok' ? (
            <Check size={12} className="text-accent-600" />
          ) : (
            <span className="h-2 w-2 rounded-full bg-warning-500" />
          )}
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  )
}

/** Memory controls: what Orbit remembers about the user — view, edit, exclude,
 *  delete. Derived, non-sensitive items only (the backend never stores PHI). */
const MemoryPanel: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [items, setItems] = useState<MemoryItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  const load = useCallback(() => {
    setError(null)
    listMemories()
      .then(setItems)
      .catch(() => setError("Couldn't load your memories."))
  }, [])
  useEffect(load, [load])

  const onSaveEdit = async (id: string) => {
    try {
      await editMemory(id, draft)
      setEditingId(null)
      load()
    } catch {
      setError("That edit didn't stick — text may be empty or look sensitive.")
    }
  }
  const onExclude = async (id: string) => {
    await excludeMemory(id).catch(() => {})
    load()
  }
  const onDelete = async (id: string) => {
    await deleteMemory(id).catch(() => {})
    load()
  }

  const active = (items || []).filter((i) => !i.excluded)
  const excluded = (items || []).filter((i) => i.excluded)

  return (
    <div className="absolute inset-0 z-10 flex flex-col rounded-[28px] bg-white/70 backdrop-blur-xl backdrop-saturate-150">
      <header className="flex items-center gap-2 border-b border-white/50 px-4 py-3">
        <Brain className="h-4 w-4 text-brand-600" />
        <div className="flex-1 text-ui-h2 text-gray-900">What Orbit remembers</div>
        <button type="button" onClick={onClose} aria-label="Back" className="rounded-lg p-1 text-gray-400 transition hover:bg-white/60 hover:text-gray-700 active:scale-90">
          <X className="h-[18px] w-[18px]" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        <p className="text-ui-caption text-gray-400">
          These are preferences and working patterns Orbit derived over time — never patient data or record contents. You're in control: edit, hide, or delete anything.
        </p>

        {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-ui-body-sm text-red-700">{error}</div>}
        {items === null && !error && <div className="text-ui-body-sm text-gray-400">Loading…</div>}
        {items !== null && active.length === 0 && excluded.length === 0 && (
          <div className="text-ui-body-sm text-gray-500">Nothing remembered yet — Orbit learns as you work together.</div>
        )}

        {active.map((it) => (
          <div key={it.id} className="rounded-xl border border-white/60 bg-white/55 shadow-sm px-3 py-2">
            <div className="mb-1 flex items-center gap-2">
              <span className="rounded-full bg-brand-50 px-2 py-0.5 text-ui-caption font-medium text-brand-700">{it.type}</span>
              <span className="ml-auto flex items-center gap-1">
                {editingId !== it.id && (
                  <>
                    <button type="button" title="Edit" onClick={() => { setEditingId(it.id); setDraft(it.text) }} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"><Pencil className="h-3.5 w-3.5" /></button>
                    <button type="button" title="Hide (don't use)" onClick={() => onExclude(it.id)} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"><EyeOff className="h-3.5 w-3.5" /></button>
                    <button type="button" title="Delete" onClick={() => onDelete(it.id)} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-red-600"><Trash2 className="h-3.5 w-3.5" /></button>
                  </>
                )}
              </span>
            </div>
            {editingId === it.id ? (
              <div className="flex items-center gap-2">
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  className="flex-1 rounded-lg border border-gray-200 px-2 py-1 text-ui-body-sm focus:border-brand-300 focus:outline-none focus:ring-2 focus:ring-brand-500/25"
                />
                <button type="button" onClick={() => onSaveEdit(it.id)} className="rounded-lg bg-brand-500 px-2 py-1 text-ui-caption text-white hover:bg-brand-600">Save</button>
                <button type="button" onClick={() => setEditingId(null)} className="rounded-lg px-2 py-1 text-ui-caption text-gray-500 hover:bg-gray-100">Cancel</button>
              </div>
            ) : (
              <div className="text-ui-body-sm text-gray-700">{it.text}</div>
            )}
          </div>
        ))}

        {excluded.length > 0 && (
          <div className="pt-2">
            <div className="mb-1 text-ui-caption font-semibold uppercase tracking-wide text-gray-400">Hidden</div>
            {excluded.map((it) => (
              <div key={it.id} className="flex items-center gap-2 rounded-xl border border-dashed border-gray-200 px-3 py-2">
                <span className="flex-1 text-ui-body-sm text-gray-400 line-through">{it.text}</span>
                <button type="button" title="Delete" onClick={() => onDelete(it.id)} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-red-600"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** Orbit's mood — what the buddy character is expressing right now. */
type BuddyMood = 'idle' | 'thinking' | 'waiting' | 'excited' | 'sad'

/** Orbit the buddy: a little floating character, not a logo-in-a-disc. It has
 *  an antenna, arms, eyes with pupils, brows, and five mouth shapes, and its
 *  whole demeanor changes with `mood`:
 *   - idle: floats and breathes, blinks with a double-flutter, gaze wanders,
 *     and once a cycle it does a proper eye-roll.
 *   - thinking: pupils scan side-to-side like reading, one brow arches, the
 *     mouth becomes a focused "o", thought dots rise from the antenna.
 *   - waiting: brows up, eyes wide on you, flat mouth — "your move".
 *   - excited: open smile, blush, quick happy bounce, waves an arm.
 *   - sad: inner brows tilt up, frown, pupils drop, the float slows.
 *  Every motion is a CSS transform/opacity keyframe on tiny SVG parts —
 *  compositor-only, no per-frame JS — and all of it freezes under
 *  prefers-reduced-motion into a static friendly character. */
const OrbitBuddy: React.FC<{ mood: BuddyMood }> = ({ mood }) => (
  <svg viewBox="0 0 64 74" width={62} height={72} className={`orbit-buddy mood-${mood}`} aria-hidden="true">
    <defs>
      <linearGradient id="orbitBuddySkin" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#4ac6de" />
        <stop offset="100%" stopColor="#7fd8a3" />
      </linearGradient>
    </defs>
    {/* ground shadow (squeezes as the body rises — sells the float) */}
    <ellipse className="orbit-b-shadow" cx="32" cy="70.5" rx="12" ry="2.6" fill="rgba(15,23,42,.26)" />
    <g className="orbit-b-float">
      {/* antenna — a glossy bobble that pulses while working */}
      <line x1="32" y1="12.5" x2="32" y2="7.5" stroke="#4ac6de" strokeWidth="2" strokeLinecap="round" />
      <circle className="orbit-b-tip" cx="32" cy="5.4" r="2.9" fill="#9be8b8" />
      <circle cx="31" cy="4.5" r="1" fill="rgba(255,255,255,.85)" />
      {/* twinkling sparkles beside the head */}
      <path className="orbit-b-spark" d="M53.5 14.5 L54.5 16.7 L56.7 17.7 L54.5 18.7 L53.5 20.9 L52.5 18.7 L50.3 17.7 L52.5 16.7 Z" fill="#fff" />
      <path className="orbit-b-spark orbit-b-spark-2" d="M11.5 19 L12.2 20.5 L13.7 21.2 L12.2 21.9 L11.5 23.4 L10.8 21.9 L9.3 21.2 L10.8 20.5 Z" fill="#fff" />
      {/* little arm nubs (the right one waves when excited) */}
      <rect className="orbit-b-arm" x="5" y="36" width="6.5" height="12" rx="3.25" fill="url(#orbitBuddySkin)" />
      <rect className="orbit-b-arm orbit-b-arm-r" x="52.5" y="36" width="6.5" height="12" rx="3.25" fill="url(#orbitBuddySkin)" />
      {/* body — soft round blob */}
      <rect x="9.5" y="12" width="45" height="50" rx="22.5" fill="url(#orbitBuddySkin)" />
      <ellipse cx="24" cy="20" rx="12" ry="6" fill="rgba(255,255,255,.3)" />
      {/* hair: a side-swept fringe of soft tufts across the crown — the
          antenna pokes out from between them */}
      <g fill="#1f6f8d">
        <path d="M15.5 21.5 Q17 12 26 10.5 Q23.5 13.5 24 16.5 Q19.5 17 15.5 21.5 Z" />
        <path d="M25.5 13.8 Q27.5 7.8 33 8.4 Q30 10.8 30 13.6 Q27.5 12.8 25.5 13.8 Z" />
        <path d="M36.5 13.2 Q40.5 8.6 45 11 Q42 12.4 41.2 15.4 Q38.8 13.6 36.5 13.2 Z" />
        <path d="M45.5 16 Q49.5 14 51.5 18.5 Q48.7 18.2 47 20.5 Q46.6 17.8 45.5 16 Z" />
      </g>
      {/* rosy blush — always softly there, glows when excited */}
      <ellipse className="orbit-b-blush" cx="16" cy="42" rx="3.6" ry="2.4" fill="#ffc9d4" />
      <ellipse className="orbit-b-blush" cx="48" cy="42" rx="3.6" ry="2.4" fill="#ffc9d4" />
      {/* brows — hidden when calm; they appear only to emote */}
      <path className="orbit-b-brow orbit-b-brow-l" d="M16.5 25.5 Q21.5 23.5 26.5 25.5" stroke="#0e3a4f" strokeWidth="2" strokeLinecap="round" fill="none" />
      <path className="orbit-b-brow orbit-b-brow-r" d="M37.5 25.5 Q42.5 23.5 47.5 25.5" stroke="#0e3a4f" strokeWidth="2" strokeLinecap="round" fill="none" />
      {/* big glossy kawaii eyes: dark iris + two catchlights; the group blinks
          (scaleY) while the inner group carries the gaze */}
      <g className="orbit-b-eye">
        <g className="orbit-b-pupil">
          <ellipse cx="21.5" cy="35" rx="6" ry="7" fill="#113c52" />
          <circle cx="19.4" cy="32.2" r="2.2" fill="#fff" />
          <circle cx="23.6" cy="38" r="1.1" fill="rgba(255,255,255,.85)" />
        </g>
      </g>
      <g className="orbit-b-eye orbit-b-eye-r">
        <g className="orbit-b-pupil">
          <ellipse cx="42.5" cy="35" rx="6" ry="7" fill="#113c52" />
          <circle cx="40.4" cy="32.2" r="2.2" fill="#fff" />
          <circle cx="44.6" cy="38" r="1.1" fill="rgba(255,255,255,.85)" />
        </g>
      </g>
      {/* a single tear that wells up and slides down when sad */}
      <ellipse className="orbit-b-tear" cx="15.2" cy="44.5" rx="1.5" ry="2.2" fill="#d6f1fa" />
      {/* mouths — exactly one is visible per mood (cross-faded in CSS). Idle
          alternates between the content resting mouth and a passing smile. */}
      <path className="orbit-b-m orbit-b-m-rest" d="M28.5 47 Q32 48.6 35.5 47" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" fill="none" />
      <path className="orbit-b-m orbit-b-m-smile" d="M27.5 46 Q32 49.8 36.5 46" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" fill="none" />
      <path className="orbit-b-m orbit-b-m-open" d="M26.5 45 Q32 52.5 37.5 45 Z" fill="#fff" />
      <path className="orbit-b-m orbit-b-m-frown" d="M27.5 50 Q32 46.4 36.5 50" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" fill="none" />
      <circle className="orbit-b-m orbit-b-m-o" cx="32" cy="47.5" r="2.3" stroke="#fff" strokeWidth="2.1" fill="none" />
      <path className="orbit-b-m orbit-b-m-flat" d="M28.5 47.5 H35.5" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" fill="none" />
      {/* thought dots (thinking only) */}
      <g className="orbit-b-dots">
        <circle className="orbit-b-dot" cx="46.5" cy="10.5" r="1.5" fill="#4ac6de" />
        <circle className="orbit-b-dot" cx="51.5" cy="8" r="1.9" fill="#4ac6de" style={{ animationDelay: '.15s' }} />
        <circle className="orbit-b-dot" cx="57" cy="5.5" r="2.2" fill="#7fd8a3" style={{ animationDelay: '.3s' }} />
      </g>
    </g>
  </svg>
)

/** Calm, minimal orbit empty state: a teal core (pulse) with satellites orbiting
 *  faint rings, a serif intro, one capability line, and context-aware starters.
 *  Motion is disabled under prefers-reduced-motion (see OrbitStyles). */
// "Good morning / afternoon / evening" for the hero headline.
function timeGreeting(): string {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

const OrbitHero: React.FC<{ starters: Starter[]; onStarter: (s: Starter) => void; welcome: WelcomeBack | null }> = ({
  starters,
  onStarter,
  welcome,
}) => (
  <div className="flex h-full flex-col items-center justify-center px-8 text-center">
    <div className="relative h-24 w-24">
      {/* rings, brand-tinted (Paper Brief: thin, deliberate lines) */}
      <div className="absolute inset-0 rounded-full border border-brand-100" />
      <div className="absolute inset-[14px] rounded-full border border-brand-100/70" />
      {/* pulse + core */}
      <div className="absolute inset-0 m-auto h-9 w-9 rounded-full bg-brand-500/15 orbit-pulse" />
      <div className="absolute inset-0 m-auto flex h-6 w-6 items-center justify-center rounded-full bg-dizzaroo-gradient text-white shadow-sm">
        <Sparkles className="h-3.5 w-3.5" />
      </div>
      {/* satellites — each carries a starter: tap the orbiting dot to send it.
          (The chips below remain the primary, always-discoverable path.)
          Each satellite glows and drags a faint comet trail behind it (the trail
          div rotates with the same wrapper, so it always follows the dot). */}
      <div className="absolute inset-0 orbit-spin">
        <div className="orbit-trail absolute inset-0" aria-hidden="true" />
        {starters[0] && (
          <button
            type="button"
            onClick={() => onStarter(starters[0])}
            aria-label={starters[0].label}
            title={starters[0].label}
            className="orbit-sat-glow absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 rounded-full bg-brand-500 transition-transform hover:scale-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
          />
        )}
      </div>
      <div className="absolute inset-[14px] orbit-spin-rev">
        <div className="orbit-trail-accent absolute inset-0" aria-hidden="true" />
        {starters[1] && (
          <button
            type="button"
            onClick={() => onStarter(starters[1])}
            aria-label={starters[1].label}
            title={starters[1].label}
            className="orbit-sat-glow-accent absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 rounded-full bg-accent-500 transition-transform hover:scale-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/40"
          />
        )}
      </div>
    </div>

    <h2 className="mt-7 bg-dizzaroo-gradient bg-clip-text font-serif text-2xl text-transparent">
      {welcome?.returning ? 'Welcome back' : `${timeGreeting()} — I'm Orbit`}
    </h2>
    <div className="mt-2 h-0.5 w-10 rounded-full bg-brand-500" />
    {welcome?.returning && welcome.last ? (
      <p className="mt-3 max-w-[19rem] text-ui-body text-gray-500">
        Last time you were asking about “{welcome.last.text}”. Want to pick that back up, or start something new?
      </p>
    ) : (
      <p className="mt-3 max-w-[19rem] text-ui-body text-gray-500">
        Ask me to open a screen, find a record, summarize your work, or create a task — I'll do it for you.
      </p>
    )}

    <div className="mt-6 flex flex-wrap justify-center gap-2">
      {starters.map((s) => {
        const Icon = actionIcon(`${s.label} ${s.message}`)
        return (
          <button
            key={s.label}
            type="button"
            onClick={() => onStarter(s)}
            className="inline-flex items-center gap-1.5 rounded-full bg-white/55 px-3.5 py-1.5 text-ui-body font-medium text-brand-700 ring-1 ring-white/60 shadow-sm backdrop-blur-sm transition hover:bg-white/80 hover:shadow active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
          >
            <Icon size={13} className="shrink-0" />
            {s.label}
          </button>
        )
      })}
    </div>
  </div>
)

/** Orbit animation keyframes (calm) + liquid-glass surfaces + reduced-motion off-switch. */
const OrbitStyles: React.FC = () => (
  <style>{`
    /* Liquid glass (iOS-style): frosted translucent sheet — heavy blur with a
       saturation boost so the app's colors glow through, a hairline light
       border, and inset specular highlights along the top/bottom edges. */
    .orbit-glass {
      background: linear-gradient(165deg, rgba(255,255,255,0.68) 0%, rgba(255,255,255,0.44) 55%, rgba(255,255,255,0.56) 100%);
      -webkit-backdrop-filter: blur(28px) saturate(180%);
      backdrop-filter: blur(28px) saturate(180%);
      border: 1px solid rgba(255,255,255,0.55);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.85),
        inset 0 -1px 0 rgba(255,255,255,0.25),
        0 12px 40px rgba(13,45,70,0.16),
        0 2px 8px rgba(13,45,70,0.07);
    }
    /* Glass edge for solid-gradient chrome (launcher, send): specular top light. */
    .orbit-glass-edge {
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.55),
        inset 0 -1px 0 rgba(0,0,0,0.06),
        0 8px 24px rgba(22,138,173,0.30);
    }
    /* No backdrop-filter support → near-opaque fallback so text stays readable. */
    @supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
      .orbit-glass { background: rgba(250,253,254,0.97); }
    }
    @keyframes orbit-spin { to { transform: rotate(360deg); } }
    @keyframes orbit-spin-rev { to { transform: rotate(-360deg); } }
    @keyframes orbit-pulse { 0%,100% { transform: scale(.85); opacity:.55; } 50% { transform: scale(1.35); opacity:0; } }
    @keyframes orbit-blink { 0%,100% { opacity:1; } 50% { opacity:.35; } }
    @keyframes orbit-rise { from { opacity:0; transform: translateY(7px) scale(.98); } to { opacity:1; transform: none; } }
    @keyframes orbit-stamp-in { from { opacity:0; transform: scale(1.5); } to { opacity:1; transform: scale(1); } }
    @keyframes orbit-panel-in { from { opacity:0; transform: translateX(28px) scale(.97); } to { opacity:1; transform: none; } }
    @keyframes orbit-dot { 0%,60%,100% { transform: translateY(0); opacity:.45; } 30% { transform: translateY(-3px); opacity:1; } }
    @keyframes orbit-aurora-a { to { transform: translate(70px, 90px) scale(1.15); } }
    @keyframes orbit-aurora-b { to { transform: translate(-60px, -110px) scale(1.2); } }
    /* ── Orbit buddy (the persona launcher) — every rule below animates only
       transform/opacity on tiny SVG parts: compositor-cheap, no layout/paint. */
    .orbit-buddy .orbit-b-shadow, .orbit-buddy .orbit-b-eye, .orbit-buddy .orbit-b-pupil,
    .orbit-buddy .orbit-b-brow, .orbit-buddy .orbit-b-arm, .orbit-buddy .orbit-b-dot,
    .orbit-buddy .orbit-b-tip, .orbit-buddy .orbit-b-spark,
    .orbit-buddy .orbit-b-tear { transform-box: fill-box; transform-origin: center; }
    @keyframes orbit-b-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-3.5px); } }
    @keyframes orbit-b-shadow { 0%,100% { transform: scaleX(1); opacity:.3; } 50% { transform: scaleX(.78); opacity:.18; } }
    .orbit-b-float { animation: orbit-b-float 3.6s ease-in-out infinite; }
    .orbit-b-shadow { animation: orbit-b-shadow 3.6s ease-in-out infinite; }
    .mood-excited .orbit-b-float, .mood-excited .orbit-b-shadow { animation-duration: .6s; }
    .mood-sad .orbit-b-float, .mood-sad .orbit-b-shadow { animation-duration: 5.6s; }
    /* blink: quick double-flutter every few seconds; right eye a beat behind */
    @keyframes orbit-eye-blink {
      0%, 3.5%, 8%, 100% { transform: scaleY(1); }
      5%, 6.5% { transform: scaleY(.12); }
    }
    .orbit-b-eye { animation: orbit-eye-blink 4.4s ease-in-out infinite; }
    .orbit-b-eye-r { animation-delay: .06s; }
    /* pupils: the idle wander includes a full eye-roll once per cycle; thinking
       scans side-to-side like reading, glancing up. */
    @keyframes orbit-b-wander {
      0%, 16%, 100% { transform: translate(0,0); }
      20%, 28% { transform: translate(2px, .3px); }
      32%, 44% { transform: translate(0,0); }
      48%, 56% { transform: translate(-2px, .3px); }
      60%, 68% { transform: translate(0,0); }
      72% { transform: translate(-1.4px,-1.6px); }
      75% { transform: translate(0,-2.2px); }
      78% { transform: translate(1.8px,-1.2px); }
      81% { transform: translate(2px,.8px); }
      86% { transform: translate(0,0); }
    }
    @keyframes orbit-b-scan { 0%,100% { transform: translate(-1.8px,-1.4px); } 50% { transform: translate(1.8px,-1.4px); } }
    .orbit-b-pupil { transition: transform .25s ease; }
    .mood-idle .orbit-b-pupil { animation: orbit-b-wander 11s ease-in-out infinite; }
    .mood-thinking .orbit-b-pupil { animation: orbit-b-scan 2.2s ease-in-out infinite; }
    .mood-waiting .orbit-b-pupil { transform: translateY(-1.6px); }
    .mood-excited .orbit-b-pupil { transform: translateY(-1.2px); }
    .mood-sad .orbit-b-pupil { transform: translateY(2px); }
    /* brows: invisible when calm (cuter); they fade in only to emote */
    .orbit-b-brow { opacity: 0; transition: transform .25s ease, opacity .25s ease; }
    .mood-thinking .orbit-b-brow-r { opacity: 1; transform: translateY(-2.4px) rotate(6deg); }
    .mood-waiting .orbit-b-brow-l, .mood-waiting .orbit-b-brow-r { opacity: 1; transform: translateY(-2.4px); }
    .mood-sad .orbit-b-brow-l { opacity: 1; transform: rotate(-13deg) translateY(.4px); }
    .mood-sad .orbit-b-brow-r { opacity: 1; transform: rotate(13deg) translateY(.4px); }
    /* mouths: exactly one visible per mood, cross-faded */
    .orbit-b-m { opacity: 0; transition: opacity .16s ease; }
    .mood-excited .orbit-b-m-open, .mood-sad .orbit-b-m-frown,
    .mood-thinking .orbit-b-m-o, .mood-waiting .orbit-b-m-flat { opacity: 1; }
    /* idle isn't a frozen grin: mostly the content resting mouth, breaking
       into a smile for a stretch of each cycle (as if remembering something
       nice), then settling again. The two keyframes are exact complements. */
    @keyframes orbit-b-m-restcycle { 0%, 58%, 88%, 100% { opacity: 1; } 63%, 83% { opacity: 0; } }
    @keyframes orbit-b-m-smilecycle { 0%, 58%, 88%, 100% { opacity: 0; } 63%, 83% { opacity: 1; } }
    .mood-idle .orbit-b-m-rest { animation: orbit-b-m-restcycle 16s ease-in-out infinite; }
    .mood-idle .orbit-b-m-smile { animation: orbit-b-m-smilecycle 16s ease-in-out infinite; }
    /* rosy blush: always softly there, glows when excited, gone when sad */
    .orbit-b-blush { opacity: .4; transition: opacity .25s ease; }
    .mood-excited .orbit-b-blush { opacity: .9; }
    .mood-sad .orbit-b-blush { opacity: 0; }
    /* sparkles beside the head twinkle gently (hidden when sad) */
    @keyframes orbit-b-twinkle { 0%,100% { opacity: 0; transform: scale(.5); } 50% { opacity: .95; transform: scale(1); } }
    .orbit-b-spark { animation: orbit-b-twinkle 3.2s ease-in-out infinite; }
    .orbit-b-spark-2 { animation-delay: 1.6s; }
    .mood-sad .orbit-b-spark { animation: none; opacity: 0; }
    /* the sad tear: wells up, slides down, fades — on repeat */
    @keyframes orbit-b-tear { 0% { opacity: 0; transform: translateY(0); } 25% { opacity: .95; } 100% { opacity: 0; transform: translateY(7px); } }
    .orbit-b-tear { opacity: 0; }
    .mood-sad .orbit-b-tear { animation: orbit-b-tear 2.4s ease-in infinite; }
    @keyframes orbit-b-wave { 0%,100% { transform: rotate(0deg); } 50% { transform: rotate(-40deg); } }
    .orbit-b-arm { transition: transform .25s ease; }
    .orbit-b-arm-r { transform-origin: top center; }
    .mood-excited .orbit-b-arm-r { animation: orbit-b-wave .6s ease-in-out infinite; }
    .mood-sad .orbit-b-arm { transform: translateY(1.6px); }
    /* antenna tip + thought dots while working */
    .mood-thinking .orbit-b-tip { animation: orbit-blink 1s ease-in-out infinite; }
    .mood-waiting .orbit-b-tip { animation: orbit-blink 1.4s ease-in-out infinite; }
    .orbit-b-dots { opacity: 0; transition: opacity .2s ease; }
    .mood-thinking .orbit-b-dots { opacity: 1; }
    .orbit-b-dot { animation: orbit-dot 1.2s ease-in-out infinite; }
    .orbit-spin { animation: orbit-spin 9s linear infinite; }
    .orbit-spin-rev { animation: orbit-spin-rev 6s linear infinite; }
    .orbit-spin-fast { animation: orbit-spin 1.8s linear infinite; }
    .orbit-spin-rev-fast { animation: orbit-spin-rev 1.2s linear infinite; }
    .orbit-pulse { animation: orbit-pulse 2.6s ease-in-out infinite; }
    .orbit-blink { animation: orbit-blink 1.4s ease-in-out infinite; }
    .orbit-block-in { animation: orbit-rise .28s ease-out both; }
    .orbit-stamp { rotate: -8deg; animation: orbit-stamp-in .25s ease-out both; }
    /* Panel entrance: an iOS-sheet spring (slight overshoot ease). */
    .orbit-panel-in { animation: orbit-panel-in .45s cubic-bezier(.32,1.25,.42,1) both; }
    .orbit-dot { animation: orbit-dot 1.2s ease-in-out infinite; }
    /* Living glass: mouse-following specular sheen (reads --mx/--my set by JS). */
    .orbit-sheen {
      background: radial-gradient(340px circle at var(--mx, 60%) var(--my, 0%), rgba(255,255,255,0.26), transparent 65%);
    }
    /* Living glass: two brand-tinted aurora blobs drifting slowly behind content. */
    .orbit-aurora { overflow: hidden; }
    .orbit-aurora::before, .orbit-aurora::after { content: ''; position: absolute; border-radius: 9999px; filter: blur(42px); }
    .orbit-aurora::before {
      width: 260px; height: 260px; left: -80px; top: 18%;
      background: rgba(22,138,173,0.14);
      animation: orbit-aurora-a 16s ease-in-out infinite alternate;
    }
    .orbit-aurora::after {
      width: 220px; height: 220px; right: -70px; bottom: 8%;
      background: rgba(118,200,147,0.13);
      animation: orbit-aurora-b 21s ease-in-out infinite alternate;
    }
    /* Hero satellites: glow + a comet trail (conic arc masked to a thin ring,
       rotating with the same wrapper so it always trails the dot). */
    .orbit-sat-glow { box-shadow: 0 0 10px 2px rgba(22,138,173,0.45); }
    .orbit-sat-glow-accent { box-shadow: 0 0 8px 2px rgba(118,200,147,0.5); }
    .orbit-trail, .orbit-trail-accent {
      border-radius: 9999px;
      -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 1.5px));
      mask: radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 1.5px));
    }
    .orbit-trail { background: conic-gradient(from 0deg, transparent 0deg 290deg, rgba(22,138,173,0.45) 360deg); }
    .orbit-trail-accent { background: conic-gradient(from 0deg, rgba(118,200,147,0.4) 0deg, transparent 70deg 360deg); }
    @media (prefers-reduced-motion: reduce) {
      .orbit-spin, .orbit-spin-rev, .orbit-spin-fast, .orbit-spin-rev-fast,
      .orbit-pulse, .orbit-blink,
      .orbit-block-in, .orbit-stamp, .orbit-panel-in, .orbit-dot,
      .orbit-b-float, .orbit-b-shadow, .orbit-b-eye, .orbit-b-pupil,
      .orbit-b-dot, .orbit-b-spark, .mood-sad .orbit-b-tear, .mood-excited .orbit-b-arm-r,
      .mood-thinking .orbit-b-tip, .mood-waiting .orbit-b-tip,
      .mood-idle .orbit-b-m-rest, .mood-idle .orbit-b-m-smile,
      .orbit-aurora::before, .orbit-aurora::after { animation: none !important; }
      /* with the idle mouth cycle frozen, pin the resting mouth on */
      .mood-idle .orbit-b-m-rest { opacity: 1; }
      .orbit-trail, .orbit-trail-accent, .orbit-sheen { display: none; }
    }
  `}</style>
)

export default AssistantWidget
