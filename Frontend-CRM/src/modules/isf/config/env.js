/**
 * ISF environment config — all values come from Vite env vars.
 * Set them in .env (local) or your CI/CD environment (production).
 *
 * Required:
 *   VITE_API_BASE   — e.g. https://api.yourcrm.com/api   (production)
 *                     or   http://localhost:8000/api       (local dev)
 *
 * Optional (Google OAuth — only if Google login is used):
 *   VITE_GOOGLE_CLIENT_ID
 *   VITE_GOOGLE_REDIRECT_URI  — defaults to <current origin>/auth/google/callback
 */
function _enforceHttps(url) {
  if (!url) return url;
  const isLocal = url.includes('localhost') || url.includes('127.0.0.1');
  if (!isLocal && url.startsWith('http://')) {
    return url.replace('http://', 'https://');
  }
  return url;
}

const config = {
  // CRM API base — injected at build time; no localhost fallback in production.
  API_URL: _enforceHttps(import.meta.env.VITE_API_BASE || ''),

  // Google OAuth — only populated when the env var is explicitly set.
  VITE_GOOGLE_CLIENT_ID: import.meta.env.VITE_GOOGLE_CLIENT_ID || '',
  VITE_GOOGLE_REDIRECT_URI: import.meta.env.VITE_GOOGLE_REDIRECT_URI || '',

  GOOGLE_OAUTH: {
    CLIENT_ID: import.meta.env.VITE_GOOGLE_CLIENT_ID || '',
    // Redirect URI adapts automatically to whatever origin the app is served from.
    REDIRECT_URI: import.meta.env.VITE_GOOGLE_REDIRECT_URI
      || (typeof window !== 'undefined' ? `${window.location.origin}/auth/google/callback` : ''),
    SCOPE: 'openid email profile',
  },
};

export { config };
