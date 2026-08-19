/**
 * Shared real-time WebSocket client — TRUE multiplex.
 *
 * What it does
 * ------------
 * ONE WebSocket connection per browser session. All channel subscriptions
 * (conversations + threads) ride that single socket via the multi-subscribe
 * protocol exposed by the `/ws` backend endpoint (see communications.py).
 *
 *     ws send: {"action":"subscribe",  "kind":"conversation"|"thread", "id":"<uuid>"}
 *     ws send: {"action":"unsubscribe","kind":"conversation"|"thread", "id":"<uuid>"}
 *
 * Inbound events are routed by `conversation_id` or `thread_id` fields in
 * the payload (the backend already includes them on broadcasts). When no
 * routing field is present (subscribe ack, ping/pong, error), we fan out
 * to every listener of the matching channel — listeners are responsible
 * for filtering noise.
 *
 * Connection lifecycle
 * --------------------
 * - First subscribe opens the socket.
 * - Refcounted: last unsubscribe closes the socket.
 * - Reconnect with exponential backoff + jitter, capped at 5 attempts.
 * - On reconnect: re-send subscribe for every channel still referenced.
 * - Visibility-aware: hidden tab pauses reconnect; visible tab kicks one
 *   immediate retry and resets the attempt counter.
 *
 * Public API is unchanged from the pre-multiplex shape:
 *
 *     realtime.subscribe('conversation', id, cb) -> unsubscribe()
 *     useRealtime('conversation', id, cb)
 *
 * Migration recipe for callers — none required. ConversationDetail /
 * ThreadDetail already use useRealtime() (Hunt 4).
 */
import { useEffect, useRef } from 'react'
import sharedAuthService from '@/features/auth/services/sharedAuthService'

const IAM_AUTH_MODE: string =
  ((import.meta as any).env?.VITE_IAM_AUTH_MODE as string) || 'local'
const HUB_MODE = IAM_AUTH_MODE === 'hub'

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------
export type ChannelKind = 'conversation' | 'thread'

export interface RealtimeMessage {
  type?: string
  [key: string]: unknown
}

export type RealtimeListener = (event: RealtimeMessage) => void

interface ChannelState {
  kind: ChannelKind
  id: string
  listeners: Set<RealtimeListener>
}

const MAX_RECONNECT_ATTEMPTS = 5

// Resolve the WebSocket base URL.
//
// Vite inlines `VITE_API_BASE` at BUILD time — it's NOT a runtime value. If
// the SWA / dev build was made without it set, the bundle has an empty
// string here and we'd otherwise silently fall back to `window.location.host`,
// which serves static files and doesn't proxy `/ws` to the backend. That was
// the bug behind the prod "WebSocket is closed before connection" report.
//
// Behavior:
//   * VITE_API_BASE absolute (https://backend/api): rewrite to wss + '/ws'.
//   * VITE_API_BASE relative (/api): build from window.location with the
//     `/api` prefix preserved.
//   * VITE_API_BASE empty: assume the developer forgot to set it; default to
//     `${origin}/api/ws` and log a one-time warning so the misconfig is
//     visible in the console rather than silently breaking realtime.
function resolveWsBase(): string {
  // IMPORTANT: must be the plain `import.meta.env.VITE_API_BASE` access for
  // Vite to statically inline the value at build time. Earlier this file
  // wrapped the access in a TypeScript cast `(import.meta as unknown as ...)`
  // — Vite's plugin pattern-matches on the literal expression and the cast
  // prevented inlining, causing every prod build to fall through to the
  // empty-env branch and produce wss://<swa-host>/api/ws (broken).
  const apiBase: string = import.meta.env.VITE_API_BASE ?? ''

  if (apiBase.startsWith('http://') || apiBase.startsWith('https://')) {
    // Strip trailing slash on the apiBase so we don't produce `/api//ws`.
    return apiBase.replace(/^http/, 'ws').replace(/\/$/, '') + '/ws'
  }

  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  if (apiBase) {
    return `${wsProtocol}//${window.location.host}${apiBase.replace(/\/$/, '')}/ws`
  }

  // No VITE_API_BASE inlined at build time. Warn once and assume the backend
  // is reachable through the same origin at /api/ws (works for setups with a
  // reverse proxy in front of both; fails noisily for Azure SWA setups so
  // the deployer notices).
  if (!RESOLVE_WS_BASE_WARNED) {
    RESOLVE_WS_BASE_WARNED = true
    console.warn(
      '[realtime] VITE_API_BASE is empty at build time. Falling back to ' +
        `${wsProtocol}//${window.location.host}/api/ws — set VITE_API_BASE in your ` +
        'SWA build env (GitHub Action env block, or SWA Configuration) and rebuild.',
    )
  }
  return `${wsProtocol}//${window.location.host}/api/ws`
}

let RESOLVE_WS_BASE_WARNED = false

function getAuthToken(): string {
  // Hub mode keeps the token in memory via sharedAuthService; local mode keeps
  // it in localStorage. Read from whichever source matches the build's auth
  // mode so the WS handshake uses a fresh token after refresh / re-login.
  //
  // When no bearer token is available, return '' so the caller omits the
  // ?token=… query param entirely. In hub mode the SSO session cookie (sent
  // automatically on the WS handshake) authenticates the connection — the
  // earlier 'test' sentinel actively broke it by forcing the backend down the
  // bearer path with an invalid JWT.
  if (HUB_MODE) {
    return sharedAuthService.getToken() || ''
  }
  try {
    return localStorage.getItem('auth_token') || ''
  } catch {
    return ''
  }
}

function backoffMs(attempt: number): number {
  // 250ms, 500ms, 1s, 2s, 4s — capped, with ±20% jitter.
  const base = Math.min(250 * 2 ** attempt, 5000)
  const jitter = base * (Math.random() * 0.4 - 0.2)
  return Math.max(100, Math.round(base + jitter))
}

function channelKey(kind: ChannelKind, id: string): string {
  return `${kind}:${id}`
}

// Extract a routing target from an inbound event so we can dispatch to the
// right channel. Several wire shapes exist historically:
//   {type:'new_message',        conversation_id:'…', message:{…}}
//   {type:'new_thread_message', thread_id:'…',       message:{…}}
//   {type:'status_update',      message:{id, conversation_id, …}}
//   {status:'subscribed',       kind:'…', id:'…',    conversation_id:'…'}
// Returns a list of channel keys this event should be dispatched to.
function dispatchTargets(event: RealtimeMessage): string[] {
  const targets = new Set<string>()
  const conv =
    (event as any).conversation_id ??
    ((event as any).message && (event as any).message.conversation_id)
  if (conv) targets.add(channelKey('conversation', String(conv)))
  const thr =
    (event as any).thread_id ??
    ((event as any).message && (event as any).message.thread_id)
  if (thr) targets.add(channelKey('thread', String(thr)))
  // Subscribe-ack carries `kind` + `id` directly.
  if ((event as any).status === 'subscribed' || (event as any).status === 'unsubscribed') {
    const kind = (event as any).kind as ChannelKind | undefined
    const id = (event as any).id as string | undefined
    if (kind && id) targets.add(channelKey(kind, id))
  }
  return Array.from(targets)
}

class RealtimeClient {
  private channels = new Map<string, ChannelState>()
  private socket: WebSocket | null = null
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private connecting = false
  private visibilityListener: (() => void) | null = null
  private authUnsubscribe: (() => void) | null = null
  private lastKnownToken: string | null = null

  // ── Public API ────────────────────────────────────────────────────────

  subscribe(kind: ChannelKind, id: string, listener: RealtimeListener): () => void {
    if (!id) return () => {}

    const key = channelKey(kind, id)
    let ch = this.channels.get(key)
    if (!ch) {
      ch = { kind, id, listeners: new Set() }
      this.channels.set(key, ch)
      this.ensureSocket()
      this.sendSubscribeIfReady(kind, id)
    }
    ch.listeners.add(listener)
    this.ensureVisibilityHandler()
    this.ensureAuthSubscription()
    return () => this.unsubscribe(kind, id, listener)
  }

  /**
   * Tear down listeners and the active socket. Intended for HMR / test
   * teardown — production code does not call this (the client is a
   * module-level singleton that lives for the page lifetime).
   */
  dispose(): void {
    if (this.visibilityListener && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.visibilityListener)
      this.visibilityListener = null
    }
    if (this.authUnsubscribe) {
      try { this.authUnsubscribe() } catch { /* ignore */ }
      this.authUnsubscribe = null
    }
    this.channels.clear()
    this.closeSocket()
  }

  // ── Internal ──────────────────────────────────────────────────────────

  private unsubscribe(kind: ChannelKind, id: string, listener: RealtimeListener) {
    const key = channelKey(kind, id)
    const ch = this.channels.get(key)
    if (!ch) return
    ch.listeners.delete(listener)
    if (ch.listeners.size === 0) {
      this.channels.delete(key)
      this.sendUnsubscribeIfReady(kind, id)
      if (this.channels.size === 0) this.closeSocket()
    }
  }

  private ensureSocket() {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) return
    if (this.connecting) return
    this.connecting = true

    const tok = getAuthToken()
    const url = tok
      ? `${resolveWsBase()}?token=${encodeURIComponent(tok)}`
      : resolveWsBase()
    let s: WebSocket
    try {
      s = new WebSocket(url)
    } catch (err) {
      console.warn('[realtime] WebSocket constructor threw:', err)
      this.connecting = false
      this.scheduleReconnect()
      return
    }
    this.socket = s

    s.onopen = () => {
      this.connecting = false
      this.reconnectAttempts = 0
      // Re-subscribe every active channel so a reconnect transparently
      // restores state. New channels added between the constructor call
      // and the open event ride the same loop.
      for (const ch of this.channels.values()) {
        this.sendSubscribeIfReady(ch.kind, ch.id)
      }
    }

    s.onmessage = (ev) => {
      let parsed: RealtimeMessage
      try {
        parsed = JSON.parse(ev.data)
      } catch {
        return
      }
      const targets = dispatchTargets(parsed)
      if (targets.length === 0) {
        // No routing info — fan out to every listener so global events
        // (e.g. error responses without an id) still reach someone.
        for (const ch of this.channels.values()) {
          for (const cb of ch.listeners) {
            try {
              cb(parsed)
            } catch (err) {
              console.warn('[realtime] listener threw:', err)
            }
          }
        }
        return
      }
      for (const key of targets) {
        const ch = this.channels.get(key)
        if (!ch) continue
        for (const cb of ch.listeners) {
          try {
            cb(parsed)
          } catch (err) {
            console.warn('[realtime] listener threw:', err)
          }
        }
      }
    }

    s.onclose = () => {
      this.socket = null
      this.connecting = false
      if (this.channels.size === 0) return
      if (document.visibilityState !== 'visible') return
      this.scheduleReconnect()
    }

    s.onerror = () => {
      // onclose follows; reconnect lives there.
    }
  }

  private closeSocket() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.socket) {
      try {
        this.socket.close()
      } catch {
        // ignore
      }
      this.socket = null
    }
    this.connecting = false
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.warn('[realtime] hit max reconnect attempts')
      return
    }
    const delay = backoffMs(this.reconnectAttempts)
    this.reconnectAttempts += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (this.channels.size > 0) this.ensureSocket()
    }, delay)
  }

  private sendSubscribeIfReady(kind: ChannelKind, id: string) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return
    try {
      // We include the legacy `conversation_id` field too so a server
      // running the pre-multi-subscribe code (rare during a deploy
      // window) still understands the message.
      this.socket.send(
        JSON.stringify({
          action: 'subscribe',
          kind,
          id,
          conversation_id: id,
        }),
      )
    } catch (err) {
      console.warn('[realtime] subscribe send failed:', err)
    }
  }

  private sendUnsubscribeIfReady(kind: ChannelKind, id: string) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return
    try {
      this.socket.send(
        JSON.stringify({
          action: 'unsubscribe',
          kind,
          id,
          conversation_id: id,
        }),
      )
    } catch {
      // ignore — server will drop the channel when the socket eventually
      // closes anyway.
    }
  }

  private ensureVisibilityHandler() {
    if (this.visibilityListener) return
    if (typeof document === 'undefined') return
    // Store the listener as a field so dispose() can remove it. Anonymous
    // closures in addEventListener cannot be removed later, which used to
    // accumulate one listener per HMR cycle in dev.
    this.visibilityListener = () => {
      if (document.visibilityState !== 'visible') return
      this.reconnectAttempts = 0
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer)
        this.reconnectTimer = null
      }
      if (this.channels.size > 0) this.ensureSocket()
    }
    document.addEventListener('visibilitychange', this.visibilityListener)
  }

  private ensureAuthSubscription() {
    if (this.authUnsubscribe) return
    this.lastKnownToken = getAuthToken()
    if (!HUB_MODE) {
      // Local mode keeps the token in localStorage; cross-tab logout fires a
      // `storage` event. Close the socket so the next subscribe reconnects
      // with whatever token is now in localStorage (or 'test' if cleared).
      const onStorage = (ev: StorageEvent) => {
        if (ev.key !== 'auth_token') return
        const current = getAuthToken()
        if (current === this.lastKnownToken) return
        this.lastKnownToken = current
        this.recycleSocketForAuthChange()
      }
      window.addEventListener('storage', onStorage)
      this.authUnsubscribe = () => window.removeEventListener('storage', onStorage)
      return
    }
    // Hub mode: subscribe to sharedAuthService changes. When the token
    // rotates (refresh or logout) we close the current socket so the
    // reconnect path picks up the fresh token via getAuthToken().
    const unsubscribe = sharedAuthService.subscribe(() => {
      const current = getAuthToken()
      if (current === this.lastKnownToken) return
      this.lastKnownToken = current
      this.recycleSocketForAuthChange()
    })
    this.authUnsubscribe = unsubscribe
  }

  private recycleSocketForAuthChange() {
    // Close the current socket (if any) and reset reconnect bookkeeping so
    // the next reconnect attempt uses a fresh token from getAuthToken().
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.reconnectAttempts = 0
    if (this.socket) {
      try { this.socket.close() } catch { /* ignore */ }
      this.socket = null
    }
    this.connecting = false
    if (this.channels.size > 0) this.ensureSocket()
  }
}

export const realtime = new RealtimeClient()

// Tear down the singleton on HMR so listeners don't pile up across hot
// reloads. Production builds skip this branch.
if ((import.meta as any).hot) {
  ;(import.meta as any).hot.dispose(() => {
    try { realtime.dispose() } catch { /* ignore */ }
  })
}

// -----------------------------------------------------------------------------
// React hook
// -----------------------------------------------------------------------------
export function useRealtime(
  kind: ChannelKind,
  id: string | null | undefined,
  listener: RealtimeListener,
) {
  const listenerRef = useRef(listener)
  listenerRef.current = listener

  useEffect(() => {
    if (!id) return
    const cb: RealtimeListener = (event) => listenerRef.current(event)
    return realtime.subscribe(kind, id, cb)
  }, [kind, id])
}
