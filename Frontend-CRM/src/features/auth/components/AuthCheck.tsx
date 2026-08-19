import React, { useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'

/**
 * Spoke-SSO gate. Active only when VITE_IAM_AUTH_MODE='hub'.
 *
 * Reads `user` and `loading` from AuthContext, which hit GET /api/auth/me on
 * mount. Behavior:
 *   • loading            → spinner
 *   • user present       → render children
 *   • !loading && !user  → hard-redirect to /api/auth/login. Spoke backend
 *                          runs the OAuth 2.1 + PKCE handshake with the hub
 *                          (POST <hub>/api/oauth/token, then POST
 *                          <hub>/api/auth/verify), then redirects back to
 *                          the frontend root with the session cookie set.
 *
 * The lib/api.ts response interceptor also redirects on any in-app 401, so
 * mid-session expiry is covered too — no per-component handling needed.
 */
const apiBase = (
  ((import.meta as any).env?.VITE_API_BASE as string) || ''
).replace(/\/$/, '')
const ssoLoginUrl = `${apiBase}/auth/login`

interface Props {
  children: React.ReactNode
}

const AuthCheck: React.FC<Props> = ({ children }) => {
  const { user, loading } = useAuth()

  useEffect(() => {
    if (!loading && !user && typeof window !== 'undefined') {
      window.location.href = ssoLoginUrl
    }
  }, [loading, user])

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-[#168AAD]" />
          <p className="mt-4 text-gray-600">Checking your session…</p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}

export default AuthCheck
