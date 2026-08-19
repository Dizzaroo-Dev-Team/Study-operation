import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  ReactNode,
} from 'react'
import { api } from '../lib/api'
import sharedAuthService, {
  HubUser,
} from '../features/auth/services/sharedAuthService'

export interface User {
  user_id: string
  email: string
  name?: string
  role: string
  is_privileged: boolean
}

interface AuthContextType {
  user: User | null
  // Legacy bearer JWT. Always null in hub mode (cookie carries identity);
  // populated in local password mode by login() / signup(). Kept on the
  // interface for consumers (StudySiteContext, AskMeAnything, ConversationDetail,
  // ThreadDetail, TaskFormModal) that still destructure `token`.
  token: string | null
  login: (email: string, password: string) => Promise<void>
  signup: (
    user_id: string,
    name: string,
    email: string,
    password: string,
    role?: string,
  ) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}

// VITE_IAM_AUTH_MODE picks the auth flow:
//   * 'local' (dev default) → email+password Login form, JWT in localStorage.
//   * 'hub'   (prod)        → spoke-SSO flow. On mount we hit /api/auth/me;
//                              on 401 the lib/api interceptor (and AuthCheck)
//                              bounce to /api/auth/login, which is the spoke
//                              backend that runs the OAuth 2.1 + PKCE handshake
//                              with the hub. Identity rides on the HttpOnly
//                              session cookie set by /api/auth/callback.
const IAM_AUTH_MODE: string =
  ((import.meta as any).env?.VITE_IAM_AUTH_MODE as string) || 'local'
const HUB_MODE = IAM_AUTH_MODE === 'hub'

const apiBase = (
  ((import.meta as any).env?.VITE_API_BASE as string) || ''
).replace(/\/$/, '')
const ssoLogoutUrl = `${apiBase}/auth/logout`

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  useEffect(() => {
    if (HUB_MODE) {
      // Hub mode: ask the spoke backend who we are. The session cookie set by
      // /api/auth/callback carries identity — no JWT in localStorage.
      // A 401 here is intercepted in lib/api.ts and triggers a hard-redirect
      // to /api/auth/login (which runs PKCE against the hub), so we don't
      // handle the "not signed in" branch in React.
      let cancelled = false
      api
        .get('/auth/me')
        .then((r) => {
          if (!cancelled) setUser(r.data as User)
        })
        .catch(() => {
          // Non-401 failures (network, 5xx): leave user null; AuthCheck will
          // continue to render the spinner and the user can retry via reload.
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
      return () => {
        cancelled = true
      }
    }

    // Local mode: legacy JWT path — bootstrap from localStorage and revalidate.
    const storedToken = localStorage.getItem('auth_token')
    const storedUser = localStorage.getItem('auth_user')
    if (storedToken && storedUser) {
      setToken(storedToken)
      try {
        setUser(JSON.parse(storedUser))
        api
          .get('/auth/me')
          .then((response) => {
            setUser(response.data)
            localStorage.setItem('auth_user', JSON.stringify(response.data))
          })
          .catch(() => {
            logout()
          })
      } catch (e) {
        console.error('Error parsing stored user:', e)
        logout()
      }
    }
    setLoading(false)
  }, [])

  // Mirror the resolved user into the shared in-memory auth singleton.
  //
  // Why: drop-in modules (notably ISF) read the current user via
  // sharedAuthService, not React context. In hub mode the identity lives ONLY
  // in this provider's state (fetched from /auth/me) — it is never written to
  // localStorage (those keys are purged on cutover) nor to the singleton. That
  // left ISF's getCurrentUser() returning null, which surfaced as
  // "Your role (null) does not have access" on every workflow stage. Syncing
  // here keeps the singleton in step with context across hub AND local modes.
  useEffect(() => {
    if (user) {
      sharedAuthService.set({ user: user as unknown as HubUser })
    } else {
      sharedAuthService.clear()
    }
  }, [user])

  const login = useCallback(async (email: string, password: string) => {
    if (HUB_MODE) {
      throw new Error('Local password login is disabled in hub mode — use SSO.')
    }
    const formData = new FormData()
    formData.append('username', email)
    formData.append('password', password)
    try {
      const response = await api.post('/auth/login', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const { access_token, user: userData } = response.data
      setToken(access_token)
      setUser(userData)
      localStorage.setItem('auth_token', access_token)
      localStorage.setItem('auth_user', JSON.stringify(userData))
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Login failed')
    }
  }, [])

  const signup = useCallback(
    async (
      user_id: string,
      name: string,
      email: string,
      password: string,
      role: string = 'participant',
    ) => {
      if (HUB_MODE) {
        throw new Error('Local signup is disabled in hub mode — use SSO.')
      }
      try {
        const response = await api.post('/auth/signup', {
          user_id,
          name,
          email,
          password,
          role,
        })
        const { access_token, user: userData } = response.data
        setToken(access_token)
        setUser(userData)
        localStorage.setItem('auth_token', access_token)
        localStorage.setItem('auth_user', JSON.stringify(userData))
      } catch (error: any) {
        throw new Error(error.response?.data?.detail || 'Signup failed')
      }
    },
    [],
  )

  const logout = useCallback(() => {
    if (HUB_MODE) {
      // Full-page nav: spoke /auth/logout clears the session cookie and
      // bounces to the hub frontend /logout for global sign-out.
      window.location.href = ssoLogoutUrl
      return
    }
    setToken(null)
    setUser(null)
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
  }, [])

  const value = useMemo<AuthContextType>(
    () => ({ user, token, login, signup, logout, loading }),
    [user, token, login, signup, logout, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
