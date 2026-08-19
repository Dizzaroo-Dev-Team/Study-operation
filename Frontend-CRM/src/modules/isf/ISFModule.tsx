/**
 * ISFModule.tsx
 *
 * Full-featured ISF shell component integrated into the CRM.
 * Replicates the standalone ISF App.jsx structure:
 *   - Left sidebar:  ISF Module branding  +  ISF Viewer / ISF Workflow nav
 *   - Top header:    page title / description  +  Settings / Alert icons
 *   - Content area:  ISFViewer  OR  ISFDocumentList  (based on active tab)
 *
 * Replaces the old SiteDocumentsTab when the 'documents' tab is active in
 * UnifiedInbox, without breaking any other CRM functionality.
 */
import React, { useState, lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FileText, FolderTree, Workflow, User, Settings, AlertCircle, Package2 } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { useStudySite } from '../../contexts/StudySiteContext'
import SitePackagesPage from '../site-packages/SitePackagesPage'

// ── Lazy-load heavy ISF pages to keep initial CRM bundle small ─────────────
// @ts-ignore – JSX files, no TS types needed
const ISFViewer = lazy(() => import('./pages/isf_viewer/ISFViewer'))
// @ts-ignore
const ISFDocumentList = lazy(() => import('./pages/isf_viewer/ISFDocumentList'))

/** Single shared QueryClient — created once per browser session. */
const isfQueryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

// ── Shared loading spinner shown while lazy chunks are fetched ─────────────
const LoadingFallback: React.FC = () => (
  <div className="flex-1 flex items-center justify-center h-full min-h-[200px]">
    <div className="text-center">
      <div className="inline-block animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mb-3" />
      <p className="text-gray-500 text-sm">Loading ISF Document Module…</p>
    </div>
  </div>
)

type ActiveTab = 'viewer' | 'workflow' | 'site-packages'

interface ISFModuleProps {
  apiBase?: string
}

const ISFModule: React.FC<ISFModuleProps> = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>('viewer')

  // Pull CRM context so we can pass the right study and show real user info
  const { user } = useAuth()
  const { selectedStudyId, selectedSiteId } = useStudySite()
  // Empty string when no study/site is selected — never fabricate a placeholder ID.
  // ISF documents are scoped by study + site, so both flow down to the list/upload.
  const studyId = selectedStudyId || ''
  const siteId = selectedSiteId || ''

  const pageTitle =
    activeTab === 'viewer'
      ? 'ISF Viewer'
      : activeTab === 'workflow'
        ? 'ISF Workflow'
        : 'Site Packages'

  const pageDesc =
    activeTab === 'viewer'
      ? 'Browse and manage ISF documents with hierarchical navigation'
      : activeTab === 'workflow'
        ? 'Document processing and workflow management'
        : 'Manage ethics board submission packages'

  return (
    <QueryClientProvider client={isfQueryClient}>
      {/* Outer flex container — fills the CRM content area completely */}
      <div className="flex h-full w-full overflow-hidden bg-gray-50" data-testid="isf-root">

        {/* ── Left sidebar (ISF navigation) ─────────────────────────────── */}
        <div className="relative flex flex-col w-48 bg-white shadow-lg border-r border-gray-200 flex-shrink-0" data-testid="isf-sidebar">
          {/* Branding */}
          <div className="p-5 pb-4">
            <div className="flex items-center gap-3 mb-7">
              <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
                <FileText className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-base font-bold text-gray-900 leading-tight">ISF Module</h1>
                <p className="text-xs text-gray-500 leading-tight">Investigator Site File</p>
              </div>
            </div>

            {/* Nav buttons */}
            <nav className="space-y-1">
              <button
                onClick={() => setActiveTab('viewer')}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium rounded-lg transition-colors ${
                  activeTab === 'viewer'
                    ? 'bg-blue-50 text-blue-700 border-l-4 border-blue-700'
                    : 'text-gray-700 hover:bg-gray-50 border-l-4 border-transparent'
                }`}
              >
                <FolderTree className="w-4 h-4 flex-shrink-0" />
                ISF Viewer
              </button>

              <button
                onClick={() => setActiveTab('workflow')}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium rounded-lg transition-colors ${
                  activeTab === 'workflow'
                    ? 'bg-blue-50 text-blue-700 border-l-4 border-blue-700'
                    : 'text-gray-700 hover:bg-gray-50 border-l-4 border-transparent'
                }`}
              >
                <Workflow className="w-4 h-4 flex-shrink-0" />
                ISF Workflow
              </button>

              <button
                onClick={() => setActiveTab('site-packages')}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm font-medium rounded-lg transition-colors ${
                  activeTab === 'site-packages'
                    ? 'bg-blue-50 text-blue-700 border-l-4 border-blue-700'
                    : 'text-gray-700 hover:bg-gray-50 border-l-4 border-transparent'
                }`}
              >
                <Package2 className="w-4 h-4 flex-shrink-0" />
                Site Packages
              </button>
            </nav>
          </div>

          {/* User info — pinned to bottom */}
          <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200 bg-white">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center flex-shrink-0">
                <User className="w-4 h-4 text-gray-500" />
              </div>
              <div className="min-w-0">
                <div className="text-xs font-medium text-gray-900 truncate">
                  {user?.name || user?.email?.split('@')[0] || 'User'}
                </div>
                <div className="text-xs text-gray-500 truncate">{user?.email || ''}</div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Main content column ────────────────────────────────────────── */}
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

          {/* Top header */}
          {activeTab !== 'site-packages' && (
            <header className="flex-shrink-0 bg-white shadow-sm border-b border-gray-200">
              <div className="px-6 py-3 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">{pageTitle}</h2>
                  <p className="text-sm text-gray-500 mt-0.5">{pageDesc}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-colors">
                    <Settings className="w-5 h-5" />
                  </button>
                  <button className="p-2 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-colors">
                    <AlertCircle className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </header>
          )}

          {/* Page content */}
          <main className="flex-1 overflow-hidden">
            <Suspense fallback={<LoadingFallback />}>
              {activeTab === 'viewer' && (
                <ISFViewer selectedStudy={studyId} />
              )}
              {activeTab === 'workflow' && (
                <ISFDocumentList selectedStudy={studyId} selectedSite={siteId} refreshKey={0} />
              )}
              {activeTab === 'site-packages' && (
                <div className="h-full overflow-y-auto">
                  <SitePackagesPage />
                </div>
              )}
            </Suspense>
          </main>
        </div>
      </div>
    </QueryClientProvider>
  )
}

export default ISFModule
