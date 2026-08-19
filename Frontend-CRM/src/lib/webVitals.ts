/**
 * Real-user Core Web Vitals beacon.
 *
 * Sends LCP / INP / CLS / FCP / TTFB to the backend on `pagehide` /
 * visibility-change so we get a p75 from production traffic, not just lab
 * Lighthouse runs. The backend logs them; ship the log stream into Grafana /
 * Azure Monitor whenever we are ready.
 *
 * Cost is intentionally tiny: one fetch with `keepalive` per metric, no
 * library boilerplate beyond the official `web-vitals` package.
 *
 * Disabled in dev to avoid HMR noise (set VITE_REPORT_WEB_VITALS=true to
 * force-enable locally).
 */
import { onLCP, onINP, onCLS, onFCP, onTTFB, type Metric } from 'web-vitals'

/**
 * Resolve the beacon endpoint.
 *
 * Mirrors axios's baseURL convention in `lib/api.ts`: VITE_API_BASE is the
 * fully-qualified URL of the API root, which already includes the `/api`
 * prefix (e.g. `https://backend.../api` in prod, `/api` in dev). Path
 * suffixes in callers therefore do NOT include `/api`.
 *
 * Without this, prod was POSTing to the SWA static host (which returns 405
 * on unknown POSTs) instead of the backend App Service.
 *
 * If VITE_API_BASE is unset (some local dev setups), this beacon is also
 * gated off via `import.meta.env.PROD` below, so an unset env doesn't
 * generate broken requests.
 */
// Plain access — Vite inlines `import.meta.env.VITE_*` by literal pattern
// match. A defensive cast prevents the inlining and the value is empty in
// prod builds. Don't wrap this.
const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

// Same VITE_API_BASE-empty defense as in lib/realtime.ts: if the build was
// produced without VITE_API_BASE inlined, fall back to `${origin}/api` so the
// beacon at least targets a reasonable path. The reporter is gated on
// `import.meta.env.PROD` so a misconfigured dev build won't fire anyway, but
// a misconfigured SWA prod build will hit this path. The realtime.ts warning
// already alerts the operator; we don't double-log here to keep the console
// quiet for normal users.
const ENDPOINT = `${(API_BASE || `${typeof window !== 'undefined' ? window.location.origin : ''}/api`).replace(/\/$/, '')}/metrics/web-vitals`

function send(metric: Metric) {
  // navigationType only exists on newer Metric shapes; pull it defensively.
  const navType = (metric as unknown as { navigationType?: string }).navigationType ?? undefined
  const body = JSON.stringify({
    name: metric.name,
    value: metric.value,
    rating: metric.rating,
    id: metric.id,
    navigationType: navType,
    path: window.location.pathname,
  })

  // `sendBeacon` survives page unload but is fire-and-forget. It also works
  // cross-origin as long as the destination accepts the request (the backend
  // CORS config already allows POSTs from the SWA origin).
  try {
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: 'application/json' })
      const ok = navigator.sendBeacon(ENDPOINT, blob)
      if (ok) return
    }
  } catch {
    // ignore and fall through to fetch
  }

  try {
    void fetch(ENDPOINT, {
      method: 'POST',
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body,
      // Required for cross-origin POST without credentials. The beacon
      // doesn't need cookies — the backend route is unauthenticated.
      mode: 'cors',
      credentials: 'omit',
    })
  } catch {
    // Beacon failure must never throw into the app.
  }
}

let started = false

export function reportWebVitals() {
  if (started) return
  started = true

  const enabled =
    import.meta.env.PROD || import.meta.env.VITE_REPORT_WEB_VITALS === 'true'
  if (!enabled) return

  onLCP(send)
  onINP(send)
  onCLS(send)
  onFCP(send)
  onTTFB(send)
}
