/**
 * ISF Module Configuration
 * Adapted for CRM integration.
 *
 * API_URL is derived from the CRM's VITE_API_BASE environment variable
 * so all ISF API calls go to the same backend as the rest of the CRM.
 * When VITE_API_BASE is empty/unset, calls use a relative path (browser
 * resolves them against the current origin).
 */

// Enforce https:// for any non-localhost URL so a mis-configured env var
// (e.g. VITE_API_BASE=http://prod-host/api) can never cause Mixed Content errors.
function _enforceHttps(url) {
  if (!url) return url;
  const isLocal = url.includes('localhost') || url.includes('127.0.0.1');
  if (!isLocal && url.startsWith('http://')) {
    return url.replace('http://', 'https://');
  }
  return url;
}

const config = {
  // Use the same base URL as the CRM frontend (no separate ISF server).
  API_URL: _enforceHttps(import.meta.env.VITE_API_BASE || ''),

  // Token storage key — must match the CRM's AuthContext (uses 'auth_token').
  TOKEN_STORAGE_KEY: 'auth_token',
  USER_STORAGE_KEY: 'auth_user',

  // Google OAuth (kept for future use but not required for CRM integration)
  VITE_GOOGLE_CLIENT_ID: import.meta.env.VITE_GOOGLE_CLIENT_ID || '',
  VITE_GOOGLE_REDIRECT_URI: import.meta.env.VITE_GOOGLE_REDIRECT_URI || '',

  // Platform services URL (used only if auth.service.js standalone flow is invoked)
  PLATFORM_SERVICES_URL: _enforceHttps(import.meta.env.VITE_API_BASE || ''),

  // App ID for permission checking
  APP_ID: 'isf-module',
};

export { config };
export default config;
