/**
 * SourceDriftPanel (#6) — a WARN surface for source-backed fields whose value in the
 * document differs from the live source data (the user edited it, or the source moved on).
 *
 * GENERAL: works for any source-backed field / agreement type — the backend decides what
 * is source-backed; this just lists drift and lets the user choose per field to KEEP their
 * edit (default, do nothing) or USE the SOURCE value. Unobtrusive: renders nothing when
 * there is no drift. The edit is valid — this never blocks; it only flags.
 */
import React, { useState } from 'react'
import BrandButton from '@/components/ui/BrandButton'
import { useSourceDrift, usePullSourceValues } from '@/lib/queries/useSourceDrift'

interface SourceDriftPanelProps {
  agreementId: string | null | undefined
}

const SourceDriftPanel: React.FC<SourceDriftPanelProps> = ({ agreementId }) => {
  const { data, isLoading, isError } = useSourceDrift(agreementId)
  const pull = usePullSourceValues(agreementId)
  const [selected, setSelected] = useState<Record<string, boolean>>({})

  const drifted = data?.drifted ?? []
  // Unobtrusive: nothing to show unless there is actual drift.
  if (isLoading || isError || drifted.length === 0) return null

  const toggle = (token: string) =>
    setSelected((s) => ({ ...s, [token]: !s[token] }))

  const chosen = drifted.filter((f) => selected[f.token]).map((f) => f.token)

  const pullSelected = async () => {
    if (chosen.length === 0) return
    try {
      await pull.mutateAsync(chosen)
      setSelected({})
    } catch {
      /* error surfaced via pull.isError below; keep selection so the user can retry */
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
      <div className="flex items-start gap-2">
        <span aria-hidden className="mt-0.5 text-amber-600">⚠️</span>
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-amber-900">
            {drifted.length} field{drifted.length > 1 ? 's' : ''} differ from the source data
          </h4>
          <p className="mt-0.5 text-xs text-amber-800">
            These fields were filled from a data source but now differ from it. Your edits are
            kept by default — tick a field and choose “Use source value” only if you want to
            pull the current source value back in.
          </p>

          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-amber-900/70">
                  <th className="w-8 py-1" />
                  <th className="py-1 pr-3 font-semibold">Field</th>
                  <th className="py-1 pr-3 font-semibold">Your edit (in document)</th>
                  <th className="py-1 pr-3 font-semibold">Source value</th>
                </tr>
              </thead>
              <tbody>
                {drifted.map((f) => (
                  <tr key={f.token} className="border-t border-amber-200 align-top">
                    <td className="py-1.5">
                      <input
                        type="checkbox"
                        aria-label={`Use source value for ${f.token}`}
                        checked={Boolean(selected[f.token])}
                        onChange={() => toggle(f.token)}
                      />
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-amber-900">{f.token}</td>
                    <td className="py-1.5 pr-3 text-gray-700">{f.doc_value || <em>(empty)</em>}</td>
                    <td className="py-1.5 pr-3 text-gray-700">{f.source_value || <em>(empty)</em>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center gap-3">
            <BrandButton
              variant="outline"
              size="sm"
              onClick={pullSelected}
              disabled={chosen.length === 0 || pull.isPending}
              className="disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {pull.isPending
                ? 'Updating…'
                : `Use source value${chosen.length ? ` for ${chosen.length} selected` : ''}`}
            </BrandButton>
            <span className="text-xs text-amber-800">Unselected fields keep your edit.</span>
          </div>

          {pull.isError && (
            <p className="mt-2 text-xs text-red-600">
              Could not update from source. Please try again.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default SourceDriftPanel
