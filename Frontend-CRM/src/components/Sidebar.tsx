import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStudySite } from '../contexts/StudySiteContext'
import { useConversationsList } from '@/lib/queries/useConversations'
import { useThreadsList } from '@/lib/queries/useThreads'

// Simple inline icon components (to avoid external icon dependencies)
const createEmojiIcon =
  (emoji: string) =>
  ({ size = 16, className }: { size?: number; className?: string }) =>
    (
      <span
        className={className}
        style={{
          fontSize: size,
          lineHeight: 1,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {emoji}
      </span>
    )

// Icons used in this sidebar
const MessageSquare = createEmojiIcon('💬')
const MessageCircle = createEmojiIcon('🧵')
const Users = createEmojiIcon('👥')
const Database = createEmojiIcon('📊')
const Settings = createEmojiIcon('⚙️')
const PlusCircle = createEmojiIcon('＋')
const ClipboardCheck = createEmojiIcon('📋')

const Menu = ({ size = 16, className }: { size?: number; className?: string }) => (
  <svg
    width={size}
    height={size}
    className={className}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="4" y1="6" x2="20" y2="6" />
    <line x1="4" y1="12" x2="20" y2="12" />
    <line x1="4" y1="18" x2="20" y2="18" />
  </svg>
)

interface SidebarProps {
  apiBase: string
  currentMode?: string
  onModeChange?: (mode: string) => void
  onNavigateToUsers?: () => void
  selectedConversationId?: string | null
  selectedThreadId?: string | null
  onSelectConversation?: (id: string) => void
  onSelectThread?: (id: string) => void
  onCreateConversation?: () => void
  onCreateThread?: () => void
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentMode = 'conversations',
  onModeChange,
  onNavigateToUsers,
  onCreateConversation,
  onCreateThread,
}) => {
  const { selectedStudyId, selectedSiteId } = useStudySite()
  const navigate = useNavigate()

  const [isCollapsed, setIsCollapsed] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  // Lists share their cache with UnifiedInbox/ConversationList; only the
  // currently visible tab actually hits the network thanks to `enabled`.
  useConversationsList(
    {
      study_id: selectedStudyId ?? null,
      site_id: selectedSiteId ?? null,
      limit: 20,
      offset: 0,
    },
    {
      enabled:
        Boolean(selectedStudyId && selectedSiteId) &&
        currentMode === 'conversations',
    },
  )
  useThreadsList(
    {
      study_id: selectedStudyId ?? null,
      site_id: selectedSiteId ?? null,
      limit: 20,
      offset: 0,
    },
    {
      enabled:
        Boolean(selectedStudyId && selectedSiteId) &&
        currentMode === 'threads',
    },
  )

  // Responsive behavior. The effect intentionally runs only once: re-subscribing
  // on every `isCollapsed` change used to bind a stale closure that ignored
  // rapid orientation flips, leaving the layout stuck. Functional updates
  // here read the latest collapse state at fire time without needing a dep.
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768
      setIsMobile(mobile)
      if (mobile) {
        setIsCollapsed((prev) => (prev ? prev : true))
      }
    }

    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const menuItems = [
    { icon: <MessageSquare size={16} />, label: 'Conversations', mode: 'conversations' },
    { icon: <MessageCircle size={16} />, label: 'Threads', mode: 'threads' },
    { icon: <Users size={16} />, label: 'Users', mode: 'users', onClick: onNavigateToUsers },
    { icon: <Database size={16} />, label: 'Site Status', mode: 'site-status' },
    { icon: <Settings size={16} />, label: 'Ask Me Anything', mode: 'ask' },
    // Workflow task inbox — a routed page (not an inbox mode): my open
    // workflow steps across all instances, with claim/reassign.
    {
      icon: <ClipboardCheck size={16} />,
      label: 'Workflow Tasks',
      mode: 'workflow-tasks',
      onClick: () => navigate('/workflows/inbox'),
    },
  ]

  const showContent = selectedStudyId && selectedSiteId


  return (
    <>
      {/* CSS override for ScrollArea viewport */}
      <style>{`
        .sidebar-scroll-area {
          max-width: 100% !important;
          width: 100% !important;
        }
        .sidebar-scroll-area > div {
          max-width: 100% !important;
          width: 100% !important;
          display: block !important;
          min-width: 0 !important;
        }
        .recent-chats-scroll::-webkit-scrollbar {
          width: 6px;
        }
        .recent-chats-scroll::-webkit-scrollbar-track {
          background: transparent;
          border-radius: 3px;
        }
        .recent-chats-scroll::-webkit-scrollbar-thumb {
          background: #d1d5db;
          border-radius: 3px;
        }
        .recent-chats-scroll::-webkit-scrollbar-thumb:hover {
          background: #9ca3af;
        }
      `}</style>

      {/* Mobile overlay */}
      {isMobile && !isCollapsed && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden"
          onClick={() => setIsCollapsed(true)}
        />
      )}

      <div className={`h-[calc(100vh-4rem)] ${isCollapsed ? 'w-16' : 'w-72'} flex flex-col border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 transition-all duration-300 relative overflow-hidden ${isMobile && !isCollapsed ? 'fixed left-0 top-16 z-50' : ''}`}>
        {/* Fixed top section */}
        <div className={`${isCollapsed ? 'p-2' : 'p-3'} border-b border-gray-100 dark:border-gray-700 min-w-0 overflow-x-hidden`}>
          {isCollapsed ? (
            /* Collapsed Layout */
            <div className="space-y-3">
              <div className="flex justify-center">
                <button
                  onClick={() => setIsCollapsed(!isCollapsed)}
                  className="group relative p-2 rounded-lg transition-all duration-300 transform hover:scale-105 text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-700/50 hover:bg-[#1E73BE]/10 dark:hover:bg-[#1E73BE]/20 hover:text-[#1E73BE] dark:hover:text-[#1E73BE] shadow-sm hover:shadow-md"
                  title="Expand Sidebar"
                >
                  <Menu size={18} className="transition-all duration-300" />
                </button>
              </div>
              
              {showContent && (
                <div className="relative">
                  <button
                    onClick={() => {
                      if (currentMode === 'conversations' && onCreateConversation) {
                        onCreateConversation()
                      } else if (currentMode === 'threads' && onCreateThread) {
                        onCreateThread()
                      }
                    }}
                    className="group relative w-full overflow-hidden rounded-lg transition-all duration-300 transform hover:scale-[1.01] active:scale-[0.99] p-2.5 bg-gradient-to-r from-[#168AAD] via-[#1E73BE] to-[#76C893] shadow-md hover:shadow-lg"
                    title={currentMode === 'conversations' ? 'New Conversation' : 'New Thread'}
                  >
                    <div className="absolute inset-0 bg-gradient-to-r from-[#76C893] via-[#168AAD] to-[#1E73BE] opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    <div className="relative z-10 flex items-center justify-center text-white font-medium">
                      <PlusCircle size={18} className="flex-shrink-0" />
                    </div>
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Expanded Layout */
            <div className="space-y-4 min-w-0 overflow-x-hidden">
              {/* Header with burger menu */}
              <div className="flex items-center gap-3 min-w-0">
                <button
                  onClick={() => setIsCollapsed(!isCollapsed)}
                  className="group relative p-1.5 rounded-md transition-all duration-300 text-gray-500 dark:text-gray-400 hover:bg-[#1E73BE]/10 dark:hover:bg-[#1E73BE]/20 hover:text-[#1E73BE] dark:hover:text-[#1E73BE] flex-shrink-0"
                  title="Collapse Sidebar"
                >
                  <Menu size={16} className="transition-all duration-300" />
                </button>
              </div>
              
              {/* New Conversation/Thread Button */}
              {showContent && (
                <div className="relative">
                  <button
                    onClick={() => {
                      if (currentMode === 'conversations' && onCreateConversation) {
                        onCreateConversation()
                      } else if (currentMode === 'threads' && onCreateThread) {
                        onCreateThread()
                      }
                    }}
                    className="group relative w-full overflow-hidden rounded-lg transition-all duration-300 transform hover:scale-[1.01] active:scale-[0.99] py-2.5 px-4 bg-gradient-to-r from-[#168AAD] via-[#1E73BE] to-[#76C893] shadow-md hover:shadow-lg"
                  >
                    <div className="absolute inset-0 bg-gradient-to-r from-[#76C893] via-[#168AAD] to-[#1E73BE] opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
                    <div className="relative z-10 flex items-center justify-center gap-2 text-white font-medium">
                      <PlusCircle size={16} className="flex-shrink-0" />
                      <span className="text-sm">
                        {currentMode === 'conversations' ? 'New Conversation' : currentMode === 'threads' ? 'New Thread' : 'New'}
                      </span>
                    </div>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Scrollable content area */}
        <div className="sidebar-scroll-area flex-1 overflow-y-auto overflow-x-hidden">
          <div className="flex-1 min-w-0 overflow-x-hidden max-w-full">
            {/* Main Menu Section */}
            <div className={`${isCollapsed ? 'mt-1 px-2' : 'mt-4 px-3'} min-w-0 overflow-x-hidden`}>
              {!isCollapsed && (
                <div className="text-xs text-gray-500 dark:text-gray-400 font-medium mb-2 px-2 truncate">
                  MAIN MENU
                </div>
              )}
              <ul className="space-y-1 min-w-0 overflow-x-hidden">
                {menuItems.map((item, index) => {
                  const isActive = currentMode === item.mode
                  return (
                    <li key={index} className="w-full min-w-0">
                      <button
                        onClick={() => {
                          if (item.onClick) {
                            item.onClick()
                          } else if (onModeChange) {
                            onModeChange(item.mode)
                          }
                        }}
                        className={`flex items-center min-w-0 w-full ${isCollapsed ? 'justify-center relative group' : ''} px-2 py-2 text-sm rounded-md transition-all duration-200 ${
                          isActive
                            ? 'text-[#1E73BE] dark:text-[#1E73BE] bg-[#1E73BE]/10 dark:bg-[#1E73BE]/20'
                            : 'text-gray-700 dark:text-gray-300 hover:bg-[#1E73BE]/10 dark:hover:bg-[#1E73BE]/20 hover:text-[#1E73BE] dark:hover:text-[#1E73BE]'
                        }`}
                        title={isCollapsed ? item.label : ""}
                      >
                        <span className={`${isCollapsed ? '' : 'mr-2'} flex-shrink-0 ${isActive ? 'text-[#1E73BE] dark:text-[#1E73BE]' : 'group-hover:text-[#1E73BE]'}`}>
                          {item.icon}
                        </span>
                        {!isCollapsed && (
                          <>
                            <span className="truncate flex-1 min-w-0 text-left">{item.label}</span>
                            {isActive && <div className="w-2 h-2 rounded-full bg-[#1E73BE] ml-auto flex-shrink-0"></div>}
                          </>
                        )}
                        {isCollapsed && isActive && (
                          <div className="absolute -right-1 top-1/2 transform -translate-y-1/2 w-1 h-6 bg-[#1E73BE] rounded-l-full"></div>
                        )}
                        
                        {/* Custom tooltip for collapsed state */}
                        {isCollapsed && (
                          <div className="absolute left-full ml-2 top-1/2 transform -translate-y-1/2 px-2 py-1 bg-gray-900 dark:bg-gray-700 text-white text-xs rounded-md opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50 pointer-events-none">
                            {item.label}
                            <div className="absolute left-0 top-1/2 transform -translate-y-1/2 -translate-x-full">
                              <div className="border-4 border-transparent border-r-gray-900 dark:border-r-gray-700"></div>
                            </div>
                          </div>
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export default Sidebar

