import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertTriangle, BarChart3, Check, ChevronDown, ChevronRight, Compass, Copy, CornerUpRight, Info, Plus, XCircle } from 'lucide-react'
import { Bar, BarChart, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Block, BlockHandlers, ChartPoint, RecordCardBlock, Tone } from './types'
import { chipClass, textClass } from './tone'

// Card spine (left rail) color per accent tone — the one-glance clinical scan.
const railClass: Record<string, string> = {
  error: 'border-l-danger-500',
  warning: 'border-l-warning-500',
  info: 'border-l-sky-400',
  success: 'border-l-accent-500',
  neutral: 'border-l-gray-200',
}

// "Dev User" → "DU" for the assignee chip.
const initialsOf = (name: string): string =>
  name.trim().split(/\s+/).slice(0, 2).map((w) => (w[0] || '').toUpperCase()).join('') || '—'

/** Glyph language for action links: the icon hints what tapping will do. */
export const actionIcon = (labelAndMessage: string) => {
  const t = labelAndMessage.toLowerCase()
  if (/(create|add |new |start a)/.test(t)) return Plus
  if (/(tour|walk me|show me around)/.test(t)) return Compass
  if (/(summari|overview|attention|breakdown|how many)/.test(t)) return BarChart3
  if (/(open|go to|take me|show )/.test(t)) return CornerUpRight
  return ChevronRight
}

/** Hover copy button for prose cards — grabs the raw markdown. */
const CopyButton: React.FC<{ text: string }> = ({ text }) => {
  const [copied, setCopied] = React.useState(false)
  const onCopy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      /* clipboard unavailable — quietly do nothing */
    }
  }
  const Icon = copied ? Check : Copy
  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label={copied ? 'Copied' : 'Copy text'}
      title={copied ? 'Copied' : 'Copy'}
      className={`absolute right-1.5 top-1.5 rounded p-1 transition-opacity focus-visible:opacity-100 motion-reduce:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 ${
        copied ? 'opacity-100 text-accent-600' : 'opacity-0 group-hover/card:opacity-100 text-gray-300 hover:bg-gray-100 hover:text-gray-600'
      }`}
    >
      <Icon size={13} />
    </button>
  )
}

/** Line-by-line reveal for streamed prose (slices at newlines so markdown
 *  structures stay intact). Instant under prefers-reduced-motion. */
const useLineReveal = (text: string): string => {
  const lines = React.useMemo(() => text.split('\n'), [text])
  const [shown, setShown] = React.useState(() => (prefersReducedMotion() ? Number.MAX_SAFE_INTEGER : 1))
  React.useEffect(() => {
    if (shown >= lines.length) return
    const step = Math.max(40, Math.min(90, 900 / lines.length))
    const t = setTimeout(() => setShown((s) => s + 1), step)
    return () => clearTimeout(t)
  }, [shown, lines.length])
  return lines.slice(0, Math.max(1, shown)).join('\n')
}

// ---------------------------------------------------------------------------
// "Paper Brief" direction: editorial, light, document-like. Whitespace and
// dotted separators instead of boxes; serif headings; large tabular numbers
// with teal underlines; underlined text actions instead of chip pills. Same
// block contract and behavior as before — presentation only.
// ---------------------------------------------------------------------------

// Flatten markdown children to a string ONLY when they're plain text — used by
// the semantic inline renderers below to inspect what the model emphasized.
const onlyText = (children: React.ReactNode): string | null => {
  const arr = React.Children.toArray(children)
  return arr.every((c) => typeof c === 'string' || typeof c === 'number') ? arr.join('') : null
}

// Bold status phrases → tone chips (one-glance clinical triage, content unchanged).
// Matched at the START of the bold text so counts survive: "**At Risk (2 studies)**".
const STATUS_CHIPS: [RegExp, string][] = [
  [/^(at risk|critical|overdue|blocked|off track|delayed|behind|pending)/i, 'bg-warning-50 text-warning-700 ring-warning-500/25'],
  [/^(failed|error|escalated|rejected)/i, 'bg-danger-50 text-danger-700 ring-danger-500/25'],
  [/^(healthy|on track|on plan|completed|executed|active|ready|approved)/i, 'bg-accent-50 text-accent-700 ring-accent-500/25'],
]

// Semantic inline renderers: statuses become tone chips; italicized record
// codes (ONCOTRIA-301) become mono badges; everything else stays plain markdown.
const mdComponents = {
  strong: ({ children }: { children?: React.ReactNode }) => {
    const txt = onlyText(children)
    const hit = txt && STATUS_CHIPS.find(([re]) => re.test(txt.trim()))
    if (hit)
      return (
        <span className={`mx-px inline-block rounded-full px-2 py-px text-[11px] font-semibold leading-4 ring-1 ${hit[1]}`}>
          {children}
        </span>
      )
    return <strong>{children}</strong>
  },
  em: ({ children }: { children?: React.ReactNode }) => {
    const txt = onlyText(children)
    if (txt && /^[A-Z][A-Z0-9]*-\d+[A-Z0-9]*$/.test(txt.trim()))
      return (
        <span className="mx-px inline-block rounded bg-brand-50 px-1.5 py-px font-mono text-[11.5px] font-medium leading-4 tracking-tight text-brand-700 ring-1 ring-brand-500/20">
          {txt.trim()}
        </span>
      )
    return <em>{children}</em>
  },
}

// Shared markdown styling (typography plugin isn't enabled, so `prose` is a
// no-op here — these scoped rules ARE the markdown styles). Lists are
// depth-aware: brand markers at the top level, quieter markers below, and the
// third level trades bullets for a thin brand rail so deep nests stay readable.
const Markdown: React.FC<{ children: string }> = ({ children }) => (
  <div
    className={
      'text-ui-body text-gray-800 leading-relaxed ' +
      '[&_p]:my-1.5 ' +
      '[&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-4 ' +
      '[&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:my-1 ' +
      '[&_li]:marker:text-brand-400 [&_li_li]:marker:text-brand-300 [&_li]:pl-0.5 ' +
      '[&_ul_ul]:my-1 [&_ul_ul]:pl-3.5 ' +
      '[&_ul_ul_ul]:list-none [&_ul_ul_ul]:border-l-2 [&_ul_ul_ul]:border-brand-500/15 [&_ul_ul_ul]:pl-2.5 ' +
      '[&_h1]:font-serif [&_h1]:text-lg [&_h1]:text-gray-900 [&_h1]:mt-3 [&_h1]:mb-1 ' +
      '[&_h2]:font-serif [&_h2]:text-base [&_h2]:text-gray-900 [&_h2]:mt-3 [&_h2]:mb-1 ' +
      '[&_h3]:font-serif [&_h3]:text-ui-h2 [&_h3]:text-gray-900 [&_h3]:mt-2 [&_h3]:mb-1 ' +
      '[&_strong]:font-semibold [&_strong]:text-gray-900 ' +
      '[&_a]:text-brand-600 [&_a]:underline [&_a]:underline-offset-2 ' +
      '[&_code]:rounded [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[12px] ' +
      '[&_blockquote]:border-l-2 [&_blockquote]:border-brand-200 [&_blockquote]:pl-3 [&_blockquote]:text-gray-600 ' +
      '[&_hr]:my-2.5 [&_hr]:border-0 [&_hr]:border-t [&_hr]:border-dotted [&_hr]:border-gray-300 ' +
      '[&_table]:my-2 [&_table]:w-full [&_table]:border-collapse [&_table]:text-ui-body-sm ' +
      '[&_thead_th]:border-b [&_thead_th]:border-gray-200 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left ' +
      '[&_th]:text-ui-caption [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-wide [&_th]:text-gray-400 ' +
      '[&_td]:border-b [&_td]:border-gray-100 [&_td]:px-2 [&_td]:py-1 [&_td]:align-top ' +
      '[&_tbody_tr:last-child_td]:border-b-0'
    }
  >
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
      {children}
    </ReactMarkdown>
  </div>
)

// Orbit's prose rides a glass card floating on the panel's brand wash.
// Reveals line-by-line as it lands; hover shows a copy button. Long answers
// clamp behind a fade + "Show more" so one reply can't swallow the panel.
const TEXT_CLAMP_PX = 360

const TextBlock: React.FC<{ text: string }> = ({ text }) => {
  const revealed = useLineReveal(text)
  const [expanded, setExpanded] = React.useState(false)
  const [overflowing, setOverflowing] = React.useState(false)
  const bodyRef = React.useRef<HTMLDivElement>(null)
  React.useEffect(() => {
    const el = bodyRef.current
    // +60 hysteresis: don't clamp for one bullet's worth of extra height.
    if (el) setOverflowing(el.scrollHeight > TEXT_CLAMP_PX + 60)
  }, [revealed])
  const clamped = overflowing && !expanded
  return (
    <div className="group/card relative rounded-lg rounded-bl-sm bg-white/70 backdrop-blur-md px-3 py-2 shadow-card ring-1 ring-white/60">
      <CopyButton text={text} />
      <div ref={bodyRef} className={clamped ? 'overflow-hidden' : undefined} style={clamped ? { maxHeight: TEXT_CLAMP_PX } : undefined}>
        <Markdown>{revealed}</Markdown>
      </div>
      {clamped && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 rounded-b-lg bg-gradient-to-t from-white via-white/80 to-transparent" />
      )}
      {overflowing && (
        <div className={`flex justify-center ${clamped ? 'absolute inset-x-0 bottom-1.5' : 'mt-1'}`}>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1 rounded-full bg-white/80 px-2.5 py-0.5 text-ui-caption font-medium text-brand-700 ring-1 ring-white/70 shadow-sm backdrop-blur-sm transition hover:bg-white active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
          >
            <ChevronDown size={12} className={expanded ? 'rotate-180 transition-transform' : 'transition-transform'} />
            {expanded ? 'Show less' : 'Show more'}
          </button>
        </div>
      )}
    </div>
  )
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Numeric values count up briefly on mount (tabular-nums, so nothing shifts).
 *  Strings, zeros, and reduced-motion users get the final value immediately. */
const CountUp: React.FC<{ value: string | number }> = ({ value }) => {
  const [display, setDisplay] = React.useState<string | number>(() => {
    const n = typeof value === 'number' ? value : Number.NaN
    return Number.isFinite(n) && n > 0 && !prefersReducedMotion() ? 0 : value
  })
  React.useEffect(() => {
    const target = typeof value === 'number' ? value : Number.NaN
    if (!Number.isFinite(target) || target <= 0 || prefersReducedMotion()) {
      setDisplay(value)
      return
    }
    let raf = 0
    const t0 = performance.now()
    const duration = 350
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration)
      setDisplay(Math.round(target * (1 - Math.pow(1 - p, 3)))) // ease-out cubic
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value])
  return <>{display}</>
}

// Large tabular numbers, small labels beneath, a short teal rule under each —
// the brief's "figures" row. A stat carrying a `message` is a drill-in: tapping
// it sends that message as the next turn (same trust path as choice chips).
const StatRow: React.FC<{ stats: { label: string; value: string | number; tone?: Tone; message?: string }[]; h: BlockHandlers }> = ({
  stats,
  h,
}) => (
  <div className="flex flex-wrap gap-x-7 gap-y-2 rounded-lg bg-white/70 backdrop-blur-md px-3 py-2 shadow-card ring-1 ring-white/60">
    {stats.map((s, i) => {
      const body = (
        <>
          <div className={`text-xl font-semibold tabular-nums leading-6 ${s.tone && s.tone !== 'neutral' ? textClass(s.tone) : 'text-gray-900'}`}>
            <CountUp value={s.value} />
          </div>
          <div className="mt-0.5 text-ui-caption uppercase tracking-wide text-gray-400">{s.label}</div>
          <div
            className={`mt-1 h-0.5 w-6 rounded-full transition-all ${
              s.tone === 'error' ? 'bg-danger-500' : s.tone === 'warning' ? 'bg-warning-500' : 'bg-brand-500'
            } ${s.message ? 'group-hover/stat:w-10' : ''}`}
          />
        </>
      )
      return s.message ? (
        <button
          key={i}
          type="button"
          disabled={h.busy}
          onClick={() => h.onSend(s.message as string)}
          title={s.message}
          className="group/stat min-w-[3rem] rounded-md px-1 -mx-1 text-left transition-colors hover:bg-brand-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 disabled:opacity-60"
        >
          {body}
        </button>
      ) : (
        <div key={i} className="min-w-[3rem]">
          {body}
        </div>
      )
    })}
  </div>
)

// Grouped counts as quiet inline text lines: "Pending 4 · In progress 3 · Done 3".
// Items with a `message` are tappable drill-ins.
const Breakdown: React.FC<{
  groups: { title: string; items: { label: string; value: string | number; tone?: Tone; message?: string }[] }[]
  h: BlockHandlers
}> = ({ groups, h }) => {
  // Bars animate from 0 to their share on mount (transition-driven; instant
  // under reduced motion because the initial state is already the final width).
  const [armed, setArmed] = React.useState(prefersReducedMotion())
  React.useEffect(() => {
    if (armed) return
    const raf = requestAnimationFrame(() => setArmed(true))
    return () => cancelAnimationFrame(raf)
  }, [armed])
  const barTone: Record<string, string> = {
    error: 'bg-danger-500',
    warning: 'bg-warning-500',
    info: 'bg-sky-400',
    success: 'bg-accent-500',
    neutral: 'bg-brand-300',
  }
  return (
    <div className="space-y-2.5 rounded-lg bg-white/70 backdrop-blur-md px-3 py-2 shadow-card ring-1 ring-white/60">
      {groups.map((g, gi) => {
        const total = g.items.reduce((a, it) => a + (typeof it.value === 'number' ? it.value : 0), 0) || 1
        return (
          <div key={gi}>
            <div className="text-ui-caption font-semibold uppercase tracking-wide text-gray-400">{g.title}</div>
            <div className="mt-1 space-y-1">
              {g.items.map((it, i) => {
                const pct = typeof it.value === 'number' ? Math.round((it.value / total) * 100) : 0
                const row = (
                  <>
                    <span className="w-28 shrink-0 truncate text-left text-ui-body-sm text-gray-600">{it.label}</span>
                    <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-gray-100">
                      <span
                        className={`block h-full rounded-full transition-[width] duration-500 ease-out ${barTone[it.tone || 'neutral'] || barTone.neutral}`}
                        style={{ width: armed ? `${pct}%` : '0%' }}
                      />
                    </span>
                    <span className={`w-6 shrink-0 text-right text-ui-body-sm font-semibold tabular-nums ${it.tone && it.tone !== 'neutral' ? textClass(it.tone) : 'text-gray-900'}`}>
                      {it.value}
                    </span>
                  </>
                )
                return it.message ? (
                  <button
                    key={i}
                    type="button"
                    disabled={h.busy}
                    onClick={() => h.onSend(it.message as string)}
                    title={it.message}
                    className="flex w-full items-center gap-2 rounded-md px-1 -mx-1 py-0.5 transition-colors hover:bg-brand-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 disabled:opacity-60"
                  >
                    {row}
                  </button>
                ) : (
                  <div key={i} className="flex w-full items-center gap-2 py-0.5">
                    {row}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** One meta entry, rendered as data-ink instead of prose: Due/Overdue → tone
 *  pill; Assignee → initials chip + name; everything else → label: value. */
const MetaEntry: React.FC<{ label: string; value: string; tone?: Tone }> = ({ label, value, tone }) => {
  if (label === 'Due' || label === 'Overdue') {
    return (
      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-px text-ui-caption font-medium ${chipClass(tone)}`}>
        {label} {value}
      </span>
    )
  }
  if (label === 'Assignee') {
    return (
      <span className="inline-flex items-center gap-1.5 text-ui-body-sm text-gray-600">
        <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-brand-50 text-[9px] font-bold text-brand-700 ring-1 ring-brand-100">
          {initialsOf(value)}
        </span>
        {value}
      </span>
    )
  }
  return (
    <span className="text-ui-body-sm">
      <span className="text-gray-400">{label}: </span>
      <span className={tone ? textClass(tone) + ' font-medium' : 'text-gray-700'}>{value}</span>
    </span>
  )
}

const RecordCard: React.FC<{ block: RecordCardBlock; h: BlockHandlers; bare?: boolean }> = ({ block, h, bare }) => {
  const clickable = Boolean(block.id)
  // Inline expand: full subtitle + stacked meta without leaving the chat.
  // Purely local presentation state — the whole-card click still opens the record.
  const [expanded, setExpanded] = React.useState(false)
  const expandable = Boolean(block.subtitle || (block.meta && block.meta.length > 0))
  const rail = railClass[block.accent || block.status?.tone || 'neutral'] || railClass.neutral
  return (
    <div
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => h.onOpenRecord(block.record_type, block.id) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                h.onOpenRecord(block.record_type, block.id)
              }
            }
          : undefined
      }
      className={`group border-l-[3px] ${rail} py-2 pl-3 pr-2 text-left transition-colors ${
        bare ? 'rounded-md bg-white/70 backdrop-blur-md shadow-card ring-1 ring-white/60' : 'bg-transparent'
      } ${
        clickable
          ? 'cursor-pointer hover:bg-brand-50/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40'
          : ''
      }`}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
            {block.flag?.label && (
              <span className={`rounded border px-1.5 py-px text-[10px] font-bold uppercase tracking-wider ${chipClass(block.flag.tone)}`}>
                {block.flag.label}
              </span>
            )}
            <span className="text-ui-caption uppercase tracking-wide text-gray-400">
              {block.record_type}
              {block.status?.label && (
                <>
                  <span className="text-gray-300"> · </span>
                  <span className={`font-semibold ${block.status.tone && block.status.tone !== 'neutral' ? textClass(block.status.tone) : 'text-gray-500'}`}>
                    {block.status.label}
                  </span>
                </>
              )}
            </span>
          </div>
          <div className={`mt-0.5 font-serif text-[15px] font-medium leading-5 text-gray-900 ${expanded ? '' : 'truncate'}`}>
            {block.title}
          </div>
          {block.subtitle && (
            <div className={`mt-0.5 text-ui-body-sm text-gray-500 ${expanded ? 'whitespace-pre-wrap' : 'line-clamp-1'}`}>
              {block.subtitle}
            </div>
          )}
          {block.meta && block.meta.length > 0 && (
            expanded ? (
              <dl className="mt-1.5 space-y-0.5 text-ui-body-sm">
                {block.meta.map((m, i) => (
                  <div key={i} className="flex gap-2">
                    <dt className="w-20 shrink-0 text-gray-400">{m.label}</dt>
                    <dd className={m.tone ? textClass(m.tone) + ' font-medium' : 'text-gray-700'}>{m.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                {block.meta.map((m, i) => (
                  <MetaEntry key={i} label={m.label} value={m.value} tone={m.tone} />
                ))}
              </div>
            )
          )}
        </div>
        {expandable && (
          <button
            type="button"
            aria-label={expanded ? 'Collapse details' : 'Expand details'}
            aria-expanded={expanded}
            onClick={(e) => {
              e.stopPropagation()
              setExpanded((v) => !v)
            }}
            onKeyDown={(e) => e.stopPropagation()}
            className="mt-0.5 shrink-0 rounded p-0.5 text-gray-300 transition-transform hover:text-brand-600 hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
          >
            <ChevronDown size={15} className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
          </button>
        )}
        {clickable && <ChevronRight size={15} className="mt-1 shrink-0 text-gray-300 transition-colors group-hover:text-brand-500" />}
      </div>

      {block.actions && block.actions.length > 0 && (
        // Quick actions surface on hover / keyboard focus / expand — quieter brief,
        // same guarded message path when used.
        <div
          className={`mt-1.5 flex flex-wrap gap-x-4 transition-opacity ${
            expanded ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100 motion-reduce:opacity-100'
          }`}
        >
          {(expanded ? block.actions : block.actions.slice(0, 2)).map((a, i) => (
            <button
              key={i}
              type="button"
              disabled={h.busy}
              onClick={(e) => {
                e.stopPropagation()
                h.onSend(a.message)
              }}
              className="text-ui-body-sm font-medium text-brand-600 underline decoration-brand-300 underline-offset-2 hover:text-brand-700 hover:decoration-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 rounded-sm disabled:opacity-40"
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// The list is one contained instrument panel — hairline ring, crisp dividers —
// so records read as rows of a console, not paragraphs of a page.
const RecordList: React.FC<{ records: RecordCardBlock[]; h: BlockHandlers }> = ({ records, h }) => (
  <div className="overflow-hidden rounded-lg bg-white/70 backdrop-blur-md shadow-card ring-1 ring-white/60 divide-y divide-gray-100">
    {records.map((r, i) => (
      <RecordCard key={r.id || i} block={r} h={h} />
    ))}
  </div>
)

// Underlined text actions with a trailing arrow — the brief's "read on" links.
const ChoiceChips: React.FC<{ question?: string | null; options: { label: string; message: string }[]; h: BlockHandlers }> = ({
  question,
  options,
  h,
}) => (
  <div className="px-1 py-0.5">
    {question && <div className="mb-1 text-ui-body text-gray-700">{question}</div>}
    <div className="flex flex-wrap gap-x-5 gap-y-1.5">
      {options.map((o, i) => {
        const Icon = actionIcon(`${o.label} ${o.message}`)
        return (
          <button
            key={i}
            type="button"
            disabled={h.busy}
            onClick={() => h.onSend(o.message)}
            className="inline-flex items-center gap-1 py-0.5 text-ui-body font-medium text-brand-600 underline decoration-brand-300 underline-offset-4 hover:text-brand-700 hover:decoration-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 rounded-sm disabled:opacity-40"
          >
            <Icon size={13} className="mt-px shrink-0" />
            {o.label}
          </button>
        )
      })}
    </div>
  </div>
)

// The "action slip": the one deliberately bordered element on the page, so a
// pending write is unmissable against the quiet brief. Regulated is stronger.
const ConfirmationCard: React.FC<{
  token: string
  risk: string
  description: string
  expiresIn?: number
  h: BlockHandlers
}> = ({ token, risk, description, expiresIn, h }) => {
  const resolved = h.resolvedTokens.has(token)
  const decision = h.decisions?.get(token) // true=approved, false=cancelled, undefined=unknown
  const regulated = risk === 'regulated'
  // Approval-window countdown — display only; the authoritative timeout lives
  // server-side. At 0 the buttons go away and the card says so honestly.
  const [secondsLeft, setSecondsLeft] = React.useState<number | null>(
    typeof expiresIn === 'number' && expiresIn > 0 ? expiresIn : null,
  )
  React.useEffect(() => {
    if (resolved || secondsLeft === null || secondsLeft <= 0) return
    const t = setInterval(() => setSecondsLeft((v) => (v === null ? v : Math.max(0, v - 1))), 1000)
    return () => clearInterval(t)
  }, [resolved, secondsLeft === null, secondsLeft === 0]) // eslint-disable-line react-hooks/exhaustive-deps
  const expired = !resolved && secondsLeft === 0
  const mmss = secondsLeft !== null ? `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')}` : null
  return (
    <div
      className={`relative rounded-md border bg-white/75 backdrop-blur-md p-3 ${
        regulated ? 'border-amber-400 border-l-4 border-l-amber-500' : 'border-amber-300 border-l-4 border-l-amber-400'
      }`}
    >
      {/* The decision is "stamped" onto the slip — the regulated moment is felt. */}
      {resolved && decision === true && (
        <div className="orbit-stamp pointer-events-none absolute right-3 top-2 rounded border-2 border-accent-600 px-2 py-0.5 text-ui-caption font-bold uppercase tracking-widest text-accent-600">
          Approved ✓
        </div>
      )}
      <div className={`flex items-baseline gap-2 text-ui-caption font-semibold uppercase tracking-wide ${regulated ? 'text-amber-800' : 'text-amber-700'}`}>
        <span className="flex-1">{regulated ? 'Regulated action — your approval required' : 'Confirm action'}</span>
        {!resolved && !expired && mmss && (
          <span className={`shrink-0 normal-case tabular-nums ${secondsLeft !== null && secondsLeft <= 30 ? 'text-danger-600' : 'text-amber-600/80'}`}>
            expires in {mmss}
          </span>
        )}
      </div>
      <p className={`mt-1 mb-3 text-ui-body ${(resolved && decision === false) || expired ? 'text-gray-400 line-through' : 'text-gray-800'}`}>
        {description}
      </p>
      {resolved ? (
        <div className="text-ui-caption font-medium text-gray-500">
          {decision === true ? 'Approved — running it now.' : decision === false ? 'Cancelled — nothing was done.' : 'Handled.'}
        </div>
      ) : expired ? (
        <div className="text-ui-caption font-medium text-gray-500">Approval window expired — nothing was done. Ask again when you're ready.</div>
      ) : (
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => h.onDecide(token, true)}
            className="rounded-md bg-brand-500 px-4 py-1.5 text-ui-body font-medium text-white hover:bg-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
          >
            Approve
          </button>
          <button
            type="button"
            onClick={() => h.onDecide(token, false)}
            className="py-1.5 text-ui-body font-medium text-gray-600 underline decoration-gray-300 underline-offset-4 hover:text-gray-800 hover:decoration-gray-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 rounded-sm"
          >
            Cancel — do nothing
          </button>
        </div>
      )}
    </div>
  )
}

// ---- Real charts (the assistant's show_chart tool) ------------------------
// Brand-first palette: teal → green → deep blue, then lights; semantic tones
// override per point (warning = amber, error = red, …).
const CHART_TONE_HEX: Record<string, string> = {
  success: '#76C893',
  warning: '#F59E0B',
  error: '#EF4444',
  info: '#168AAD',
}
const CHART_SERIES_HEX = ['#168AAD', '#76C893', '#1E73BE', '#4BA8C5', '#A4D9B5', '#F59E0B', '#4A9FE8', '#5BA374']
const chartColor = (p: ChartPoint, i: number): string =>
  (p.tone && CHART_TONE_HEX[p.tone]) || CHART_SERIES_HEX[i % CHART_SERIES_HEX.length]

const AXIS_TICK = { fontSize: 11, fill: '#6B7280' }

const ChartBlockView: React.FC<{ kind?: string; title?: string | null; unit?: string | null; points: ChartPoint[] }> = ({
  kind,
  title,
  unit,
  points,
}) => {
  const data = (points || []).filter((p) => p && typeof p.value === 'number' && Number.isFinite(p.value))
  if (data.length === 0) return null
  const total = data.reduce((a, p) => a + p.value, 0)
  const animate = !prefersReducedMotion()
  const fmt = (v: number) => `${Number(v).toLocaleString()}${unit ? ` ${unit}` : ''}`

  // Small glass tooltip matching the console material.
  const Tip = ({ active, payload }: { active?: boolean; payload?: any[] }) =>
    active && payload?.length ? (
      <div className="rounded-lg bg-white/90 px-2.5 py-1.5 text-ui-caption text-gray-600 shadow-card ring-1 ring-white/70 backdrop-blur-sm">
        <span className="font-semibold text-gray-900">{payload[0].payload.label}</span> · {fmt(payload[0].value)}
      </div>
    ) : null

  return (
    <div className="rounded-lg bg-white/70 backdrop-blur-md px-3 py-2.5 shadow-card ring-1 ring-white/60">
      {title && (
        <div className="mb-1.5 flex items-baseline gap-2">
          <span className="font-serif text-ui-h2 text-gray-900">{title}</span>
          <span className="ml-auto text-ui-caption tabular-nums text-gray-400">total {fmt(total)}</span>
        </div>
      )}
      {kind === 'donut' ? (
        <div className="flex items-center gap-3">
          <div className="h-[170px] w-[55%] min-w-[150px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="label" innerRadius={44} outerRadius={70} paddingAngle={2} strokeWidth={0} isAnimationActive={animate}>
                  {data.map((p, i) => (
                    <Cell key={i} fill={chartColor(p, i)} />
                  ))}
                </Pie>
                <Tooltip content={<Tip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="min-w-0 flex-1 space-y-1.5">
            {data.map((p, i) => (
              <div key={i} className="flex items-center gap-1.5 text-ui-caption text-gray-600">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: chartColor(p, i) }} />
                <span className="min-w-0 flex-1 truncate">{p.label}</span>
                <span className="font-medium tabular-nums text-gray-900">{Number(p.value).toLocaleString()}</span>
                {total > 0 && <span className="tabular-nums text-gray-400">{Math.round((p.value / total) * 100)}%</span>}
              </div>
            ))}
          </div>
        </div>
      ) : kind === 'line' ? (
        <div className="h-[190px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="label" tick={AXIS_TICK} axisLine={{ stroke: '#E5E7EB' }} tickLine={false} />
              <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={38} />
              <Tooltip content={<Tip />} cursor={{ stroke: 'rgba(22,138,173,0.25)' }} />
              <Line type="monotone" dataKey="value" stroke="#168AAD" strokeWidth={2.5} dot={{ r: 3, fill: '#168AAD', strokeWidth: 0 }} activeDot={{ r: 4.5 }} isAnimationActive={animate} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-[190px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }} barCategoryGap="28%">
              <XAxis dataKey="label" tick={AXIS_TICK} axisLine={{ stroke: '#E5E7EB' }} tickLine={false} interval={0} />
              <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={38} />
              <Tooltip content={<Tip />} cursor={{ fill: 'rgba(22,138,173,0.06)' }} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} isAnimationActive={animate}>
                {data.map((p, i) => (
                  <Cell key={i} fill={chartColor(p, i)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {unit && <div className="mt-1 text-right text-ui-caption text-gray-400">{unit}</div>}
    </div>
  )
}

const HelpAnswer: React.FC<{ markdown: string; offer?: { label: string; message: string } | null; h: BlockHandlers }> = ({
  markdown,
  offer,
  h,
}) => {
  const OfferIcon = offer ? actionIcon(`${offer.label} ${offer.message}`) : ChevronRight
  return (
    <div className="group/card relative rounded-lg border-l-[3px] border-l-brand-400 bg-white/70 backdrop-blur-md px-3 py-2 shadow-card ring-1 ring-white/60">
      <CopyButton text={markdown} />
      <Markdown>{markdown}</Markdown>
      {offer && (
        <button
          type="button"
          disabled={h.busy}
          onClick={() => h.onSend(offer.message)}
          className="mt-2 inline-flex items-center gap-1 py-0.5 text-ui-body font-medium text-brand-600 underline decoration-brand-300 underline-offset-4 hover:text-brand-700 hover:decoration-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 rounded-sm disabled:opacity-40"
        >
          <OfferIcon size={14} className="shrink-0" />
          {offer.label}
        </button>
      )}
    </div>
  )
}

const NoticeBlock: React.FC<{ kind: 'info' | 'warning' | 'error'; message: string }> = ({ kind, message }) => {
  const cfg = {
    info: { cls: 'border-l-sky-400 bg-sky-50/80 text-sky-900 ring-sky-100', icon: 'text-sky-500', Icon: Info },
    warning: { cls: 'border-l-yellow-400 bg-yellow-50/80 text-yellow-900 ring-yellow-100', icon: 'text-yellow-500', Icon: AlertTriangle },
    error: { cls: 'border-l-red-400 bg-red-50/80 text-red-900 ring-red-100', icon: 'text-red-500', Icon: XCircle },
  }[kind] || { cls: 'border-l-gray-300 bg-gray-50 text-gray-700 ring-gray-100', icon: 'text-gray-400', Icon: Info }
  const { cls, icon, Icon } = cfg
  return (
    <div className={`flex items-start gap-2 rounded-lg border-l-[3px] ${cls} px-3 py-2 text-ui-body ring-1`}>
      <Icon size={15} className={`mt-0.5 shrink-0 ${icon}`} />
      <span>{message}</span>
    </div>
  )
}

/** Registry: block type → renderer. Adding a type is one entry here. */
export const BlockRenderer: React.FC<{ block: Block; h: BlockHandlers }> = ({ block, h }) => {
  switch (block.type) {
    case 'text':
      return <TextBlock text={(block as any).text || ''} />
    case 'stat_row':
      return <StatRow stats={(block as any).stats || []} h={h} />
    case 'breakdown':
      return <Breakdown groups={(block as any).groups || []} h={h} />
    case 'record_card':
      return <RecordCard block={block as RecordCardBlock} h={h} bare />
    case 'chart':
      return (
        <ChartBlockView
          kind={(block as any).kind}
          title={(block as any).title}
          unit={(block as any).unit}
          points={(block as any).points || []}
        />
      )
    case 'record_list':
      return <RecordList records={(block as any).records || []} h={h} />
    case 'choice_chips':
      return <ChoiceChips question={(block as any).question} options={(block as any).options || []} h={h} />
    case 'confirmation':
      return (
        <ConfirmationCard
          token={(block as any).token}
          risk={(block as any).risk}
          description={(block as any).description}
          expiresIn={(block as any).expires_in}
          h={h}
        />
      )
    case 'help_answer':
      return <HelpAnswer markdown={(block as any).markdown || ''} offer={(block as any).offer} h={h} />
    case 'notice':
      return <NoticeBlock kind={(block as any).kind || 'info'} message={(block as any).message || ''} />
    default:
      // Unknown block type → never break; show whatever text we can.
      return <TextBlock text={(block as any).text || (block as any).message || '…'} />
  }
}
