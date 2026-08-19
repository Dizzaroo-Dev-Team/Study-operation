import React, { useEffect, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { useStudySite } from '../contexts/StudySiteContext'
import { FORMS_NAV_ITEMS } from './Navbar/FormsDropdown'
import NavbarUserMenu from './Navbar/NavbarUserMenu'
import NavbarWorkspaceContext from './Navbar/NavbarWorkspaceContext'
import { useMyAssignments } from '@/lib/queries/useAgreements'
const NAV_ITEMS = [
  { id: 'dashboard',     label: 'Dashboard',    icon: '📊' },
  { id: 'study-setup',   label: 'Study Setup',  icon: '🔬' },
  { id: 'site-profile',  label: 'Site Profile', icon: '📋' },
  { id: 'site-status',   label: 'Site Status',  icon: '📋' },
  { id: 'documents',     label: 'Documents',    icon: '📁' },
  { id: 'tasks',         label: 'Tasks',        icon: '✅' },
  { id: 'monitoring',    label: 'Monitoring',   icon: '📡' },
  { id: 'conversations', label: 'Conversations',icon: '💬' },
] as const

function logoFallback(parent: HTMLElement, img: HTMLImageElement) {
  const span = document.createElement('span')
  span.textContent = 'DZ'
  span.style.cssText =
    'font-weight:800;font-size:18px;color:white;letter-spacing:-.5px;'
  parent.insertBefore(span, img)
}

interface NavbarProps {
  onModeChange?: (mode: string) => void
  currentMode?: string
  onNavigateToUsers?: () => void
}

const MenuIcon = ({ size = 20 }: { size?: number }) => (
  <svg width={size} height={size} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
  </svg>
)


const BellIcon = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
  </svg>
)

const Navbar: React.FC<NavbarProps> = ({ onModeChange, currentMode = 'dashboard' }) => {
  const { user, logout } = useAuth()
  const {
    selectedStudyId,
    setSelectedStudyId,
    selectedSiteId,
    setSelectedSiteId,
    studies,
    filteredSites,
    loading,
  } = useStudySite()
  const [isOpen, setIsOpen] = useState(false)
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [showBellMenu, setShowBellMenu] = useState(false)
  const bellMenuRef = useRef<HTMLDivElement>(null)

  const myAssignmentsQuery = useMyAssignments()
  const myAssignments = myAssignmentsQuery.data ?? []

  // Show navigation immediately once authenticated. Site context is now handled
  // inside the modules that need it, not gated at the navbar.
  const showNavigationControls = !!user
  const showControls = showNavigationControls


  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (bellMenuRef.current && !bellMenuRef.current.contains(event.target as Node)) {
        setShowBellMenu(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleModeClick = (mode: string) => {
    onModeChange?.(mode)
    setIsOpen(false)
    setShowUserMenu(false)
  }

  const closeMenus = () => {
    setShowUserMenu(false)
  }

  const isSiteProfileSection =
    currentMode === 'site-profile' ||
    currentMode === 'site-staff-details' ||
    currentMode === 'irb-administrative-info'

  const renderNavItems = () =>
    NAV_ITEMS.map((item) => {
      const isActive =
        item.id === 'site-profile'
          ? isSiteProfileSection
          : currentMode === item.id
      const tab = (
        <button
          key={item.id}
          type="button"
          title={item.label}
          data-testid={`nav-${item.id}`}
          className={`px-2.5 lg:px-3 py-1.5 text-sm font-medium transition-all relative flex items-center gap-1.5 whitespace-nowrap shrink-0 ${
            isActive ? 'text-white' : 'text-white/80 hover:text-white'
          }`}
          onClick={() => handleModeClick(item.id === 'site-profile' ? 'site-profile' : item.id)}
        >
          <span aria-hidden="true">{item.icon}</span>
          <span className="hidden lg:inline">{item.label}</span>
          {isActive && (
            <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-white rounded-full" />
          )}
        </button>
      )

      return tab
    })

  return (
    <nav
      data-testid="app-navbar"
      className="w-full h-16 shrink-0 flex items-center px-2 sm:px-3 lg:px-4 overflow-visible relative z-[200]"
      style={{
        background: 'linear-gradient(to right, rgba(22, 138, 173, 0.92), rgba(118, 200, 147, 0.92))',
        backdropFilter: 'blur(12px) saturate(180%)',
        WebkitBackdropFilter: 'blur(12px) saturate(180%)',
        boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(255, 255, 255, 0.2) inset',
        borderBottom: '1px solid rgba(255, 255, 255, 0.15)',
      }}
    >
      <div className="flex items-center gap-2 w-full min-w-0 h-full">
        <div className="flex items-center gap-1 sm:gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setIsOpen((o) => !o)}
            className="lg:hidden p-2 rounded-md text-white hover:bg-white/20 shrink-0"
            aria-label="Open menu"
          >
            <MenuIcon size={20} />
          </button>

          {isOpen && (
            <div className="fixed inset-0 z-50 lg:hidden">
              <div className="fixed inset-0 bg-black/50" onClick={() => setIsOpen(false)} />
              <div className="fixed left-0 top-0 bottom-0 w-[280px] sm:w-[320px] bg-gradient-to-b from-[#168AAD] to-[#76C893] shadow-xl overflow-y-auto">
                <div className="p-4 border-b border-white/20 flex items-center gap-2">
                  <img src="/dizzaroo_logo.png" alt="Dizzaroo" className="h-6 w-auto object-contain" />
                  <h2 className="text-lg font-bold text-white">Dizzaroo</h2>
                </div>
                <div className="p-4 space-y-3">
                  <NavbarWorkspaceContext layout="drawer" />
                </div>
                <div className="p-4 border-t border-white/20 space-y-1">
                  <p className="text-xs font-semibold text-white/80 uppercase tracking-wide mb-2">
                    Site Profile
                  </p>
                  {FORMS_NAV_ITEMS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                        currentMode === item.id
                          ? 'bg-white/20 text-white font-medium'
                          : 'text-white hover:bg-white/15'
                      }`}
                      onClick={() => handleModeClick(item.id)}
                    >
                      {item.icon} {item.label}
                    </button>
                  ))}
                  <p className="text-xs font-semibold text-white/80 uppercase tracking-wide mb-2 mt-4">
                    Navigation
                  </p>
                  {NAV_ITEMS.filter((item) => item.id !== 'site-profile').map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                        currentMode === item.id
                          ? 'bg-white/20 text-white font-medium'
                          : 'text-white hover:bg-white/15'
                      }`}
                      onClick={() => handleModeClick(item.id)}
                    >
                      {item.icon} {item.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          <img
            src="/dizzaroo_logo.png"
            alt="Dizzaroo"
            className="h-6 sm:h-7 w-auto object-contain shrink-0"
            onError={(e) => {
              const target = e.target as HTMLImageElement
              target.style.display = 'none'
              const parent = target.parentElement
              if (parent) logoFallback(parent, target)
            }}
          />
        </div>

        {showControls && (
          <div
            className="hidden md:flex flex-1 min-w-0 items-center overflow-x-auto overflow-y-hidden mx-1
              [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
            aria-label="Main navigation"
          >
            <div className="flex items-center gap-0 min-w-max">{renderNavItems()}</div>
          </div>
        )}

        {/* Right cluster. Outer wrapper deliberately *not* `shrink-0` — when the
            inner study/site selectors are wide they have to give ground before
            the profile button gets pushed off the right edge of the viewport.
            Profile keeps its own `shrink-0` so it always stays visible. */}
        <div className="flex items-center gap-1.5 min-w-0 overflow-visible ml-auto">
          {/* Study + Site selectors. Site lives here (not just on the
              conversations page) so the operator can switch context once and
              every gated module — inbox, profile, status, logistics, control
              tower, monitoring — picks it up via StudySiteContext.
              `min-w-0` on this row lets the selects shrink past their content
              width when the navbar is tight; long names truncate visually
              (`text-ellipsis`) but expand in the open dropdown panel. */}
          {showNavigationControls && (
            <div className="hidden md:flex items-center gap-1 border-r border-white/30 pr-1.5 mr-0.5 min-w-0">
              <button
                type="button"
                onClick={() => {
                  closeMenus()
                  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))
                }}
                className="inline-flex items-center gap-1.5 px-2 py-1.5 bg-white/10 hover:bg-white/20 text-white/90 text-xs font-medium rounded-lg border border-white/20 transition shrink-0"
                aria-label="Open command palette"
                title="Search / jump to anything (⌘K)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
                <kbd className="text-[10px] bg-white/15 border border-white/20 rounded px-1 py-0">⌘K</kbd>
              </button>
              <select
                value={selectedStudyId || ''}
                onChange={(e) => setSelectedStudyId(e.target.value || null)}
                disabled={loading || studies.length === 0}
                aria-label="Select study"
                data-testid="nav-study-selector"
                title={
                  selectedStudyId
                    ? (studies.find((s) => s.id === selectedStudyId)?.name || 'Selected study')
                    : 'Select study'
                }
                className="px-2 py-1.5 bg-white/15 hover:bg-white/25 text-white text-xs font-medium rounded-lg transition-all border border-white/30 focus:outline-none focus:ring-2 focus:ring-white/50 disabled:opacity-50 disabled:cursor-not-allowed min-w-0 w-[110px] lg:w-[130px] appearance-none cursor-pointer text-ellipsis"
                style={{ color: 'white' }}
              >
                <option value="" style={{ color: '#1f2937', backgroundColor: 'white' }}>
                  {studies.length === 0 ? 'No studies' : 'Select study'}
                </option>
                {studies.map((study) => (
                  <option key={study.id} value={study.id} style={{ color: '#1f2937', backgroundColor: 'white' }}>
                    {study.name}
                  </option>
                ))}
              </select>
              <select
                value={selectedSiteId || ''}
                onChange={(e) => setSelectedSiteId(e.target.value || null)}
                disabled={loading || !selectedStudyId || filteredSites.length === 0}
                aria-label="Select site"
                data-testid="nav-site-selector"
                title={
                  !selectedStudyId
                    ? 'Select a study first'
                    : selectedSiteId
                      ? (filteredSites.find((s) => s.site_id === selectedSiteId)?.name || 'Selected site')
                      : 'Select site'
                }
                className="px-2 py-1.5 bg-white/15 hover:bg-white/25 text-white text-xs font-medium rounded-lg transition-all border border-white/30 focus:outline-none focus:ring-2 focus:ring-white/50 disabled:opacity-50 disabled:cursor-not-allowed min-w-0 w-[110px] lg:w-[130px] appearance-none cursor-pointer text-ellipsis"
                style={{ color: 'white' }}
              >
                <option value="" style={{ color: '#1f2937', backgroundColor: 'white' }}>
                  {!selectedStudyId
                    ? 'Pick study first'
                    : filteredSites.length === 0
                      ? 'No sites'
                      : 'Select site'}
                </option>
                {filteredSites.map((site) => (
                  <option key={site.id} value={site.site_id} style={{ color: '#1f2937', backgroundColor: 'white' }}>
                    {site.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* CTA bell notifications */}
          {user && (
            <div className="relative overflow-visible" ref={bellMenuRef}>
              <button
                onClick={() => setShowBellMenu((prev) => !prev)}
                className="relative p-2 rounded-lg text-white/90 hover:text-white hover:bg-white/20 focus:outline-none focus:ring-2 focus:ring-white/50 transition shrink-0"
                aria-label="CTA reviews and signatures"
                title="My CTA Reviews & Signatures"
              >
                <BellIcon size={18} />
                {myAssignments.length > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center leading-none">
                    {myAssignments.length > 9 ? '9+' : myAssignments.length}
                  </span>
                )}
              </button>

              {showBellMenu && (
                <div
                  className="bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-[100] overflow-y-auto max-h-[calc(100vh-5rem)] w-72"
                  style={{ position: 'fixed', top: '4rem', right: '3.5rem' }}
                >
                  <div className="px-3 py-2 border-b border-gray-100">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      My CTA Reviews & Signatures
                    </p>
                  </div>
                  {myAssignments.length === 0 ? (
                    <p className="px-3 py-4 text-sm text-gray-500 text-center">
                      No pending reviews or signatures.
                    </p>
                  ) : (
                    <ul>
                      {myAssignments.map((a) => (
                        <li key={a.agreement_id}>
                          <button
                            type="button"
                            onClick={() => {
                              setShowBellMenu(false)
                              try {
                                if (a.study_id) {
                                  localStorage.setItem('crm.lastStudyId', a.study_id)
                                  localStorage.setItem('dizzaroo_selected_study', a.study_id)
                                }
                                if (a.site_id) {
                                  localStorage.setItem('dizzaroo_selected_site', a.site_id)
                                }
                                // Strong intent consumed once by StudySiteContext
                                // for auto-select + access check.
                                localStorage.setItem(
                                  'crm.openAgreementIntent',
                                  JSON.stringify({
                                    study_id: a.study_id ?? null,
                                    site_id: a.site_id ?? null,
                                    agreement_id: a.agreement_id,
                                  }),
                                )
                                localStorage.setItem('crm.lastModule', 'study-setup')
                                localStorage.setItem('crm.lastTab', 'study-setup:agreements')
                                localStorage.setItem('crm.landOn', 'study-setup')
                                sessionStorage.setItem('crm.sessionOpened', '1')
                              } catch {
                                /* ignore storage errors */
                              }
                              window.location.assign('/')
                            }}
                            className="w-full text-left flex items-start gap-2 px-3 py-2.5 hover:bg-gray-50 transition focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                          >
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-gray-900 truncate">
                                {a.study_name || 'Untitled CTA'}
                              </p>
                              {a.site_name && (
                                <p className="text-xs text-gray-500 truncate">{a.site_name}</p>
                              )}
                            </div>
                            <span
                              className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                                a.role === 'reviewer'
                                  ? 'bg-purple-100 text-purple-700'
                                  : 'bg-blue-100 text-blue-700'
                              }`}
                            >
                              {a.role === 'reviewer' ? 'Review' : 'Sign'}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}

          {user && (
            <NavbarUserMenu
              user={user}
              open={showUserMenu}
              onToggle={() => {
                setShowUserMenu((o) => !o)
              }}
              onClose={() => setShowUserMenu(false)}
              onLogout={() => {
                logout()
                setShowUserMenu(false)
              }}
            />
          )}
        </div>
      </div>
    </nav>
  )
}

export default Navbar
