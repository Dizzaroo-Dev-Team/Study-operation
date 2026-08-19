/**
 * sharedAuthService — singleton for hub-issued auth state.
 *
 * Holds {user, token, applications} in module-level memory (NOT localStorage —
 * hub policy and the Neurodoc reference flow both require an in-memory session).
 * Subscribers (AuthContext) listen via subscribe() to re-render on change.
 *
 * Responsibilities:
 *   • parseAuthParam — read ?auth=<json> from the URL after a hub redirect,
 *     populate the session, then strip the param via history.replaceState.
 *   • verifyWithHub — validate an in-memory token by calling hub /api/auth/verify.
 *   • hydrateFromCookie — best-effort cross-origin call with credentials:'include'.
 *     Hub must set CORS Access-Control-Allow-Origin + Allow-Credentials for our
 *     origin AND SameSite=None;Secure cookies, otherwise this fails silently and
 *     callers should fall back to redirectToHubLogin.
 *   • redirectToHubLogin / redirectToHubLogout.
 */

export interface HubApplication {
  key: string;
  isActive?: boolean;
  [k: string]: unknown;
}

export interface HubUser {
  user_id?: string;
  userId?: string;
  id?: string;
  email?: string;
  name?: string;
  displayName?: string;
  role?: string;
  hub_roles?: string | string[];
  applications?: HubApplication[];
  is_privileged?: boolean | string;
  [k: string]: unknown;
}

export interface AuthSession {
  user: HubUser | null;
  token: string | null;
  applications: HubApplication[];
}

const HUB_BASE: string =
  (import.meta as any).env?.VITE_HUB_BASE_URL ||
  'https://punk-reunite-sage.ngrok-free.dev';

const APP_KEY: string =
  (import.meta as any).env?.VITE_IAM_APPLICATION_ID || 'study_operations';

const VERIFY_PATH = '/api/auth/verify';
const LOGIN_PATH = '/login';
const LOGOUT_PATH = '/api/auth/logout'; // POST per hub contract

const NGROK_BYPASS_HEADER = { 'ngrok-skip-browser-warning': '1' };

// ─── State + subscribers ──────────────────────────────────────────────────────

let _session: AuthSession = { user: null, token: null, applications: [] };
const _listeners = new Set<(s: AuthSession) => void>();

function _notify() {
  for (const l of _listeners) {
    try {
      l(_session);
    } catch {
      /* swallow listener errors */
    }
  }
}

function _normaliseApplications(payload: any): HubApplication[] {
  const raw =
    payload?.applications ?? payload?.user?.applications ?? [];
  if (!Array.isArray(raw)) return [];
  return raw
    .map((entry: any) => {
      if (entry && typeof entry === 'object') return entry as HubApplication;
      if (typeof entry === 'string') return { key: entry, isActive: true };
      return null;
    })
    .filter((x: HubApplication | null): x is HubApplication => Boolean(x?.key));
}

function _normaliseUser(payload: any): HubUser | null {
  if (!payload) return null;
  if (payload.user && typeof payload.user === 'object') return payload.user as HubUser;
  if (typeof payload === 'object') return payload as HubUser;
  return null;
}

// ─── Public API ───────────────────────────────────────────────────────────────

export const sharedAuthService = {
  hubBaseUrl: HUB_BASE,
  applicationKey: APP_KEY,

  get(): AuthSession {
    return _session;
  },
  getUser(): HubUser | null {
    return _session.user;
  },
  getToken(): string | null {
    return _session.token;
  },
  getApplications(): HubApplication[] {
    return _session.applications;
  },
  hasEntitlement(): boolean {
    const target = APP_KEY.toLowerCase();
    return _session.applications.some((a) => {
      // The hub may identify our app via `key`, `code`, or `application_key`.
      // Match any of them, case-insensitively.
      const candidates = [
        (a as any).key,
        (a as any).code,
        (a as any).application_key,
        (a as any).appKey,
        (a as any).applicationKey,
      ]
        .map((v) => String(v ?? '').toLowerCase())
        .filter(Boolean);
      return candidates.includes(target) && a.isActive !== false;
    });
  },

  set(next: Partial<AuthSession>): void {
    _session = {
      user: next.user ?? _session.user,
      token: next.token ?? _session.token,
      applications:
        next.applications ?? _session.applications ?? [],
    };
    _notify();
  },

  clear(): void {
    _session = { user: null, token: null, applications: [] };
    _notify();
  },

  subscribe(listener: (s: AuthSession) => void): () => void {
    _listeners.add(listener);
    return () => {
      _listeners.delete(listener);
    };
  },

  /**
   * Read `?auth=<urlencoded-json>` from the current URL. If present, parse it,
   * populate the in-memory session, and strip the param from the URL bar
   * (history.replaceState — keeps tokens out of bookmarks/history).
   * Returns true when a session was established from the URL.
   */
  parseAuthParam(): boolean {
    if (typeof window === 'undefined') return false;
    const url = new URL(window.location.href);
    const raw = url.searchParams.get('auth');
    if (!raw) return false;

    try {
      const parsed = JSON.parse(decodeURIComponent(raw));
      const user = _normaliseUser(parsed);
      const token = parsed?.token || parsed?.access_token || null;
      const applications = _normaliseApplications(parsed);
      if (!token || !user) return false;
      _session = { user, token, applications };
    } catch {
      return false;
    } finally {
      url.searchParams.delete('auth');
      const cleaned = url.pathname + (url.search ? url.search : '') + url.hash;
      try {
        window.history.replaceState({}, '', cleaned);
      } catch {
        /* ignore — non-browser env */
      }
    }
    _notify();
    return true;
  },

  /**
   * Validate the in-memory token by hitting the hub. Returns the verify
   * payload on success, null on rejection or network error.
   */
  async verifyWithHub(token?: string | null): Promise<any | null> {
    const t = token ?? _session.token;
    if (!t) return null;
    try {
      const resp = await fetch(`${HUB_BASE}${VERIFY_PATH}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${t}`,
          Accept: 'application/json',
          ...NGROK_BYPASS_HEADER,
        },
        credentials: 'include',
      });
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  },

  /**
   * No-token bootstrap: ask the hub if we have a valid session cookie.
   * Best-effort — if hub CORS isn't configured for our origin in dev, this
   * silently returns null and callers should redirect to hub login instead.
   */
  async hydrateFromCookie(): Promise<any | null> {
    try {
      const resp = await fetch(`${HUB_BASE}${VERIFY_PATH}`, {
        method: 'POST',
        headers: { Accept: 'application/json', ...NGROK_BYPASS_HEADER },
        credentials: 'include',
      });
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  },

  /**
   * Apply a verify response to the in-memory session.
   * Pulls the token out of the response if present, otherwise keeps the
   * existing in-memory token.
   */
  applyVerifyResponse(payload: any): void {
    const user = _normaliseUser(payload);
    const applications = _normaliseApplications(payload);
    const token =
      (payload && (payload.token || payload.access_token)) ?? _session.token;
    _session = { user, token, applications };
    _notify();
  },

  redirectToHubLogin(returnUrl?: string): void {
    if (typeof window === 'undefined') return;
    const ru = encodeURIComponent(returnUrl ?? window.location.href);
    window.location.href = `${HUB_BASE}${LOGIN_PATH}?returnUrl=${ru}`;
  },

  /**
   * Hub-mode logout. Calls the hub's `POST /api/auth/logout` (sends bearer
   * token + cookies so the hub can invalidate both), then clears the
   * in-memory session and bounces the browser to the hub login page so the
   * user can sign back in if they want.
   *
   * The fetch is best-effort — if the hub is unreachable we still clear the
   * local session and redirect (a stale hub session on the next login will
   * pick up automatically when the cookie is fresh).
   */
  async logout(): Promise<void> {
    const token = _session.token;
    try {
      await fetch(`${HUB_BASE}${LOGOUT_PATH}`, {
        method: 'POST',
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          Accept: 'application/json',
          ...NGROK_BYPASS_HEADER,
        },
        credentials: 'include',
      });
    } catch {
      /* swallow — logout should never block redirect */
    }
    _session = { user: null, token: null, applications: [] };
    _notify();
    this.redirectToHubLogin();
  },

  /** Legacy / non-async callers — fire-and-forget wrapper around `logout()`. */
  redirectToHubLogout(): void {
    void this.logout();
  },
};

/**
 * One-shot migration that runs on module import (hub mode only): shed legacy
 * `auth_token` / `auth_user` keys from the previous local-only auth flow so a
 * stale browser doesn't keep replaying old JWTs after the SSO cutover.
 *
 * Local mode keeps these keys intact — Login.tsx still writes them.
 */
function _cleanupLegacyLocalStorageKeys() {
  if (typeof window === 'undefined' || !window.localStorage) return;
  const mode = (import.meta as any).env?.VITE_IAM_AUTH_MODE;
  if (mode !== 'hub') return;
  for (const k of [
    'auth_token',
    'auth_user',
    'token',
    'authToken',
    'user',
    'crmTokenKey',
    'crmUserKey',
  ]) {
    try {
      window.localStorage.removeItem(k);
    } catch {
      /* ignore */
    }
  }
}

_cleanupLegacyLocalStorageKeys();

export default sharedAuthService;
