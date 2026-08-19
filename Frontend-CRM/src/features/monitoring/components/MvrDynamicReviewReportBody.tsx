/**
 * Read-only body for MVR review links: renders payload.submissionData
 * using the same template schema the CRA used (matches DynamicVisitReportShell).
 * Uses divs/spans so reviewers can select text for annotations.
 */
import React from 'react'
import type { MvrFieldDef, MvrTemplateDto } from '@/components/mon/types/mvrTemplate'

const C = {
  text: '#111827',
  textSub: '#6b7280',
  border: '#e5e7eb',
  bg: '#ffffff',
  bgSubtle: '#f9fafb',
  primary: '#1a56db',
  primaryLight: '#e8f0fe',
} as const

const labelBase: React.CSSProperties = {
  display: 'block',
  fontSize: 12,
  fontWeight: 600,
  color: C.textSub,
  marginBottom: 5,
  letterSpacing: '.02em',
  textTransform: 'uppercase',
}

const valueBox: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  fontSize: 13.5,
  lineHeight: 1.5,
  color: C.text,
  background: '#f3f4f6',
  border: `1.5px solid ${C.border}`,
  borderRadius: 8,
  boxSizing: 'border-box',
  minHeight: 38,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
}

function displayVal(v: unknown): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (Array.isArray(v)) return v.length ? v.map((item) => String(item)).join(', ') : '—'
  return String(v)
}

type Row = Record<string, string>

function ReadOnlyTable({
  cols,
  rows,
  label,
}: {
  cols: { key: string; label: string }[]
  rows: Row[]
  label?: string
}) {
  const showLabel = label != null && label !== ""
  if (!rows || rows.length === 0) {
    return (
      <div style={{ marginTop: showLabel ? 10 : 0 }}>
        {showLabel && <label style={labelBase}>{label}</label>}
        <div style={{ ...valueBox, color: C.textSub }}>—</div>
      </div>
    )
  }
  return (
    <div style={{ marginTop: showLabel ? 10 : 0, overflowX: 'auto' }}>
      {showLabel && <label style={labelBase}>{label}</label>}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c.key}
                style={{
                  textAlign: 'left',
                  padding: '8px 10px',
                  background: C.bgSubtle,
                  borderBottom: `2px solid ${C.border}`,
                  borderTop: `1.5px solid ${C.border}`,
                  color: C.textSub,
                  fontWeight: 700,
                  fontSize: 11,
                  letterSpacing: '.04em',
                  textTransform: 'uppercase',
                }}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ background: i % 2 === 0 ? C.bg : C.bgSubtle }}>
              {cols.map((c) => (
                <td key={c.key} style={{ padding: '6px 10px', borderBottom: `1px solid ${C.border}`, color: C.text }}>
                  {row[c.key] ?? '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function isFullWidthReviewField(field: MvrFieldDef): boolean {
  return field.type === 'section' || field.type === 'table' || field.type === 'textarea' || field.type === 'multiselect'
}

export function MvrDynamicReviewReportBody({
  template,
  submissionData,
  changedFieldKeys,
  layout = 'page',
}: {
  template: MvrTemplateDto
  submissionData: Record<string, unknown>
  changedFieldKeys?: Set<string>
  /** page = standalone 2-col grid; inline = field nodes only (for legacy grid embedding) */
  layout?: 'page' | 'inline'
}) {
  const fields = template.schema?.fields ?? []

  const renderField = (f: MvrFieldDef) => {
    const key = f.id
    const val = submissionData[key]

    if (f.type === 'section') {
      return (
        <div key={key} style={{ marginBottom: 20, paddingBottom: 16, borderBottom: `1px solid ${C.border}` }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 8px', color: C.text }}>{f.label}</h3>
          {f.content && (
            <div style={{ fontSize: 13, color: C.textSub, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{f.content}</div>
          )}
        </div>
      )
    }

    const changed = changedFieldKeys?.has(key) ?? false
    const fieldStyle: React.CSSProperties = {
      marginBottom: f.type === 'table' ? 20 : 16,
      padding: changed ? 10 : 0,
      border: changed ? '2px solid #22c55e' : 'none',
      borderRadius: changed ? 10 : 0,
      background: changed ? '#f0fdf4' : 'transparent',
    }
    const req = f.required ? <span style={{ color: '#dc2626' }}> *</span> : null
    const label = (
      <label style={labelBase}>
        {f.label}
        {req}
        {changed && (
          <span style={{ marginLeft: 8, color: '#15803d', fontWeight: 800, textTransform: 'none', letterSpacing: 0 }}>
            Changed
          </span>
        )}
      </label>
    )

    if (f.type === 'text' || f.type === 'date' || f.type === 'number') {
      return (
        <div key={key} data-mvr-field={key} style={fieldStyle}>
          {label}
          <div style={{ ...valueBox, display: 'flex', alignItems: 'center', color: val == null || val === '' ? C.textSub : C.text }}>
            {displayVal(val)}
          </div>
        </div>
      )
    }

    if (f.type === 'textarea') {
      return (
        <div key={key} data-mvr-field={key} style={fieldStyle}>
          {label}
          <div style={{ ...valueBox, minHeight: 80 }}>{displayVal(val)}</div>
        </div>
      )
    }

    if (f.type === 'checkbox') {
      return (
        <div key={key} data-mvr-field={key} style={fieldStyle}>
          {label}
          <div style={{ ...valueBox, display: 'flex', alignItems: 'center', fontWeight: 600 }}>{displayVal(val)}</div>
        </div>
      )
    }

    if (f.type === 'radio' || f.type === 'select' || f.type === 'multiselect') {
      return (
        <div key={key} data-mvr-field={key} style={fieldStyle}>
          {label}
          <div style={{ ...valueBox, display: 'flex', alignItems: 'center', fontWeight: 600 }}>{displayVal(val)}</div>
        </div>
      )
    }

    if (f.type === 'table') {
      const cols = (f.columns?.length ? f.columns : [{ id: 'col_a', label: 'Column A' }]).map((c) => ({ key: c.id, label: c.label }))
      const raw = val
      const rows: Row[] = Array.isArray(raw)
        ? (raw as Record<string, string>[]).map((r) => {
            const row: Row = {}
            for (const c of cols) row[c.key] = r[c.key] ?? ''
            return row
          })
        : []
      return (
        <div key={key} data-mvr-field={key} style={fieldStyle}>
          {label}
          <ReadOnlyTable cols={cols} rows={rows} />
        </div>
      )
    }

    return (
      <div key={key} style={{ marginBottom: 12, padding: 12, background: '#fffbeb', borderRadius: 8, fontSize: 13, color: '#92400e' }}>
        Unsupported field type in template: {f.label}
      </div>
    )
  }

  if (!fields.length) {
    return layout === 'inline' ? null : <div style={{ color: C.textSub, fontSize: 13 }}>This template has no fields.</div>
  }

  const fieldNodes = fields.map((f) => renderField(f))

  if (layout === 'inline') {
    return <>{fieldNodes}</>
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(1, minmax(0, 1fr))',
        gap: 16,
      }}
      className="mvr-review-fields-grid"
    >
      <style>{`
        @media (min-width: 768px) {
          .mvr-review-fields-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          .mvr-review-fields-grid > [data-mvr-review-full-width="true"] { grid-column: 1 / -1; }
        }
      `}</style>
      {fields.map((f) => {
        const fullWidth = isFullWidthReviewField(f)
        return (
          <div key={f.id} data-mvr-review-full-width={fullWidth ? 'true' : 'false'}>
            {renderField(f)}
          </div>
        )
      })}
    </div>
  )
}
