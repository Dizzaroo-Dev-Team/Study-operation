// Transport client for the agentic assistant.
//
// We use fetch-based SSE (not the EventSource API) so we can attach the bearer
// token as an Authorization header — EventSource cannot set headers, and the
// backend authenticates the stream with get_current_user like every other route.
//
// VITE_API_BASE already includes the `/api` suffix (see src/lib/api.ts).

const API_BASE = ((import.meta as any).env?.VITE_API_BASE as string) || ''

// Auth parity with src/lib/api.ts. Under the spoke-SSO flow (hub mode) the
// credential is an HttpOnly session cookie that must ride every cross-origin
// request — raw fetch() does NOT send it unless credentials: 'include' is set
// (this was the prod 401 on /assistant/stream). The localStorage bearer below
// covers local mode and is a no-op in hub mode.
const IAM_AUTH_MODE: string = ((import.meta as any).env?.VITE_IAM_AUTH_MODE as string) || 'local'
const FETCH_CREDENTIALS: RequestCredentials | undefined =
  IAM_AUTH_MODE === 'hub' ? 'include' : undefined

export type AssistantEvent = {
  type: 'ready' | 'token' | 'done' | 'error' | string
  text?: string
  message?: string
  [k: string]: unknown
}

function authHeaders(): Record<string, string> {
  try {
    const token = localStorage.getItem('auth_token')
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    return {}
  }
}

/**
 * Open the per-session SSE channel and invoke `onEvent` for each parsed event.
 * Resolves when the stream closes (server end or abort). Rejects on a failed
 * handshake so the caller can surface a connection error.
 */
export async function openAssistantStream(
  sessionId: string,
  onEvent: (e: AssistantEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const url = `${API_BASE}/assistant/stream?session_id=${encodeURIComponent(sessionId)}`
  const res = await fetch(url, {
    headers: { ...authHeaders(), Accept: 'text/event-stream' },
    credentials: FETCH_CREDENTIALS,
    signal,
  })
  if (!res.ok || !res.body) {
    throw new Error(`assistant stream failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE frames are separated by a blank line.
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      for (const line of frame.split('\n')) {
        if (!line.startsWith('data:')) continue // skip `:` keep-alive comments
        const payload = line.slice(5).trim()
        if (!payload) continue
        try {
          onEvent(JSON.parse(payload) as AssistantEvent)
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  }
}

/** Send a user message. The reply streams back over the SSE channel. */
export async function sendAssistantMessage(
  sessionId: string,
  text: string,
  screen?: string,
  catalog?: unknown,
  context?: { study_id?: string | null; site_id?: string | null },
  tours?: unknown,
  entities?: unknown,
  mode?: string,
  forms?: unknown,
  screenView?: { text: string; more_below: boolean; more_above: boolean },
  formView?: { id: string; label: string; visible_fields: string[]; hidden_fields: string[] }[],
): Promise<void> {
  const res = await fetch(`${API_BASE}/assistant/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    credentials: FETCH_CREDENTIALS,
    body: JSON.stringify({ session_id: sessionId, text, screen, catalog, context, tours, entities, mode, forms, screen_view: screenView, form_view: formView }),
  })
  if (!res.ok) {
    throw new Error(`assistant message failed: ${res.status}`)
  }
}

// ---------------------------------------------------------------------------
// Orbit derived memory
// ---------------------------------------------------------------------------

export type WelcomeBack = {
  returning: boolean
  memories: { id: string; type: string; text: string }[]
  last: { text: string } | null
}

export type MemoryItem = {
  id: string
  type: string
  text: string
  salience: number
  hits: number
  excluded: boolean
  created_at: string | null
}

/** Session-open welcome-back payload (memory recap + last-session hint). Never
 *  throws — a fresh/unauthenticated user just gets a cold open. */
export async function fetchWelcomeBack(): Promise<WelcomeBack> {
  const cold: WelcomeBack = { returning: false, memories: [], last: null }
  try {
    const res = await fetch(`${API_BASE}/assistant/memory/context`, { headers: { ...authHeaders() }, credentials: FETCH_CREDENTIALS })
    if (!res.ok) return cold
    return (await res.json()) as WelcomeBack
  } catch {
    return cold
  }
}

/** List the user's memories for the controls panel. */
export async function listMemories(): Promise<MemoryItem[]> {
  const res = await fetch(`${API_BASE}/assistant/memory`, { headers: { ...authHeaders() }, credentials: FETCH_CREDENTIALS })
  if (!res.ok) throw new Error(`list memories failed: ${res.status}`)
  return (await res.json()) as MemoryItem[]
}

export async function editMemory(id: string, text: string): Promise<void> {
  const res = await fetch(`${API_BASE}/assistant/memory/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    credentials: FETCH_CREDENTIALS,
    body: JSON.stringify({ text }),
  })
  if (!res.ok) throw new Error(`edit memory failed: ${res.status}`)
}

export async function excludeMemory(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/assistant/memory/${id}/exclude`, {
    method: 'POST',
    headers: { ...authHeaders() },
    credentials: FETCH_CREDENTIALS,
  })
  if (!res.ok) throw new Error(`exclude memory failed: ${res.status}`)
}

export async function deleteMemory(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/assistant/memory/${id}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
    credentials: FETCH_CREDENTIALS,
  })
  if (!res.ok) throw new Error(`delete memory failed: ${res.status}`)
}

/** Approve or cancel a pending write/regulated action. The paused turn resumes. */
export async function decideAssistantAction(
  sessionId: string,
  actionToken: string,
  approve: boolean,
): Promise<void> {
  const res = await fetch(`${API_BASE}/assistant/${approve ? 'approve' : 'cancel'}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    credentials: FETCH_CREDENTIALS,
    body: JSON.stringify({ session_id: sessionId, action_token: actionToken }),
  })
  if (!res.ok) {
    throw new Error(`assistant ${approve ? 'approve' : 'cancel'} failed: ${res.status}`)
  }
}
