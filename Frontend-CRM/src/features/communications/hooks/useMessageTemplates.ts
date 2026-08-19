import { useEffect, useState } from 'react'

export interface MessageTemplate {
  id: string
  name: string
  body: string
}

const STORAGE_KEY = 'crm.message-templates.v1'

const DEFAULTS: MessageTemplate[] = [
  {
    id: 'follow-up',
    name: 'Follow-up',
    body:
      "Hi {{name}}\n\nFollowing up on this — could you confirm next steps when you get a moment? Happy to set up a call if easier.\n\nThanks",
  },
  {
    id: 'site-activation',
    name: 'Site activation packet',
    body:
      "Hi {{name}}\n\nAttached is the site activation packet for your review. Please return the signed copy by {{due}}.\n\nLet me know if you have questions.",
  },
  {
    id: 'meeting-request',
    name: 'Schedule a call',
    body:
      "Hi {{name}}\n\nWould you have 15 minutes this week to align on the trial timeline? Open windows on my side are Tue/Wed PM.\n\nThanks",
  },
]

/**
 * Lightweight Phase-2 templates store. Persists to localStorage on this
 * device so users can iterate without a backend round-trip. When the team is
 * ready, lift this to a real `/templates` endpoint and adapt the same shape.
 */
export function useMessageTemplates() {
  const [templates] = useState<MessageTemplate[]>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as MessageTemplate[]
        if (Array.isArray(parsed) && parsed.length > 0) return parsed
      }
    } catch {
      /* ignore corrupted storage */
    }
    return DEFAULTS
  })

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(templates))
    } catch {
      /* ignore quota errors */
    }
  }, [templates])

  // NOTE: `setTemplates` is intentionally not exported — there is no template
  // editor surface yet. Add `add` / `remove` here when one ships.
  return { templates }
}

/** Substitute `{{name}}`, `{{due}}` etc. with values from `vars`. */
export function applyTemplate(body: string, vars: Record<string, string | undefined>): string {
  return body.replace(/\{\{(\w+)\}\}/g, (_, key) => vars[key] || `{{${key}}}`)
}
