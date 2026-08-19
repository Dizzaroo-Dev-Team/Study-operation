import React, { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'

interface TemplateDocxViewerProps {
  templateId: string
  templateName?: string
}

async function blobFromTemplateResponse(res: { data: Blob; headers: Record<string, unknown> }): Promise<Blob> {
  const blob = res.data
  const contentType = String(res.headers['content-type'] || '')
  if (contentType.includes('application/json') || (blob.type && blob.type.includes('json'))) {
    const text = await blob.text()
    try {
      const parsed = JSON.parse(text)
      const detail = parsed?.detail
      throw new Error(typeof detail === 'string' ? detail : text || 'Failed to load template file')
    } catch (e) {
      if (e instanceof Error && e.message !== 'Failed to load template file') throw e
      throw new Error(text || 'Failed to load template file')
    }
  }
  return blob
}

/**
 * Read-only DOCX preview for study templates (Template Library "View").
 * Uses docx-preview — not OnlyOffice.
 */
const TemplateDocxViewer: React.FC<TemplateDocxViewerProps> = ({
  templateId,
  templateName,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!templateId) return

    const container = containerRef.current
    if (!container) return

    let cancelled = false

    const load = async () => {
      setLoading(true)
      setError(null)
      container.innerHTML = ''

      try {
        const res = await api.get(`/templates/${templateId}/template-file`, {
          responseType: 'blob',
        })
        const blob = await blobFromTemplateResponse(res)
        if (!blob || blob.size === 0) {
          throw new Error('Template file is empty')
        }

        const header = new Uint8Array(await blob.slice(0, 4).arrayBuffer())
        const isZip = header[0] === 0x50 && header[1] === 0x4b
        if (!isZip) {
          throw new Error('The file is not a valid DOCX document')
        }

        if (cancelled) return

        const { renderAsync } = await import('docx-preview')
        await renderAsync(blob, container, undefined, {
          className: 'docx-preview-wrapper',
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          breakPages: true,
          renderHeaders: true,
          renderFooters: true,
        })
      } catch (err: unknown) {
        if (!cancelled) {
          const ax = err as { response?: { data?: { detail?: string } }; message?: string }
          const detail = ax?.response?.data?.detail
          const message =
            typeof detail === 'string'
              ? detail
              : err instanceof Error
                ? err.message
                : 'Failed to load template preview'
          setError(message)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [templateId])

  return (
    <div className="relative h-full w-full overflow-auto bg-white p-4">
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-white">
          <p className="text-sm text-gray-600">Loading document preview…</p>
        </div>
      )}

      {error && !loading && (
        <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-3 p-8 text-center">
          <p className="text-sm font-medium text-red-700">{error}</p>
          <p className="text-xs text-gray-500">
            {templateName ? `"${templateName}"` : 'Template'} could not be previewed.
          </p>
        </div>
      )}

      <div
        ref={containerRef}
        className={`w-full min-h-full ${error ? 'hidden' : ''}`}
        aria-hidden={Boolean(error)}
      />
      {!error && (
        <style>{`
          .docx-preview-wrapper { padding: 20px; background: white; }
          .docx-preview-wrapper .docx-wrapper {
            background: white;
            padding: 20px;
            margin: 0 auto;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
          }
          .docx-preview-wrapper .docx-wrapper > section.docx {
            margin-bottom: 20px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.1);
          }
        `}</style>
      )}
    </div>
  )
}

export default TemplateDocxViewer
