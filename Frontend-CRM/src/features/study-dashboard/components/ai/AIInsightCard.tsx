/*
 * Renders a single AssistantResponse inside a mockup-style `.cc` card.
 *
 * Switches on response.chart.type to pick a Recharts component (or fall back
 * to a plain `.d` table). Visual idiom matches the rest of MockupDashboard so
 * pinned cards in Section 10 look like first-class dashboard sections.
 */
import React from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { AssistantData, AssistantResponse, ChartSpec } from '../../types'

const PIE_COLORS = ['#378ADD', '#1D9E75', '#EF9F27', '#A32D2D', '#854F0B', '#5F5E5A', '#185FA5']

interface Props {
  response: AssistantResponse
  showSql?: boolean
  /** Render compact inside the drawer (smaller chart heights). */
  compact?: boolean
}

const AIInsightCard: React.FC<Props> = ({ response, showSql = true, compact = false }) => {
  if (response.status === 'no_data') {
    return (
      <div className="cc">
        <div className="ct">No data</div>
        {response.narrative ? <p style={{ margin: 0, fontSize: 12 }}>{response.narrative}</p> : null}
        {response.reason ? (
          <p style={{ margin: '6px 0 0', fontSize: 11, color: 'var(--color-text-secondary)' }}>
            {response.reason}
          </p>
        ) : null}
      </div>
    )
  }

  if (response.status === 'rejected' || response.status === 'execution_error') {
    return (
      <div className="cc" style={{ borderLeft: '3px solid var(--color-text-danger)' }}>
        <div className="ct" style={{ color: 'var(--color-text-danger)' }}>
          {response.status === 'rejected' ? 'Query rejected' : 'Execution error'}
        </div>
        {response.reason ? <p style={{ margin: 0, fontSize: 12 }}>{response.reason}</p> : null}
        {response.sql ? <SqlBlock sql={response.sql} /> : null}
      </div>
    )
  }

  // status === 'ok'
  const { chart, data, narrative, sql, row_count, elapsed_ms } = response
  if (!chart || !data) {
    return (
      <div className="cc">
        <div className="ct">No chart spec returned</div>
        {narrative ? <p style={{ margin: 0, fontSize: 12 }}>{narrative}</p> : null}
      </div>
    )
  }

  return (
    <div className="cc">
      <div className="ct">{chart.title}</div>
      {narrative ? (
        <p style={{ margin: '0 0 8px', fontSize: 12, color: 'var(--color-text-primary)' }}>
          {narrative}
        </p>
      ) : null}
      <ChartRender chart={chart} data={data} compact={compact} />
      <div
        style={{
          marginTop: 6,
          fontSize: 10,
          color: 'var(--color-text-tertiary)',
          display: 'flex',
          gap: 12,
        }}
      >
        <span>{row_count ?? 0} rows</span>
        {typeof elapsed_ms === 'number' ? <span>{elapsed_ms} ms</span> : null}
      </div>
      {showSql && sql ? <SqlBlock sql={sql} /> : null}
    </div>
  )
}

const SqlBlock: React.FC<{ sql: string }> = ({ sql }) => {
  const [open, setOpen] = React.useState(false)
  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      style={{ marginTop: 8 }}
    >
      <summary
        style={{
          cursor: 'pointer',
          fontSize: 11,
          color: 'var(--color-text-secondary)',
          listStyle: 'none',
          userSelect: 'none',
        }}
      >
        {open ? '▾' : '▸'} View SQL
      </summary>
      <pre
        style={{
          margin: '6px 0 0',
          padding: 8,
          background: 'var(--color-background-tertiary)',
          borderRadius: 4,
          fontSize: 11,
          lineHeight: 1.4,
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        <code>{sql}</code>
      </pre>
    </details>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Chart switch
// ─────────────────────────────────────────────────────────────────────────────
const ChartRender: React.FC<{ chart: ChartSpec; data: AssistantData; compact: boolean }> = ({
  chart,
  data,
  compact,
}) => {
  const height = compact ? 180 : 260
  const objects = toObjects(data)

  switch (chart.type) {
    case 'kpi':
      return <KpiCard chart={chart} data={data} />
    case 'table':
      return <TableCard data={data} />
    case 'pie': {
      const nameKey = chart.x_field ?? data.columns[0]
      const valueKey = chart.value_field ?? chart.y_field ?? data.columns[1]
      return (
        <ResponsiveContainer width="100%" height={height}>
          <PieChart>
            <Pie
              data={objects}
              dataKey={valueKey}
              nameKey={nameKey}
              cx="50%"
              cy="50%"
              innerRadius={compact ? 36 : 50}
              outerRadius={compact ? 70 : 95}
              paddingAngle={2}
            >
              {objects.map((_, i) => (
                <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ResponsiveContainer>
      )
    }
    case 'line': {
      const xKey = chart.x_field ?? data.columns[0]
      const yKey = chart.y_field ?? data.columns[1]
      return (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={objects} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-tertiary)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line type="monotone" dataKey={yKey} stroke="#378ADD" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )
    }
    case 'stacked_bar': {
      const xKey = chart.x_field ?? data.columns[0]
      const seriesKey = chart.series_field ?? data.columns[1]
      const valueKey = chart.y_field ?? data.columns[2] ?? data.columns[1]
      // Pivot for stacking: gather distinct series values
      const series = Array.from(new Set(objects.map((o) => String(o[seriesKey] ?? ''))))
      const pivoted: Record<string, any>[] = []
      const xs = Array.from(new Set(objects.map((o) => String(o[xKey] ?? ''))))
      xs.forEach((x) => {
        const row: Record<string, any> = { [xKey]: x }
        series.forEach((s) => {
          const match = objects.find((o) => String(o[xKey]) === x && String(o[seriesKey]) === s)
          row[s] = match ? Number(match[valueKey]) || 0 : 0
        })
        pivoted.push(row)
      })
      return (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={pivoted} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-tertiary)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {series.map((s, i) => (
              <Bar key={s} dataKey={s} stackId="a" fill={PIE_COLORS[i % PIE_COLORS.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )
    }
    case 'bar':
    default: {
      const xKey = chart.x_field ?? data.columns[0]
      const yKey = chart.y_field ?? data.columns[1]
      return (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={objects} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-tertiary)" />
            <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey={yKey} fill="#378ADD" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )
    }
  }
}

const KpiCard: React.FC<{ chart: ChartSpec; data: AssistantData }> = ({ chart, data }) => {
  const valueField = chart.value_field ?? chart.y_field ?? data.columns[0]
  const idx = data.columns.indexOf(valueField)
  const value = idx >= 0 && data.rows.length > 0 ? data.rows[0][idx] : '—'
  return (
    <div className="kpi" style={{ marginTop: 4 }}>
      <div className="kl">{valueField}</div>
      <div className="kv">{value === null || value === undefined ? '—' : String(value)}</div>
    </div>
  )
}

const TableCard: React.FC<{ data: AssistantData }> = ({ data }) => (
  <div style={{ overflowX: 'auto', maxHeight: 320, overflowY: 'auto' }}>
    <table className="d">
      <thead>
        <tr>
          {data.columns.map((c) => (
            <th key={c}>{c}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.rows.map((row, i) => (
          <tr key={i}>
            {row.map((cell, j) => (
              <td key={j}>{cell === null || cell === undefined ? '' : String(cell)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)

function toObjects(data: AssistantData): Record<string, any>[] {
  return data.rows.map((row) => {
    const o: Record<string, any> = {}
    data.columns.forEach((c, i) => {
      o[c] = row[i]
    })
    return o
  })
}

export default AIInsightCard
