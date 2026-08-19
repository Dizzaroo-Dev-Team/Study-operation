import React, { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { StudySiteProvider } from './contexts/StudySiteContext'
import { ThemeProvider } from './providers/ThemeProvider'
import { queryClient } from './lib/queryClient'
import AppLayout from './layouts/AppLayout'
import UnifiedInbox from '@/features/communications/components/UnifiedInbox'
import CommandPalette from './components/CommandPalette'
import AssistantWidget from '@/features/assistant/components/AssistantWidget'
import AuthCheck from '@/features/auth/components/AuthCheck'
import Login from '@/features/auth/components/Login'
import Signup from '@/features/auth/components/Signup'
import { Toaster } from './components/Toaster'
import './App.css'

// Public (token-gated) pages are lazy-loaded: a user only ever hits one of
// these per visit, and they're cleanly isolated from the protected app shell.
const FeasibilityForm = lazy(() => import('@/features/feasibility/components/FeasibilityForm'))
const AgreementReviewPage = lazy(() => import('@/features/agreements/components/AgreementReviewPage'))
const AgreementSignPage = lazy(() => import('@/features/agreements/components/AgreementSignPage'))
const VisitReschedulePage = lazy(() => import('@/features/monitoring/components/VisitReschedulePage'))
const VisitReportReviewPage = lazy(() => import('@/features/monitoring/components/VisitReportReviewPage'))
const VisitConfirmationPage = lazy(() => import('@/features/monitoring/components/VisitConfirmationPage'))
const PreVisitAcknowledgePage = lazy(() => import('@/features/monitoring/components/PreVisitAcknowledgePage'))
const AcknowledgeReceipt = lazy(() => import('./components/AcknowledgeReceipt'))
// Workflow task inbox (my open steps across instances) + per-instance runner page.
const WorkflowInboxPage = lazy(() => import('@/features/workflows/inbox/WorkflowInboxPage'))
const WorkflowInstancePage = lazy(() => import('@/features/workflows/WorkflowInstancePage'))

// Clause Library — template builder (full-page, CLAUSE_COMPOSED templates only).
const TemplateBuilderPage = lazy(() => import('@/features/agreements/components/TemplateBuilderPage'))

// Orbit live-eval dashboard (read-only scores + judge reasons; in-house only).
const LiveEvalDashboardPage = lazy(() => import('@/features/live-evals/components/LiveEvalDashboardPage'))

// Use relative path for Vite proxy, or absolute URL if explicitly set
const API_BASE = (import.meta as any).env?.VITE_API_BASE

const IAM_AUTH_MODE: string =
  ((import.meta as any).env?.VITE_IAM_AUTH_MODE as string) || 'local'
const HUB_MODE = IAM_AUTH_MODE === 'hub'

type Mode =
  | 'dashboard'
  | 'conversations'
  | 'threads'
  | 'site-profile'
  | 'site-staff-details'
  | 'irb-administrative-info'
  | 'site-status'
  | 'monitoring'
  | 'documents'
  | 'study-setup'
  | 'tasks'

const pathToMode = (pathname: string): Mode | null => {
  if (pathname === '/monitoring') return 'monitoring'
  if (pathname === '/forms/site-profile') return 'site-profile'
  if (pathname === '/forms/site-staff-details') return 'site-staff-details'
  if (pathname === '/forms/irb-administrative-info') return 'irb-administrative-info'
  return null
}

const modeToPath = (mode: Mode): string | null => {
  if (mode === 'monitoring') return '/monitoring'
  if (mode === 'site-profile') return '/forms/site-profile'
  if (mode === 'site-staff-details') return '/forms/site-staff-details'
  if (mode === 'irb-administrative-info') return '/forms/irb-administrative-info'
  return null
}

const RouteSpinner: React.FC = () => (
  <div className="min-h-screen flex items-center justify-center bg-gray-50">
    <div className="text-center">
      <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-dizzaroo-deep-blue"></div>
      <p className="mt-4 text-gray-600">Loading...</p>
    </div>
  </div>
)

// Protected tree: auth check, layout, and the UnifiedInbox mode router.
// This is the catch-all route - everything that isn't a public page lands here.
const ProtectedShell: React.FC = () => {
  const { user, loading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [showSignup, setShowSignup] = useState(false)
  const [currentMode, setCurrentModeRaw] = useState<Mode>(() => {
    const valid: Mode[] = [
      'dashboard', 'conversations', 'threads',
      'site-profile', 'site-staff-details', 'irb-administrative-info',
      'site-status', 'monitoring', 'documents', 'study-setup',
      'tasks',
    ]
    const isFreshOpen =
      typeof window !== 'undefined' && !sessionStorage.getItem('crm.sessionOpened')
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('crm.sessionOpened', '1')
    }

    // Fresh tab/window -> always land on dashboard, clean the URL.
    if (isFreshOpen) {
      if (typeof window !== 'undefined' && pathToMode(window.location.pathname)) {
        window.history.replaceState({}, '', '/')
      }
      return 'dashboard'
    }

    // Refresh in same tab -> keep whatever page user was on.
    const fromPath = pathToMode(window.location.pathname)
    if (fromPath) return fromPath
    const stored = (typeof window !== 'undefined' ? localStorage.getItem('crm.lastModule') : null) as Mode | null
    if (stored && valid.includes(stored)) return stored
    return 'dashboard'
  })
  const setCurrentMode: React.Dispatch<React.SetStateAction<Mode>> = (value) => {
    setCurrentModeRaw((prev) => {
      const next = typeof value === 'function' ? (value as (p: Mode) => Mode)(prev) : value
      if (typeof window !== 'undefined') localStorage.setItem('crm.lastModule', next)
      return next
    })
  }

  // Sync mode from URL whenever the route changes (back/forward + initial mount).
  useEffect(() => {
    const mapped = pathToMode(location.pathname)
    if (mapped) {
      setCurrentMode(mapped)
    }
  }, [location.pathname])

  // On login (false -> true transition of `user`), land on Dashboard regardless
  // of whatever the previous session's last module was.
  //
  // Exception: if a one-shot `crm.landOn` intent was stashed by an in-app
  // deep link (e.g., the CTA notification inbox), honour it and clear the
  // intent so the override only fires once.
  const wasAuthed = useRef<boolean>(!!user)
  useEffect(() => {
    if (user && !wasAuthed.current) {
      const validModes = new Set<Mode>([
        'dashboard', 'conversations', 'threads',
        'site-profile', 'site-staff-details', 'irb-administrative-info',
        'site-status', 'monitoring', 'documents', 'study-setup',
        'tasks',
      ])
      let intent: Mode | null = null
      try {
        const raw = localStorage.getItem('crm.landOn')
        if (raw && validModes.has(raw as Mode)) {
          intent = raw as Mode
        }
        localStorage.removeItem('crm.landOn')
      } catch {
        /* ignore storage errors */
      }
      if (intent) {
        setCurrentMode(intent)
      } else if (!pathToMode(window.location.pathname)) {
        setCurrentMode('dashboard')
      }
    }
    wasAuthed.current = !!user
  }, [user])

  if (loading) {
    return <RouteSpinner />
  }

  if (!HUB_MODE && !user) {
    return showSignup ? (
      <Signup onSwitchToLogin={() => setShowSignup(false)} />
    ) : (
      <Login onSwitchToSignup={() => setShowSignup(true)} />
    )
  }

  const handleModeChange = (mode: string) => {
    const nextMode = mode as Mode
    setCurrentMode(nextMode)

    const path = modeToPath(nextMode)
    if (path) {
      if (location.pathname !== path) {
        navigate(path)
      }
      return
    }

    // Modes without a dedicated URL (dashboard, documents, tasks, …) live at `/`.
    // If we came from a reserved path such as `/monitoring`, clear it so the address bar
    // matches the active tab (otherwise Documents would still show `/monitoring`).
    if (location.pathname.startsWith('/forms/')) {
      navigate('/')
    } else if (pathToMode(location.pathname)) {
      navigate('/')
    }
  }

  const protectedTree = (
    <StudySiteProvider>
      <AppLayout
        currentMode={currentMode}
        onModeChange={handleModeChange}
      >
        <UnifiedInbox
          apiBase={API_BASE}
          currentMode={currentMode}
          onModeChange={handleModeChange}
        />
      </AppLayout>
      <AssistantWidget onNavigate={handleModeChange} currentMode={currentMode} />
      {/* Global Cmd+K palette. Mounted once at the top of the protected tree. */}
      <CommandPalette
        apiBase={API_BASE}
        onSelectConversation={(id) => {
          // Switch to the conversations module and signal the inbox via a
          // custom event so it can pre-select the row without prop drilling.
          handleModeChange('conversations')
          window.dispatchEvent(new CustomEvent('crm:select-conversation', { detail: { id } }))
        }}
        onModeChange={handleModeChange}
      />
    </StudySiteProvider>
  )

  if (HUB_MODE) {
    return <AuthCheck>{protectedTree}</AuthCheck>
  }

  return protectedTree
}

// Thin wrapper: reads :templateId from the URL and forwards it to TemplateBuilderPage.
const TemplateBuilderRoute: React.FC = () => {
  const params = useParams<{ templateId: string }>()
  const navigate = useNavigate()
  if (!params.templateId) return null
  return (
    <TemplateBuilderPage
      templateId={params.templateId}
      onClose={() => navigate(-1)}
    />
  )
}

const AppRoutes: React.FC = () => (
  <Suspense fallback={<RouteSpinner />}>
    <Routes>
      {/* Public, token-gated pages: no auth required, lazy-loaded. */}
      <Route path="/feasibility/form" element={<FeasibilityForm />} />
      <Route path="/agreement/review/*" element={<AgreementReviewPage />} />
      <Route path="/agreement/sign/*" element={<AgreementSignPage />} />
      <Route path="/monitoring/visits/:visitId/reschedule" element={<VisitReschedulePage />} />
      <Route path="/monitoring/visits/:visitId/review" element={<VisitReportReviewPage />} />
      <Route path="/monitoring/visits/:visitId/confirm" element={<VisitConfirmationPage />} />
      <Route
        path="/monitoring/visits/:visitId/pre-visit-report/acknowledge"
        element={<PreVisitAcknowledgePage />}
      />
      <Route path="/acknowledge" element={<AcknowledgeReceipt />} />

      {/* Workflow task inbox + per-instance runner (linked from the sidebar). */}
      <Route path="/workflows/inbox" element={<WorkflowInboxPage />} />
      <Route path="/workflows/instances/:id" element={<WorkflowInstancePage />} />

      {/* Clause Library — template builder for CLAUSE_COMPOSED templates. */}
      <Route path="/templates/:templateId/builder" element={<TemplateBuilderRoute />} />

      {/* Orbit live evals — scores with judge reasoning (auth via API 401 redirect). */}
      <Route path="/orbit/evals" element={<LiveEvalDashboardPage />} />

      {/* Everything else lands in the protected shell (auth + AppLayout + UnifiedInbox). */}
      <Route path="*" element={<ProtectedShell />} />
    </Routes>
  </Suspense>
)

function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <AppRoutes />
            <Toaster />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

export default App
