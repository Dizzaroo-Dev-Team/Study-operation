// src/lib/api.ts
import axios from 'axios'

const apiBase = (
  ((import.meta as any).env?.VITE_API_BASE as string) || ''
).replace(/\/$/, '')

const IAM_AUTH_MODE: string =
  ((import.meta as any).env?.VITE_IAM_AUTH_MODE as string) || 'local'
const HUB_MODE = IAM_AUTH_MODE === 'hub'

// `withCredentials: true` is mandatory under the spoke-SSO flow — the
// HttpOnly session cookie set by /api/auth/callback must ride every
// cross-origin request from study-operation.dizzaroo.com to
// api-study-operation.dizzaroo.com. Harmless in local mode.
export const api = axios.create({
  baseURL: apiBase,
  withCredentials: HUB_MODE,
})

// Legacy bearer JWT attach. Cookies cover the new SSO flow, but a few drop-in
// modules (ISF, token-gated public pages like /agreement/sign/*) and the
// local password flow still mint short-lived JWTs in localStorage. Safe no-op
// when nothing is stored.
api.interceptors.request.use((config) => {
  try {
    const token = localStorage.getItem('auth_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  } catch {
    /* ignore — non-browser env or storage disabled */
  }
  // Prevent browser ETag replay (304 with empty body breaks axios JSON parsing).
  if ((config.method || 'get').toLowerCase() === 'get') {
    config.headers['Cache-Control'] = 'no-cache'
    config.headers['Pragma'] = 'no-cache'
  }
  return config
})

// 401 handling.
//   * Hub mode → hard-redirect to /api/auth/login (the spoke route that
//                triggers OAuth 2.1 + PKCE against the hub). Backend runs the
//                whole handshake server-side; the frontend is never directly
//                redirected to the hub frontend.
//   * Local mode → wipe stale JWT and reload so AuthContext re-bootstraps
//                  empty and ProtectedShell renders <Login>.
// `_redirectingForAuth` guards against the storm of 401s a stale session
// triggers (every queued request fails at once) — we only want one redirect.
const ssoLoginUrl = `${apiBase}/auth/login`
let _redirectingForAuth = false

function _handleUnauthorized() {
  if (_redirectingForAuth) return
  _redirectingForAuth = true
  try {
    if (HUB_MODE) {
      if (typeof window !== 'undefined') {
        window.location.href = ssoLoginUrl
      }
      return
    }
    try { localStorage.removeItem('auth_token') } catch { /* ignore */ }
    try { localStorage.removeItem('auth_user') } catch { /* ignore */ }
    if (typeof window !== 'undefined') {
      // Reload re-mounts AuthContext with empty localStorage, which makes
      // ProtectedShell render the Login form on the next render pass.
      window.location.reload()
    }
  } catch {
    if (typeof window !== 'undefined') window.location.reload()
  }
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      _handleUnauthorized()
    }
    return Promise.reject(error)
  },
)

// Flatten an axios/FastAPI error into a single human-readable string.
// FastAPI 422 responses set `detail` to an array of objects like
// `[{type, loc, msg, input}]`; rendering that directly in JSX crashes React.
export function extractApiError(err: any, fallback = 'Request failed'): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => {
        if (typeof d === 'string') return d
        const loc = Array.isArray(d?.loc) ? d.loc.join('.') : ''
        const msg = d?.msg || d?.message || ''
        return loc ? `${loc}: ${msg}` : msg
      })
      .filter(Boolean)
      .join('; ') || fallback
  }
  if (detail && typeof detail === 'object') {
    return detail.msg || detail.message || JSON.stringify(detail)
  }
  return err?.message || fallback
}
