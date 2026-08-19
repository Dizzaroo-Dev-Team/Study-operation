// Typed response-block protocol. The assistant streams these over SSE; the
// frontend renders each with a real component (see Blocks.tsx / registry).
// Unknown types fall back to text so nothing ever breaks.

export type Tone = 'success' | 'warning' | 'info' | 'error' | 'neutral'

export interface StatItem {
  label: string
  value: string | number
  tone?: Tone
  /** Optional drill-in: tapping the stat sends this as the next message
   *  (same trust path as choice chips — a normal turn, guards run). Backend
   *  attaches it where a sensible drill-in exists; absent → static display. */
  message?: string
}

export interface MetaItem {
  label: string
  value: string
  tone?: Tone
}

export interface RecordAction {
  label: string
  message: string // sent as the next turn when tapped (routes through the normal path)
}

export interface RecordCardBlock {
  type: 'record_card'
  record_type: string // task | study | agreement | conversation | …
  id?: string
  title: string
  subtitle?: string | null
  status?: { label: string; tone?: Tone } | null
  /** Prominent badge (severity / priority) — backend-parsed, e.g. "Critical". */
  flag?: { label: string; tone?: Tone } | null
  /** The card's spine (left rail) tone — severity first, else status. */
  accent?: Tone
  meta?: MetaItem[]
  actions?: RecordAction[]
}

export interface ChoiceOption {
  label: string
  message: string
}

export interface BreakdownGroup {
  title: string
  items: StatItem[]
}

export interface ChartPoint {
  label: string
  value: number
  tone?: Tone
}

export interface ChartBlock {
  type: 'chart'
  /** bar = compare categories, donut = parts of a whole, line = trend. */
  kind?: 'bar' | 'donut' | 'line'
  title?: string | null
  /** Unit label for values, e.g. "subjects". */
  unit?: string | null
  points: ChartPoint[]
}

export type Block =
  | { type: 'text'; text: string }
  | { type: 'stat_row'; stats: StatItem[] }
  | { type: 'breakdown'; groups: BreakdownGroup[] }
  | RecordCardBlock
  | ChartBlock
  | { type: 'record_list'; record_type: string; records: RecordCardBlock[] }
  | { type: 'choice_chips'; question?: string | null; options: ChoiceOption[] }
  | { type: 'confirmation'; token: string; command: string; risk: string; description: string; expires_in?: number }
  | { type: 'help_answer'; markdown: string; offer?: { label: string; message: string } | null }
  | { type: 'notice'; kind: 'info' | 'warning' | 'error'; message: string }
  | { type: string; [k: string]: unknown } // unknown → text fallback

export interface BlockHandlers {
  /** Send a message as the next turn (chips, quick actions, offers). */
  onSend: (message: string) => void
  /** Open a record's detail screen. */
  onOpenRecord: (recordType: string, id?: string) => void
  /** Approve/cancel a pending confirmation (existing gate + audit). */
  onDecide: (token: string, approve: boolean) => void
  /** Tokens already approved/cancelled (to disable the buttons). */
  resolvedTokens: Set<string>
  /** Which way each resolved token went (true = approved) — drives the
   *  stamped/struck presentation of the action slip. Presentation only. */
  decisions?: Map<string, boolean>
  /** True while a turn is streaming (disables interactions that start a new turn). */
  busy: boolean
}
