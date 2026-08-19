/**
 * VisitReportReviewPage — Google Docs-style reviewer interface
 *
 * Route: /monitoring/visits/:visitId/review?token=<uuid>
 *
 * Layout
 * ──────
 * Fixed top bar | Two-column body
 *   Left  → main report (scrolls with page, flex: 1)
 *   Right → sticky comment sidebar (position: sticky, independent scroll)
 *
 * Bi-directional sync
 * ───────────────────
 * • Click a highlighted span  → activates comment + sidebar card scrolls into view
 * • Click a sidebar card      → activates comment + document highlight scrolls into view
 * • Active highlight turns amber; default is light-yellow
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  useApproveVisitReport,
  usePatchVisitReportComment,
  usePostVisitReportComment,
  useRejectVisitReport,
  useVisitReportReview,
} from '@/lib/queries/useMonitoring'
import { MvrDynamicReviewReportBody } from './MvrDynamicReviewReportBody'
import type { MvrTemplateDto } from '@/components/mon/types/mvrTemplate'
import { resolveCommentedFieldKeysFromTemplate, encodeDomPathWithFieldKey } from '@/components/mon/utils/mvrReviewCommentNavigation'
import { LEGACY_VISIT_REPORT_FIELD_DEFS } from '@/components/mon/utils/legacyVisitReportFieldDefs'
import { SECTION4_CONSENT_QUESTIONS } from '@/components/mon/components/views/visit-detail/visitReportSection4Questions'
import { SECTION4_SITE_MANAGEMENT_QUESTIONS, isSection4SiteManagementQuestionVisible, type Section4SiteManagementQuestionId } from '@/components/mon/components/views/visit-detail/visitReportSection4SiteManagementQuestions'
import { SECTION10_ESSENTIAL_DOCS_QUESTIONS } from '@/components/mon/components/views/visit-detail/visitReportSection10EssentialDocsQuestions'
import { SECTION10_IMP_QUESTIONS } from '@/components/mon/components/views/visit-detail/visitReportSection10ImpQuestions'
import { SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS } from '@/components/mon/components/views/visit-detail/visitReportSection9BiologicalSampleQuestions'
import { questionCommentKey } from '@/components/mon/components/views/visit-detail/visitReportSectionQuestionComments'
import { SECTION6_SDV_QUESTIONS } from '@/components/mon/components/views/visit-detail/visitReportSection6SdvQuestions'
import {
  buildLegacyCustomFieldsByAnchor,
  buildSubmissionDataForReview,
  legacyCustomFieldsAfter,
  reportValuesForReview,
  shouldUseDynamicReviewBody,
} from '@/components/mon/utils/mvrReviewPayload'
import { MvrLegacyInsertedFieldsReview } from './MvrLegacyInsertedFieldsReview'

// ── API helpers ───────────────────────────────────────────────────────────────
interface ReviewComment {
  id: string
  highlighted_text: string
  dom_path: string
  start_offset: number
  end_offset: number
  comment_text: string
  author_reply?: string
  author_reply_at?: string | null
  created_at: string
  updated_at: string
}

interface ReviewData {
  payload: Record<string, unknown>
  comments: ReviewComment[]
  reviewer_email: string
  message: string
  /** Present when the CRA submitted a dynamic MVR (payload.templateId); schema for read-only render. */
  template?: MvrTemplateDto | null
  /** Per-site visit sequence for display (same as CRA "Visit #N"); omitted for legacy rows without a number. */
  site_visit_number?: number | null
}

interface RevisionBaseline {
  createdAt?: string
  payload?: Record<string, unknown>
  submissionData?: Record<string, unknown>
}

interface CommentChangeInfo {
  changed: boolean
  fieldKeys: string[]
  changedKeys: string[]
  label: string
  before: string
  after: string
}

// Network calls live in @/lib/queries/useMonitoring — hooks for the read +
// each mutation. Local helper types preserved below.

function pathVisitId(pathname: string): string | null {
  const m = pathname.match(/^\/monitoring\/visits\/([^/]+)\/review\/?$/)
  return m ? decodeURIComponent(m[1]) : null
}

/** Walk up from a selection node to the nearest field wrapper id (data-mvr-field). */
function nearestFieldKey(node: Node | null, root: HTMLElement): string | null {
  let cur: Node | null = node
  while (cur && cur !== root.parentNode) {
    if (cur instanceof HTMLElement) {
      const key = cur.getAttribute('data-mvr-field')
      if (key) return key
    }
    cur = cur.parentNode
  }
  return null
}

function domPath(node: Node, root: HTMLElement): string {
  const parts: string[] = []
  let cur: Node | null = node
  while (cur && cur !== root) {
    const parent: Node | null = cur.parentNode
    if (!parent) break
    const children = Array.from(parent.childNodes)
    const idx = children.indexOf(cur as ChildNode)
    parts.unshift(`${(cur as Element).tagName?.toLowerCase() ?? 'text'}[${idx}]`)
    cur = parent
  }
  return parts.join('>')
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function stableStringify(value: unknown): string {
  if (value == null) return ''
  if (typeof value !== 'object') return String(value)
  if (Array.isArray(value)) return `[${value.map((item) => stableStringify(item)).join(',')}]`
  try {
    const record = value as Record<string, unknown>
    return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(',')}}`
  } catch {
    return String(value)
  }
}

function valuesEqual(a: unknown, b: unknown): boolean {
  return stableStringify(a) === stableStringify(b)
}

function formatSignatureDateDisplay(value: unknown): string {
  const raw = String(value ?? '').trim()
  if (!raw) return '—'
  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (iso) return `${iso[3]}-${iso[2]}-${iso[1]}`
  return raw
}

function signatureReviewValue(payload: Record<string, unknown>, nameKey: string, legacyKey: string): string {
  const primary = String(payload[nameKey] ?? '').trim()
  if (primary) return primary
  return String(payload[legacyKey] ?? '').trim() || '—'
}

function previewValue(value: unknown): string {
  if (value == null || value === '') return 'Empty'
  const text = typeof value === 'string' ? value : stableStringify(value)
  return text.length > 140 ? `${text.slice(0, 140)}...` : text
}

function labelForField(key: string, reviewData: ReviewData | null): string {
  const dynamicField = reviewData?.template?.schema?.fields?.find((f) => f.id === key)
  if (dynamicField?.label) return dynamicField.label
  return LEGACY_VISIT_REPORT_FIELD_DEFS.find((f) => f.id === key)?.label ?? key
}

function resolveRevisionBaseline(payload: Record<string, unknown>): RevisionBaseline {
  return asRecord(payload.revisionBaseline) as RevisionBaseline
}

function reportValuesForComparison(reviewData: ReviewData | null): Record<string, unknown> {
  if (!reviewData) return {}
  return reportValuesForReview(reviewData.payload ?? {}, reviewData.template)
}

function baselineValuesForComparison(reviewData: ReviewData | null): Record<string, unknown> {
  const baseline = resolveRevisionBaseline(reviewData?.payload ?? {})
  const baselinePayload = asRecord(baseline.payload)
  if (Object.keys(baselinePayload).length > 0) {
    return reportValuesForReview(baselinePayload, reviewData?.template)
  }
  const baselineSubmission = asRecord(baseline.submissionData)
  if (Object.keys(baselineSubmission).length > 0) {
    return reportValuesForReview({ submissionData: baselineSubmission }, reviewData?.template)
  }
  return {}
}

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  primary:      '#1a56db',
  primaryLight: '#e8f0fe',
  text:         '#111827',
  textSub:      '#6b7280',
  border:       '#e5e7eb',
  bg:           '#ffffff',
  bgSubtle:     '#f9fafb',
  danger:       '#dc2626',
  success:      '#16a34a',
  radius:       '10px',
  shadow:       '0 1px 3px rgba(0,0,0,.08)',
  topbarH:      56,
} as const

const inputBase: React.CSSProperties = {
  width: '100%', padding: '8px 12px', fontSize: 13.5, lineHeight: 1.5,
  color: C.text, background: '#f3f4f6', border: `1.5px solid ${C.border}`,
  borderRadius: 8, outline: 'none', boxSizing: 'border-box', cursor: 'default',
}

const labelBase: React.CSSProperties = {
  display: 'block', fontSize: 12, fontWeight: 600, color: C.textSub,
  marginBottom: 5, letterSpacing: '.02em', textTransform: 'uppercase',
}

const grid: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(200px,1fr))', gap: '14px 18px',
}

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: C.bg, border: `1.5px solid ${C.border}`,
      borderRadius: C.radius, padding: '20px 22px',
      boxShadow: C.shadow, marginBottom: 14, ...style,
    }}>{children}</div>
  )
}

function ROInput({ value, label, full }: { value: unknown; label: string; full?: boolean }) {
  const display = value == null || value === '' ? '—' : String(value)
  return (
    <div style={{ gridColumn: full ? '1 / -1' : undefined }}>
      <label style={labelBase}>{label}</label>
      <div style={{ ...inputBase, minHeight: 38, display: 'flex', alignItems: 'center', color: display === '—' ? C.textSub : C.text }}>{display}</div>
    </div>
  )
}

function ROTextarea({ value, label, full }: { value: unknown; label: string; full?: boolean }) {
  const display = value == null || value === '' ? '—' : String(value)
  return (
    <div style={{ gridColumn: full ? '1 / -1' : undefined }}>
      <label style={labelBase}>{label}</label>
      <div style={{ ...inputBase, minHeight: 80, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: display === '—' ? C.textSub : C.text }}>{display}</div>
    </div>
  )
}

function SectionHeader({ num, title }: { num: string; title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 7, background: C.primaryLight, color: C.primary, fontSize: 11, fontWeight: 800, flexShrink: 0 }}>{num}</span>
      <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{title}</span>
    </div>
  )
}

type YNChoice = 'Yes' | 'No' | 'N/A' | ''
const ynColor = (v: YNChoice): React.CSSProperties => {
  if (v === 'Yes') return { borderColor: C.success, background: '#f0fdf4', color: '#14532d' }
  if (v === 'No')  return { borderColor: C.danger,  background: '#fef2f2', color: '#991b1b' }
  if (v === 'N/A') return { borderColor: C.border,  background: C.bgSubtle }
  return {}
}

function ROYNBadge({ value, label, num, comment }: { value: YNChoice; label: string; num: string; comment?: string }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: comment !== undefined ? 'minmax(0, 1fr) auto minmax(140px, 200px)' : '1fr auto',
      gap: 16, alignItems: 'center',
      padding: '10px 14px', borderRadius: 8, marginBottom: 4,
      border: `1.5px solid ${value ? (value === 'Yes' ? '#bbf7d0' : value === 'No' ? '#fecaca' : C.border) : C.border}`,
      background: value ? (value === 'Yes' ? '#f0fdf4' : value === 'No' ? '#fef2f2' : C.bgSubtle) : 'transparent',
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: C.primary, background: C.primaryLight, borderRadius: 5, padding: '2px 6px', flexShrink: 0, marginTop: 1 }}>{num}</span>
        <span style={{ fontSize: 13.5, color: C.text, lineHeight: 1.45 }}>{label}</span>
      </div>
      <span style={{ ...inputBase, width: 'auto', minWidth: 70, textAlign: 'center', fontWeight: 700, fontSize: 12.5, padding: '4px 10px', ...ynColor(value) }}>{value || '—'}</span>
      {comment !== undefined && (
        <div style={{ ...inputBase, minHeight: 34, fontSize: 12.5, color: comment ? C.text : C.textSub, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {comment || '—'}
        </div>
      )}
    </div>
  )
}

type Row = Record<string, string>
function ROTable({ cols, rows, label }: { cols: { key: string; label: string; type?: "yn" | "select" }[]; rows: Row[]; label: string }) {
  if (!rows || rows.length === 0) return null
  return (
    <div style={{ marginTop: 10, overflowX: 'auto' }}>
      <label style={labelBase}>{label}</label>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead>
          <tr>{cols.map((c) => (
            <th key={c.key} style={{ textAlign: 'left', padding: '8px 10px', background: C.bgSubtle, borderBottom: `2px solid ${C.border}`, borderTop: `1.5px solid ${C.border}`, color: C.textSub, fontWeight: 700, fontSize: 11, letterSpacing: '.04em', textTransform: 'uppercase' }}>{c.label}</th>
          ))}</tr>
        </thead>
        <tbody>{rows.map((row, i) => (
          <tr key={i} style={{ background: i % 2 === 0 ? C.bg : C.bgSubtle }}>
            {cols.map((c) => {
              const raw = row[c.key] ?? ''
              const display = c.type === 'yn'
                ? (raw === 'Yes' || raw === 'No' ? raw : '—')
                : (raw || '—')
              return (
                <td key={c.key} style={{ padding: '6px 10px', borderBottom: `1px solid ${C.border}`, color: C.text }}>
                  {c.type === 'yn' && (raw === 'Yes' || raw === 'No') ? (
                    <span style={{ ...inputBase, display: 'inline-block', width: 'auto', minWidth: 70, textAlign: 'center', fontWeight: 700, fontSize: 12.5, padding: '4px 10px', ...ynColor(raw as YNChoice) }}>{raw}</span>
                  ) : display}
                </td>
              )
            })}
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

// ── Annotation Popover (fixed, viewport-relative) ─────────────────────────────
interface SelectionCapture {
  text: string; domPath: string; fieldKey: string | null; startOffset: number; endOffset: number; x: number; y: number
}

function AnnotationPopover({ capture, onSave, onClose }: {
  capture: SelectionCapture; onSave: (text: string) => void; onClose: () => void
}) {
  const [commentText, setCommentText] = useState('')
  const [saving, setSaving] = useState(false)
  const handleSave = async () => {
    if (!commentText.trim()) return
    setSaving(true); await onSave(commentText.trim()); setSaving(false)
  }
  return (
    <div
      style={{
        position: 'fixed',
        left: Math.min(Math.max(capture.x, 8), window.innerWidth - 320),
        top: Math.min(capture.y + 8, window.innerHeight - 240),
        zIndex: 2000, width: 300, background: '#fff', borderRadius: 10,
        boxShadow: '0 8px 32px rgba(0,0,0,.2)', border: `1.5px solid ${C.border}`, padding: 14,
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div style={{ fontSize: 12, fontWeight: 600, color: C.textSub, marginBottom: 6 }}>Add comment on:</div>
      <div style={{ fontSize: 12, background: '#fef3c7', borderRadius: 6, padding: '4px 8px', marginBottom: 8, color: '#92400e', fontStyle: 'italic', wordBreak: 'break-word', maxHeight: 56, overflow: 'hidden' }}>
        "{capture.text.length > 80 ? capture.text.slice(0, 80) + '…' : capture.text}"
      </div>
      <textarea
        autoFocus placeholder="Type your comment…" value={commentText}
        onChange={(e) => setCommentText(e.target.value)}
        style={{ ...inputBase, background: '#fff', resize: 'vertical', minHeight: 70, cursor: 'text', marginBottom: 8 }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') { onClose() }
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { void handleSave() }
        }}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
        <button type="button" onClick={onClose}
          style={{ fontSize: 12, background: 'none', border: `1.5px solid ${C.border}`, borderRadius: 6, padding: '5px 12px', cursor: 'pointer', color: C.textSub }}>
          Cancel
        </button>
        <button type="button" onClick={() => void handleSave()} disabled={!commentText.trim() || saving}
          style={{ fontSize: 12, fontWeight: 700, border: 'none', borderRadius: 6, padding: '5px 14px', cursor: commentText.trim() ? 'pointer' : 'default', background: C.primary, color: '#fff', opacity: !commentText.trim() || saving ? 0.5 : 1 }}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  )
}

// ── Inline highlight mark ─────────────────────────────────────────────────────
function CommentMark({ comment, isActive, onActivate, registerRef }: {
  comment: ReviewComment
  isActive: boolean
  onActivate: () => void
  registerRef: (el: HTMLElement | null) => void
}) {
  return (
    <mark
      ref={registerRef}
      data-comment-id={comment.id}
      onClick={(e) => { e.stopPropagation(); onActivate() }}
      title={comment.comment_text}
      style={{
        background: isActive ? '#fbbf24' : '#fef9c3',
        borderBottom: `2px solid ${isActive ? '#d97706' : '#fde68a'}`,
        borderRadius: 2,
        padding: '1px 0',
        cursor: 'pointer',
        transition: 'background .15s, border-color .15s',
        boxShadow: isActive ? '0 0 0 2px rgba(251,191,36,.4)' : 'none',
      }}
    >
      {comment.highlighted_text}
    </mark>
  )
}

// ── Sidebar comment card ──────────────────────────────────────────────────────
void CommentMark

function CommentCard({ comment, isActive, onClick, onEdit, registerRef, changeInfo }: {
  comment: ReviewComment
  isActive: boolean
  onClick: () => void
  onEdit: (c: ReviewComment, newText: string) => void
  registerRef: (el: HTMLElement | null) => void
  changeInfo?: CommentChangeInfo
}) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(comment.comment_text)
  const [saving, setSaving] = useState(false)

  return (
    <div
      ref={registerRef}
      onClick={() => { if (!editing) onClick() }}
      style={{
        background: '#fff',
        border: `1.5px solid ${isActive ? '#fbbf24' : C.border}`,
        borderLeft: `3px solid ${isActive ? '#f59e0b' : '#d1d5db'}`,
        borderRadius: 8,
        padding: '12px 12px 10px',
        marginBottom: 8,
        cursor: editing ? 'default' : 'pointer',
        boxShadow: isActive ? '0 2px 12px rgba(251,191,36,.25)' : C.shadow,
        transition: 'border-color .15s, box-shadow .15s',
        transform: isActive ? 'translateX(-2px)' : 'none',
      }}
    >
      {/* Quote */}
      <div style={{
        fontSize: 11.5, color: '#92400e', background: '#fffbeb',
        borderRadius: 4, padding: '3px 7px', marginBottom: 7,
        fontStyle: 'italic', wordBreak: 'break-word',
        borderLeft: '2px solid #fcd34d',
      }}>
        "{comment.highlighted_text.length > 60 ? comment.highlighted_text.slice(0, 60) + '…' : comment.highlighted_text}"
      </div>

      {/* Comment body */}
      {editing ? (
        <>
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            autoFocus
            onClick={(e) => e.stopPropagation()}
            style={{ ...inputBase, background: '#fff', resize: 'vertical', minHeight: 64, cursor: 'text', fontSize: 12.5, marginBottom: 6 }}
          />
          <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end' }}>
            <button type="button" onClick={(e) => { e.stopPropagation(); setEditing(false); setEditText(comment.comment_text) }}
              style={{ fontSize: 11, padding: '3px 9px', border: `1.5px solid ${C.border}`, borderRadius: 5, background: C.bgSubtle, cursor: 'pointer' }}>
              Cancel
            </button>
            <button type="button" disabled={!editText.trim() || saving}
              onClick={async (e) => {
                e.stopPropagation()
                if (!editText.trim()) return
                setSaving(true); await onEdit(comment, editText.trim()); setSaving(false); setEditing(false)
              }}
              style={{ fontSize: 11, padding: '3px 10px', border: 'none', borderRadius: 5, background: C.primary, color: '#fff', cursor: 'pointer', opacity: saving ? 0.5 : 1 }}>
              {saving ? '…' : 'Save'}
            </button>
          </div>
        </>
      ) : (
        <>
          <div style={{ fontSize: 13, color: C.text, lineHeight: 1.5, marginBottom: 8, wordBreak: 'break-word' }}>
            {comment.comment_text}
          </div>
          {(comment.author_reply || '').trim() ? (
            <div style={{
              fontSize: 12, color: '#1e3a8a', background: '#eff6ff',
              border: '1px solid #bfdbfe', borderRadius: 6,
              padding: '8px 10px', marginBottom: 8, wordBreak: 'break-word',
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.04em', color: '#1d4ed8', marginBottom: 4 }}>
                Author reply
              </div>
              {comment.author_reply}
            </div>
          ) : null}
          {changeInfo && (
            <div style={{
              fontSize: 11.5,
              color: changeInfo.changed ? '#14532d' : '#6b7280',
              background: changeInfo.changed ? '#f0fdf4' : '#f9fafb',
              border: `1px solid ${changeInfo.changed ? '#bbf7d0' : C.border}`,
              borderRadius: 6,
              padding: '8px 10px',
              marginBottom: 8,
              wordBreak: 'break-word',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.04em', marginBottom: 4 }}>
                <span>{changeInfo.changed ? 'Changed by CRA' : 'No detected field change'}</span>
              </div>
              <div style={{ fontWeight: 700, marginBottom: changeInfo.changed ? 5 : 0 }}>
                {changeInfo.label}
              </div>
              {changeInfo.changed && (
                <div style={{ display: 'grid', gap: 4 }}>
                  <div><strong>Before:</strong> {changeInfo.before}</div>
                  <div><strong>Now:</strong> {changeInfo.after}</div>
                </div>
              )}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 10.5, color: C.textSub }}>
              {new Date(comment.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button type="button"
                onClick={(e) => { e.stopPropagation(); setEditing(true); setEditText(comment.comment_text) }}
                style={{ fontSize: 10.5, padding: '2px 8px', border: `1.5px solid ${C.border}`, borderRadius: 4, background: C.bgSubtle, cursor: 'pointer', color: C.textSub }}>
                Edit
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function VisitReportReviewPage() {
  const visitId = pathVisitId(window.location.pathname)
  const token = new URLSearchParams(window.location.search).get('token') ?? ''

  const [reviewData, setReviewData] = useState<ReviewData | null>(null)
  const [comments, setComments] = useState<ReviewComment[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeCommentId, setActiveCommentId] = useState<string | null>(null)

  // selection / annotation
  const [selection, setSelection] = useState<SelectionCapture | null>(null)
  const reportRef = useRef<HTMLDivElement>(null)

  // bi-directional scroll refs
  const highlightRefs = useRef<Map<string, HTMLElement>>(new Map())
  const commentCardRefs = useRef<Map<string, HTMLElement>>(new Map())
  const sidebarRef = useRef<HTMLDivElement>(null)

  const registerHighlight = useCallback((id: string, el: HTMLElement | null) => {
    if (el) highlightRefs.current.set(id, el)
    else highlightRefs.current.delete(id)
  }, [])

  const registerCard = useCallback((id: string, el: HTMLElement | null) => {
    if (el) commentCardRefs.current.set(id, el)
    else commentCardRefs.current.delete(id)
  }, [])

  // Scroll a comment card into view within the sidebar only (not the main page)
  const scrollCardInSidebar = useCallback((id: string) => {
    const card = commentCardRefs.current.get(id)
    const sidebar = sidebarRef.current
    if (!card || !sidebar) return
    const cardTop = card.offsetTop
    const target = cardTop - sidebar.clientHeight / 2 + card.clientHeight / 2
    sidebar.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
  }, [])

  // Click highlight → activate + scroll sidebar card into view (sidebar-only scroll)
  const handleHighlightClick = useCallback((id: string) => {
    setActiveCommentId(id)
    scrollCardInSidebar(id)
  }, [scrollCardInSidebar])

  // Click sidebar card → activate + scroll document highlight into view
  const handleCardClick = useCallback((id: string) => {
    setActiveCommentId(id)
    highlightRefs.current.get(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [])

  // modals
  const [showRejectModal, setShowRejectModal] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [showApproveConfirm, setShowApproveConfirm] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [doneState, setDoneState] = useState<'approved' | 'rejected' | null>(null)

  const reviewQuery = useVisitReportReview(visitId, token)
  const postCommentMutation = usePostVisitReportComment(visitId)
  const patchCommentMutation = usePatchVisitReportComment(visitId)
  const approveMutation = useApproveVisitReport(visitId)
  const rejectMutation = useRejectVisitReport(visitId)

  useEffect(() => {
    if (!visitId || !token) {
      setLoadError('Invalid review link.')
      setLoading(false)
      return
    }
    if (reviewQuery.isSuccess && reviewQuery.data) {
      const d = reviewQuery.data as ReviewData
      setReviewData(d)
      setComments(d.comments ?? [])
      setLoading(false)
    } else if (reviewQuery.isError) {
      const err = reviewQuery.error as any
      setLoadError(
        String(
          err?.response?.data?.detail ??
            'Could not load report. The link may have expired or already been used.',
        ),
      )
      setLoading(false)
    }
  }, [visitId, token, reviewQuery.isSuccess, reviewQuery.isError, reviewQuery.data, reviewQuery.error])

  // Close active comment when clicking outside
  const handleBodyClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement
    if (!target.closest('[data-comment-id]') && !target.closest('[data-comment-card]')) {
      setActiveCommentId(null)
    }
  }, [])

  // Text selection handler
  const handleMouseUp = useCallback(() => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || !reportRef.current) { setSelection(null); return }
    const range = sel.getRangeAt(0)
    const text = sel.toString().trim()
    if (!text || text.length < 2) { setSelection(null); return }
    const container = range.commonAncestorContainer
    const rect = range.getBoundingClientRect()
    const path = domPath(container, reportRef.current)
    const fieldKey = nearestFieldKey(container, reportRef.current)
    setSelection({ text, domPath: path, fieldKey, startOffset: range.startOffset, endOffset: range.endOffset, x: rect.left, y: rect.bottom })
  }, [])

  const handleSaveAnnotation = async (commentText: string) => {
    if (!selection || !visitId) return
    try {
      const encodedDomPath = encodeDomPathWithFieldKey(selection.fieldKey, selection.domPath)
      const result = await postCommentMutation.mutateAsync({
        token,
        highlighted_text: selection.text,
        dom_path: encodedDomPath,
        start_offset: selection.startOffset,
        end_offset: selection.endOffset,
        comment_text: commentText,
      })
      const newComment: ReviewComment = {
        id: result.id, highlighted_text: selection.text, dom_path: encodedDomPath,
        start_offset: selection.startOffset, end_offset: selection.endOffset,
        comment_text: commentText, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      }
      setComments((prev) => [...prev, newComment])
      setActiveCommentId(result.id)
      window.getSelection()?.removeAllRanges()
      setSelection(null)
      // Scroll sidebar to the new card after render (sidebar-only, no page scroll)
      setTimeout(() => scrollCardInSidebar(result.id), 80)
    } catch { alert('Failed to save comment. Please try again.') }
  }

  const handleEditComment = async (comment: ReviewComment, newText: string) => {
    if (!visitId) return
    await patchCommentMutation.mutateAsync({ commentId: comment.id, token, comment_text: newText })
    setComments((prev) => prev.map((c) => c.id === comment.id ? { ...c, comment_text: newText, updated_at: new Date().toISOString() } : c))
  }

  const handleApprove = async () => {
    if (!visitId) return
    setActionBusy(true)
    try { await approveMutation.mutateAsync({ token }); setDoneState('approved') }
    catch (err: any) { alert(err?.response?.data?.detail ?? 'Approval failed.') }
    finally { setActionBusy(false); setShowApproveConfirm(false) }
  }

  const handleReject = async () => {
    if (!rejectReason.trim() || !visitId) return
    setActionBusy(true)
    try { await rejectMutation.mutateAsync({ token, reason: rejectReason.trim() }); setDoneState('rejected') }
    catch (err: any) { alert(err?.response?.data?.detail ?? 'Rejection failed.') }
    finally { setActionBusy(false); setShowRejectModal(false) }
  }

  const payload = reviewData?.payload ?? {}
  const useDynamicReviewBody = useMemo(
    () => shouldUseDynamicReviewBody(reviewData?.template, payload),
    [reviewData?.template, payload],
  )
  const submissionRecord = useMemo(
    () => buildSubmissionDataForReview(payload, reviewData?.template),
    [payload, reviewData?.template],
  )
  const legacyCustomFieldsByAnchor = useMemo(
    () => buildLegacyCustomFieldsByAnchor(reviewData?.template),
    [reviewData?.template],
  )

  const visitHeaderTitle = useMemo(() => {
    if (!visitId) return 'Visit Report'
    const n = reviewData?.site_visit_number
    if (n != null && Number.isFinite(Number(n))) return `Visit #${Number(n)}`
    return `Visit ${visitId}`
  }, [visitId, reviewData?.site_visit_number])

  const isDynamicMvr = useDynamicReviewBody
  const revisionBaseline = useMemo(() => resolveRevisionBaseline(reviewData?.payload ?? {}), [reviewData])
  const comparisonValues = useMemo(() => reportValuesForComparison(reviewData), [reviewData])
  const baselineValues = useMemo(() => baselineValuesForComparison(reviewData), [reviewData])
  const changedFieldKeys = useMemo(() => {
    const keys = new Set<string>()
    const allKeys = new Set([...Object.keys(baselineValues), ...Object.keys(comparisonValues)])
    for (const key of allKeys) {
      if (key === 'reportStatus' || key === 'rejectionReason' || key === 'revisionBaseline') continue
      if (!valuesEqual(baselineValues[key], comparisonValues[key])) keys.add(key)
    }
    return keys
  }, [baselineValues, comparisonValues])
  const renderInsertedAfter = useCallback(
    (placement: 'block' | 'grid', ...anchorIds: string[]) => {
      const fields = legacyCustomFieldsAfter(legacyCustomFieldsByAnchor, ...anchorIds)
      if (!fields.length) return null
      return (
        <MvrLegacyInsertedFieldsReview
          fields={fields}
          submissionData={submissionRecord}
          changedFieldKeys={changedFieldKeys}
          placement={placement}
        />
      )
    },
    [legacyCustomFieldsByAnchor, submissionRecord, changedFieldKeys],
  )
  const commentChangeInfo = useMemo(() => {
    const out: Record<string, CommentChangeInfo> = {}
    if (!Object.keys(baselineValues).length) return out
    const matchDefs = reviewData?.template?.schema?.fields?.length
      ? reviewData.template.schema.fields
      : LEGACY_VISIT_REPORT_FIELD_DEFS
    for (const comment of comments) {
      const matched = Array.from(resolveCommentedFieldKeysFromTemplate([comment], matchDefs))
      const changed = matched.filter((key) => changedFieldKeys.has(key))
      const displayKey = changed[0] ?? matched[0] ?? ''
      out[comment.id] = {
        changed: changed.length > 0,
        fieldKeys: matched,
        changedKeys: changed,
        label: displayKey ? labelForField(displayKey, reviewData) : 'Commented text',
        before: displayKey ? previewValue(baselineValues[displayKey]) : 'Not matched',
        after: displayKey ? previewValue(comparisonValues[displayKey]) : 'Not matched',
      }
    }
    return out
  }, [baselineValues, changedFieldKeys, comments, comparisonValues, reviewData])
  const changedCommentCount = useMemo(
    () => Object.values(commentChangeInfo).filter((info) => info.changed).length,
    [commentChangeInfo],
  )

  // ── Loading / Error / Done screens ───────────────────────────────────────
  const spinnerScreen = (msg: string) => (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bgSubtle }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ width: 40, height: 40, borderRadius: '50%', border: '3px solid #ddd', borderTopColor: C.primary, animation: 'spin 1s linear infinite', margin: '0 auto 12px' }} />
        <div style={{ color: C.textSub, fontSize: 14 }}>{msg}</div>
      </div>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )

  if (loading) return spinnerScreen('Loading report…')

  if (loadError) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bgSubtle }}>
      <div style={{ background: '#fff', borderRadius: 14, padding: 32, maxWidth: 440, textAlign: 'center', boxShadow: '0 4px 24px rgba(0,0,0,.1)' }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>🔗</div>
        <div style={{ fontSize: 18, fontWeight: 700, color: C.text, marginBottom: 8 }}>Review Link Issue</div>
        <div style={{ fontSize: 14, color: C.textSub }}>{loadError}</div>
      </div>
    </div>
  )

  if (doneState) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.bgSubtle }}>
      <div style={{ background: '#fff', borderRadius: 14, padding: 40, maxWidth: 440, textAlign: 'center', boxShadow: '0 4px 24px rgba(0,0,0,.1)', border: `2px solid ${doneState === 'approved' ? '#bbf7d0' : '#fecaca'}` }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>{doneState === 'approved' ? '✅' : '🔄'}</div>
        <div style={{ fontSize: 20, fontWeight: 800, color: C.text, marginBottom: 8 }}>
          {doneState === 'approved' ? 'Report Approved!' : 'Report Rejected — Author Notified'}
        </div>
        <div style={{ fontSize: 14, color: C.textSub }}>
          {doneState === 'approved'
            ? 'The report has been approved and locked. The author has been notified.'
            : 'The author has been notified by email to address your comments and resubmit.'}
        </div>
        <div style={{ marginTop: 20, fontSize: 12, color: C.textSub }}>You may close this tab.</div>
      </div>
    </div>
  )

  const p = payload
  const fieldValues = submissionRecord
  const pv = (key: string) => fieldValues[key] ?? ''
  const pvText = (key: string) => previewValue(pv(key))
  const prows = (key: string): Row[] => { const v = fieldValues[key]; return Array.isArray(v) ? (v as Row[]) : [] }
  const section4SiteValues: Record<Section4SiteManagementQuestionId, string> = {
    q401: String(pv('q401')),
    q402: String(pv('q402')),
    q403: String(pv('q403')),
    q404: String(pv('q404')),
    q405: String(pv('q405')),
    q406: String(pv('q406')),
    q407: String(pv('q407')),
    q408: String(pv('q408')),
    q409: String(pv('q409')),
    q410: String(pv('q410')),
  }
  const questionCommentsMap =
    p.questionComments && typeof p.questionComments === 'object' && !Array.isArray(p.questionComments)
      ? (p.questionComments as Record<string, string>)
      : {}
  const pqc = (questionId: string) => questionCommentsMap[questionCommentKey(questionId)] ?? ''

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      <style>{`
        @keyframes spin{to{transform:rotate(360deg)}}
        html,body{overflow:auto!important;height:auto!important;min-height:100vh;margin:0;font-family:system-ui,-apple-system,sans-serif;}
        *{box-sizing:border-box}
        ::selection{background:#fef3c7}
        .sidebar-scroll::-webkit-scrollbar{width:5px}
        .sidebar-scroll::-webkit-scrollbar-track{background:transparent}
        .sidebar-scroll::-webkit-scrollbar-thumb{background:#d1d5db;border-radius:4px}
      `}</style>

      {/* ── Fixed top bar ── */}
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 999, height: C.topbarH,
        background: C.primary, boxShadow: '0 2px 12px rgba(0,0,0,.2)',
        padding: '0 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
      }}>
        <div style={{ color: '#fff', minWidth: 0 }}>
          <div style={{ fontSize: 11, opacity: .7, fontWeight: 600, letterSpacing: '.08em', textTransform: 'uppercase' }}>Monitoring Visit Report — Review Mode</div>
          <div style={{ fontSize: 13, fontWeight: 700, marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {comments.length > 0 ? `${comments.length} comment${comments.length !== 1 ? 's' : ''}` : 'Highlight text to comment'}
            {reviewData?.reviewer_email && <span style={{ opacity: .6, fontWeight: 400, marginLeft: 8 }}>· {reviewData.reviewer_email}</span>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
          <button type="button" onClick={() => setShowRejectModal(true)} disabled={actionBusy}
            style={{ background: '#fff', color: C.danger, border: '2px solid #fff', borderRadius: 7, padding: '7px 16px', fontWeight: 700, fontSize: 13, cursor: actionBusy ? 'default' : 'pointer', opacity: actionBusy ? .6 : 1 }}>
            ✗ Reject
          </button>
          <button type="button" onClick={() => setShowApproveConfirm(true)} disabled={actionBusy}
            style={{ background: C.success, color: '#fff', border: `2px solid ${C.success}`, borderRadius: 7, padding: '7px 16px', fontWeight: 700, fontSize: 13, cursor: actionBusy ? 'default' : 'pointer', opacity: actionBusy ? .6 : 1 }}>
            ✓ Approve
          </button>
        </div>
      </div>

      {/* ── Modals ── */}
      {showApproveConfirm && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1100, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div style={{ background: '#fff', borderRadius: 14, padding: 28, width: '100%', maxWidth: 400, textAlign: 'center', boxShadow: '0 20px 60px rgba(0,0,0,.25)' }}>
            <div style={{ fontSize: 40, marginBottom: 10 }}>✅</div>
            <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 8, color: C.text }}>Approve this Report?</div>
            <div style={{ fontSize: 13.5, color: C.textSub, marginBottom: 20 }}>
              This will mark the report as <strong>Approved</strong>, lock it, and notify the author.
              {comments.length > 0 && ` Your ${comments.length} comment${comments.length !== 1 ? 's' : ''} will be preserved.`}
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button type="button" onClick={() => setShowApproveConfirm(false)} disabled={actionBusy}
                style={{ padding: '9px 20px', borderRadius: 8, border: `1.5px solid ${C.border}`, background: C.bgSubtle, cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button type="button" onClick={() => void handleApprove()} disabled={actionBusy}
                style={{ padding: '9px 20px', borderRadius: 8, border: 'none', background: C.success, color: '#fff', cursor: 'pointer', fontWeight: 700, fontSize: 13, opacity: actionBusy ? .6 : 1 }}>
                {actionBusy ? 'Approving…' : 'Yes, Approve'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showRejectModal && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1100, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div style={{ background: '#fff', borderRadius: 14, padding: 28, width: '100%', maxWidth: 460, boxShadow: '0 20px 60px rgba(0,0,0,.25)' }}>
            <div style={{ fontSize: 17, fontWeight: 800, color: C.text, marginBottom: 4 }}>Reject Report</div>
            <div style={{ fontSize: 12.5, color: C.textSub, marginBottom: 16 }}>Provide an overall rejection reason. The author will receive this by email along with your inline comments.</div>
            <label style={labelBase}>Overall Rejection Reason <span style={{ color: C.danger }}>*</span></label>
            <textarea autoFocus placeholder="Describe what needs to be addressed…" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
              style={{ ...inputBase, background: '#fff', resize: 'vertical', minHeight: 100, cursor: 'text', marginBottom: 16 }} />
            {comments.length > 0 && (
              <div style={{ fontSize: 12, color: C.textSub, marginBottom: 16, padding: '8px 12px', background: '#fffbeb', borderRadius: 6, border: '1px solid #fde68a' }}>
                📝 {comments.length} inline comment{comments.length !== 1 ? 's' : ''} will be included.
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" onClick={() => setShowRejectModal(false)} disabled={actionBusy}
                style={{ padding: '9px 18px', borderRadius: 8, border: `1.5px solid ${C.border}`, background: C.bgSubtle, cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>Cancel</button>
              <button type="button" onClick={() => void handleReject()} disabled={!rejectReason.trim() || actionBusy}
                style={{ padding: '9px 18px', borderRadius: 8, border: 'none', background: C.danger, color: '#fff', cursor: rejectReason.trim() ? 'pointer' : 'default', fontWeight: 700, fontSize: 13, opacity: !rejectReason.trim() || actionBusy ? .5 : 1 }}>
                {actionBusy ? 'Rejecting…' : 'Reject & Notify Author'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Annotation Popover ── */}
      {selection && (
        <AnnotationPopover capture={selection} onSave={handleSaveAnnotation}
          onClose={() => { setSelection(null); window.getSelection()?.removeAllRanges() }} />
      )}

      {/* ── Two-column body ── */}
      <div
        style={{ display: 'flex', gap: 0, paddingTop: C.topbarH, minHeight: '100vh', background: '#f1f5f9' }}
        onClick={handleBodyClick}
      >
        {/* ─── Left: main report ─── */}
        <div
          style={{ flex: 1, minWidth: 0, padding: '20px 20px 40px 20px' }}
          onMouseUp={handleMouseUp}
          ref={reportRef}
        >
          {/* Banners */}
          {reviewData?.message && (
            <div style={{ background: '#ede9fe', border: '1.5px solid #c4b5fd', borderRadius: C.radius, padding: '10px 14px', marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#4c1d95', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '.04em' }}>Message from the Monitor</div>
              <div style={{ fontSize: 13, color: '#374151' }}>{reviewData.message}</div>
            </div>
          )}
          <div style={{ background: '#fffbeb', border: '1.5px solid #fde68a', borderRadius: C.radius, padding: '9px 14px', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 16 }}>✏️</span>
            <div style={{ fontSize: 12.5, color: '#92400e' }}>
              <strong>Review Mode</strong> — Select any text to add a comment. Click highlights or sidebar cards to navigate.
            </div>
          </div>

          {Object.keys(baselineValues).length > 0 && (
            <div style={{
              background: '#f0fdf4',
              border: '1.5px solid #bbf7d0',
              borderRadius: C.radius,
              padding: '10px 14px',
              marginBottom: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              color: '#14532d',
            }}>
              <span style={{ fontSize: 16 }}>✓</span>
              <div style={{ fontSize: 12.5 }}>
                <strong>Revision changes detected:</strong>{' '}
                {changedFieldKeys.size} field{changedFieldKeys.size !== 1 ? 's' : ''} changed since rejection
                {comments.length > 0
                  ? `, including ${changedCommentCount} of ${comments.length} commented area${comments.length !== 1 ? 's' : ''}.`
                  : '.'}
                {revisionBaseline.createdAt && (
                  <span style={{ display: 'block', color: '#166534', marginTop: 2, fontSize: 11.5 }}>
                    Baseline captured {new Date(revisionBaseline.createdAt).toLocaleString()}.
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Report header */}
          <Card style={{ background: 'linear-gradient(135deg,#1a56db 0%,#1e40af 100%)', border: 'none', color: '#fff', marginBottom: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', opacity: .7, marginBottom: 4 }}>Monitoring Visit Report (MVR) — Read-Only Review</div>
            <div style={{ fontSize: 20, fontWeight: 800 }}>{visitHeaderTitle}</div>
            {reviewData?.template && (
              <div style={{ marginTop: 6, fontSize: 12, opacity: 0.9, fontWeight: 600 }}>
                {reviewData.template.name} · template v{reviewData.template.version}
                {!isDynamicMvr && ' · built-in visit report layout'}
              </div>
            )}
            <div style={{ marginTop: 8, display: 'inline-block', background: '#ede9fe', color: '#4c1d95', borderRadius: 20, padding: '3px 12px', fontSize: 11.5, fontWeight: 700 }}>Under Review</div>
          </Card>

          {isDynamicMvr && reviewData?.template ? (
          <Card>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 7, background: C.primaryLight, color: C.primary, fontSize: 11, fontWeight: 800, flexShrink: 0 }}>MVR</span>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: C.text }}>Submitted report</div>
                <div style={{ fontSize: 12, color: C.textSub, marginTop: 2 }}>Same template and answers the CRA submitted.</div>
              </div>
            </div>
            <MvrDynamicReviewReportBody
              template={reviewData.template}
              submissionData={submissionRecord}
              changedFieldKeys={changedFieldKeys}
            />
          </Card>
          ) : (
          <>
          {/* Section 1 — legacy static MVR only */}
          <Card>
            <SectionHeader num="1" title="Study and Visit Details" />
            {renderInsertedAfter('block', '__template_start__', 'legacy_s1')}
            <div style={grid}>
              <ROInput label="Study Title" value={pv('studyTitle')} />
              {renderInsertedAfter(
                'grid',
                'legacy_s1_study_title',
                'legacy_s1_sponsor',
                'legacy_s1_study_type',
                'legacy_s1_pi',
              )}
              <ROInput label="Sponsor" value={pv('sponsor')} />
              <ROInput label="Type of Study" value={pv('studyType')} />
              <ROInput label="Site Name" value={pv('site')} />
              {renderInsertedAfter('grid', 'legacy_s1_site')}
              <ROInput label="Principal Investigator (PI)" value={pv('pi')} />
              <ROInput label="Start Visit Date" value={pv('visitStartDate') || pv('visitDate')} />
              {renderInsertedAfter('grid', 'legacy_s1_visit_start_date')}
              <ROInput label="End Visit Date" value={pv('visitEndDate')} />
              {renderInsertedAfter('grid', 'legacy_s1_visit_end_date')}
              <ROInput label="Start Date of Previous Visit" value={pv('prevVisitNA') ? 'N/A' : (pv('prevVisitStartDate') || pv('prevVisitDate'))} />
              <ROInput label="End Date of Previous Visit" value={pv('prevVisitNA') ? 'N/A' : pv('prevVisitEndDate')} />
              {renderInsertedAfter('grid', 'legacy_s1_prev_visit_date', 'legacy_s1_prev_visit_note')}
              <ROInput label="Start Date of Next Visit" value={pv('nextVisitTbd') ? 'TBD' : (pv('nextVisitStartDate') || pv('nextVisitDate'))} />
              <ROInput label="End Date of Next Visit" value={pv('nextVisitTbd') ? 'TBD' : pv('nextVisitEndDate')} />
              {renderInsertedAfter('grid', 'legacy_s1_next_visit_date', 'legacy_s1_next_visit_note')}
            </div>
            <ROTable label="Site Personnel" cols={[{ key:'name',label:'Name' },{ key:'role',label:'Role' }]} rows={prows('sitePersonnelRows')} />
            <ROTable label="Monitor Personnel" cols={[{ key:'name',label:'Name' },{ key:'role',label:'Role' }]} rows={prows('monitorPersonnelRows')} />
            <ROTable label="Other Personnel" cols={[{ key:'name',label:'Name' },{ key:'role',label:'Role' }]} rows={prows('otherPersonnelRows')} />
            <ROTextarea label="Purpose of This Visit" value={pv('visitPurpose')} full />
          </Card>

          {/* Section 2 */}
          <Card>
            <SectionHeader num="2" title="Recruitment Participant Status" />
            <div style={grid}>
              {(['Screened','Enrolled','Active','Drop-outs','Completed Study'] as const).map((lbl, i) => {
                const keys = ['ptScreened','ptEnrolled','ptActive','ptDropouts','ptCompleted']
                return <ROInput key={lbl} label={`Participants ${lbl}`} value={pv(keys[i])} />
              })}
            </div>
            <ROTextarea label="Comments" value={pv('s2Comments')} />
          </Card>

          {/* Section 3 */}
          <Card>
            <SectionHeader num="3" title="Findings" />
            <ROYNBadge num="3" label="Are there any findings?" value={pv('q3') as YNChoice} />
            <ROTextarea label="Findings Summary" value={pv('s3Comments')} />
          </Card>

          {/* Section 4 */}
          <Card>
            <SectionHeader num="4" title="Site Management & General Site Assessment" />
            {SECTION4_SITE_MANAGEMENT_QUESTIONS.map((q, i) => {
              if (!isSection4SiteManagementQuestionVisible(q, section4SiteValues)) return null;
              return (
                <ROYNBadge key={q.id} num={`4.${i + 1}`} value={pv(q.id) as YNChoice} label={q.label} comment={pqc(q.id)} />
              );
            })}
          </Card>

          {/* Section 5 */}
          {!pv('s5NA') && (
          <Card>
            <SectionHeader num="5" title="Participants Informed Consent / Enrolment" />
            {SECTION4_CONSENT_QUESTIONS.map((q, i) => (
              <ROYNBadge key={q.id} num={`5.${i + 1}`} value={pv(q.id) as YNChoice} label={q.label} comment={pqc(q.id)} />
            ))}
            <ROTable
              label="ICF Review Table"
              cols={[
                { key:'screeningNo',label:'Subject screening No.' },
                { key:'correctIcfVersion',label:'ICF Version Used (Version No. & Date)' },
                { key:'consentBeforeProcedures',label:'Consent Obtained Before Procedures', type:'yn' },
                { key:'subjectSignatureDate',label:'Subject Signature Date' },
                { key:'personObtainingConsent',label:'Consent obtained by', type:'select' },
                { key:'piSignatureDate',label:'Investigator Signature Date' },
                { key:'comments',label:'Comments' },
              ]}
              rows={prows('icfRows')}
            />
          </Card>
          )}

          {/* Section 6 */}
          {!pv('s6NA') && (
          <Card>
            <SectionHeader num="6" title="Case Report Form (CRF) / Source Data Verification (SDV)" />
            {SECTION6_SDV_QUESTIONS.map((q, i) => (
              <ROYNBadge key={q.id} num={`6.${i + 1}`} value={pv(q.id) as YNChoice} label={q.label} comment={pqc(q.id)} />
            ))}
            <ROTable label="SDV Review Table" cols={[
              { key:'screeningNo',label:'Subject Screening No.' },
              { key:'subjectId',label:'Subject ID' },
              { key:'visitCycle',label:'Visit / Cycle' },
              { key:'comments',label:'Comments' },
            ]} rows={prows('sdvRows')} />
          </Card>
          )}

          {!pv('s11NA') && (
          <Card>
            <SectionHeader num="7" title="Essential Documents, ISF or TMF" />
            {SECTION10_ESSENTIAL_DOCS_QUESTIONS.map((q, i) => (
              <ROYNBadge key={q.id} num={`7.${i + 1}`} value={pv(q.id) as YNChoice} label={q.label} comment={pqc(q.id)} />
            ))}
          </Card>
          )}

          {!pv('s8NA') && (
            <Card>
              <SectionHeader num="8" title="Investigational Medical Product (IMP)" />
              {SECTION10_IMP_QUESTIONS.map((q, i) => (
                <ROYNBadge key={q.id} num={`8.${i + 1}`} value={pv(q.id) as YNChoice} label={q.label} comment={pqc(q.id)} />
              ))}
            </Card>
          )}

          {!pv('s9NA') && (
            <Card>
              <SectionHeader num="9" title="Biological Sample / Laboratory Sample Review" />
              {SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS.map((q, i) => (
                <ROYNBadge key={q.id} num={`9.${i + 1}`} value={pv(q.id) as YNChoice} label={q.label} comment={pqc(q.id)} />
              ))}
            </Card>
          )}

          <Card>
            <SectionHeader num="10" title="Summary of the Visit" />
            <div style={{ ...inputBase, minHeight: 100, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: pv('summary') ? C.text : C.textSub }}>{pvText('summary')}</div>
          </Card>

          <Card>
            <SectionHeader num="11" title="Signatures" />
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr)',
                gap: 16,
                alignItems: 'end',
                marginBottom: 8,
              }}
            >
              <div />
              <label style={{ ...labelBase, marginBottom: 0 }}>Signature</label>
              <label style={{ ...labelBase, marginBottom: 0 }}>Date</label>
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr)',
                gap: 16,
                alignItems: 'end',
                marginBottom: 18,
              }}
            >
              <ROInput label="Prepared by" value={signatureReviewValue(p, 'preparedByName', 'monitorName')} />
              <ROInput label=" " value={pv('preparedBySignature')} />
              <ROInput label=" " value={formatSignatureDateDisplay(pv('preparedByDate'))} />
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr)',
                gap: 16,
                alignItems: 'end',
              }}
            >
              <ROInput label="Reviewed & Approved by" value={signatureReviewValue(p, 'reviewedByName', 'reviewerName')} />
              <ROInput label=" " value={pv('reviewedBySignature')} />
              <ROInput label=" " value={formatSignatureDateDisplay(pv('reviewedByDate'))} />
            </div>
          </Card>
          </>
          )}

          {/* Bottom CTA */}
          <Card style={{ border: `2px solid ${C.primaryLight}`, background: C.primaryLight }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 14 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: C.text }}>Ready to submit your review?</div>
                <div style={{ fontSize: 12.5, color: C.textSub, marginTop: 2 }}>
                  {comments.length > 0 ? `${comments.length} comment${comments.length !== 1 ? 's' : ''} added.` : 'Select text anywhere in the report to add inline comments.'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button type="button" onClick={() => setShowRejectModal(true)}
                  style={{ padding: '9px 20px', borderRadius: 8, border: `2px solid ${C.danger}`, background: '#fff', color: C.danger, fontWeight: 700, fontSize: 13.5, cursor: 'pointer' }}>✗ Reject</button>
                <button type="button" onClick={() => setShowApproveConfirm(true)}
                  style={{ padding: '9px 20px', borderRadius: 8, border: 'none', background: C.success, color: '#fff', fontWeight: 700, fontSize: 13.5, cursor: 'pointer' }}>✓ Approve</button>
              </div>
            </div>
          </Card>
        </div>

        {/* ─── Right: sticky comment sidebar ─── */}
        <div
          ref={sidebarRef}
          className="sidebar-scroll"
          data-comment-card="sidebar"
          style={{
            width: 300,
            flexShrink: 0,
            position: 'sticky',
            top: C.topbarH,
            height: `calc(100vh - ${C.topbarH}px)`,
            overflowY: 'auto',
            background: '#f8fafc',
            borderLeft: `1.5px solid ${C.border}`,
            padding: '14px 12px',
          }}
        >
          {/* Sidebar header */}
          <div style={{ fontWeight: 700, fontSize: 13, color: C.text, marginBottom: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>💬 Comments{comments.length > 0 ? ` (${comments.length})` : ''}</span>
            {activeCommentId && (
              <button type="button" onClick={() => setActiveCommentId(null)}
                style={{ fontSize: 11, color: C.textSub, background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px' }}>
                Clear ×
              </button>
            )}
          </div>

          {comments.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 10px', color: C.textSub }}>
              <div style={{ fontSize: 28, marginBottom: 10 }}>✏️</div>
              <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>Select any text in the report to add a comment here.</div>
            </div>
          ) : (
            comments.map((c) => (
              <CommentCard
                key={c.id}
                comment={c}
                isActive={activeCommentId === c.id}
                onClick={() => handleCardClick(c.id)}
                onEdit={handleEditComment}
                registerRef={(el) => registerCard(c.id, el)}
                changeInfo={commentChangeInfo[c.id]}
              />
            ))
          )}

          {/* Pending new selection indicator */}
          {selection && (
            <div style={{ border: '2px dashed #fcd34d', borderRadius: 8, padding: '10px 12px', background: '#fffbeb', marginTop: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#92400e', marginBottom: 4 }}>New comment…</div>
              <div style={{ fontSize: 11.5, color: '#92400e', fontStyle: 'italic' }}>"{selection.text.length > 50 ? selection.text.slice(0, 50) + '…' : selection.text}"</div>
            </div>
          )}
        </div>
      </div>

      {/* ── Inline highlights (rendered as an overlay pass over the whole doc) ── */}
      {/* We render highlights by searching the DOM for text nodes after mount.    */}
      {/* For simplicity, highlights are shown as floating marks in a portal div,  */}
      {/* or — the simpler approach: embed them inline via data-comment markers.    */}
      {/* Since the text is rendered as static divs, we overlay highlight marks    */}
      {/* using an absolute-positioned div per comment anchored to the report.     */}
      {/* The approach below uses a dedicated floating marks layer.                */}
      <HighlightLayer
        comments={comments}
        activeCommentId={activeCommentId}
        reportRef={reportRef}
        onActivate={handleHighlightClick}
        registerHighlight={registerHighlight}
      />
    </>
  )
}

// ── Highlight layer ───────────────────────────────────────────────────────────
// Finds each comment's highlighted text within the reportRef DOM, measures the
// bounding rect, and renders a fixed-positioned translucent mark behind the text.
function HighlightLayer({ comments, activeCommentId, reportRef, onActivate, registerHighlight }: {
  comments: ReviewComment[]
  activeCommentId: string | null
  reportRef: React.RefObject<HTMLDivElement | null>
  onActivate: (id: string) => void
  registerHighlight: (id: string, el: HTMLElement | null) => void
}) {
  const [rects, setRects] = useState<Array<{ id: string; rects: DOMRect[] }>>([])

  // Recalculate highlight positions on comments change or scroll/resize
  const recalc = useCallback(() => {
    if (!reportRef.current) return
    const root = reportRef.current
    const result: Array<{ id: string; rects: DOMRect[] }> = []

    for (const comment of comments) {
      const found: DOMRect[] = []
      // Walk all text nodes in the report, find ones containing the highlighted_text
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
      let node: Node | null
      const target = comment.highlighted_text
      while ((node = walker.nextNode())) {
        const text = node.textContent ?? ''
        const idx = text.indexOf(target)
        if (idx === -1) continue
        try {
          const range = document.createRange()
          range.setStart(node, idx)
          range.setEnd(node, idx + target.length)
          const domRects = Array.from(range.getClientRects())
          found.push(...domRects)
          break // use first match
        } catch { /* ignore */ }
      }
      if (found.length > 0) result.push({ id: comment.id, rects: found })
    }
    setRects(result)
  }, [comments, reportRef])

  useEffect(() => {
    recalc()
    window.addEventListener('scroll', recalc, { passive: true })
    window.addEventListener('resize', recalc, { passive: true })
    return () => { window.removeEventListener('scroll', recalc); window.removeEventListener('resize', recalc) }
  }, [recalc])

  return (
    <>
      {rects.map(({ id, rects: domRects }) => {
        const isActive = activeCommentId === id
        return (
          <React.Fragment key={id}>
            {domRects.map((r, ri) => (
              <div
                key={ri}
                ref={ri === 0 ? (el) => registerHighlight(id, el as HTMLElement | null) : undefined}
                data-comment-id={id}
                onClick={(e) => { e.stopPropagation(); onActivate(id) }}
                style={{
                  position: 'fixed',
                  left: r.left,
                  top: r.top,
                  width: r.width,
                  height: r.height,
                  background: isActive ? 'rgba(251,191,36,.55)' : 'rgba(254,240,138,.55)',
                  borderBottom: `2px solid ${isActive ? '#d97706' : '#fde68a'}`,
                  cursor: 'pointer',
                  zIndex: 10,
                  pointerEvents: 'auto',
                  transition: 'background .15s, border-color .15s',
                  boxShadow: isActive ? '0 0 0 2px rgba(251,191,36,.3)' : 'none',
                  borderRadius: 2,
                }}
                title={comments.find(c => c.id === id)?.comment_text}
              />
            ))}
          </React.Fragment>
        )
      })}
    </>
  )
}
