import React, { useLayoutEffect, useRef, useState } from 'react'

const LogOutIcon = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
  </svg>
)

const SettingsIcon = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
)

interface NavbarUserMenuProps {
  user: { name?: string | null; email?: string | null; is_privileged?: boolean }
  open: boolean
  onToggle: () => void
  onClose: () => void
  onLogout: () => void
}

const NavbarUserMenu: React.FC<NavbarUserMenuProps> = ({
  user,
  open,
  onToggle,
  onClose,
  onLogout,
}) => {
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(null)

  const initials = (() => {
    if (user.name) {
      return user.name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    }
    if (user.email) return user.email[0].toUpperCase()
    return 'U'
  })()

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) {
      setMenuPos(null)
      return
    }
    const rect = buttonRef.current.getBoundingClientRect()
    setMenuPos({
      top: rect.bottom + 8,
      right: Math.max(8, window.innerWidth - rect.right),
    })
  }, [open])

  useLayoutEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open, onClose])

  return (
    <div className="relative shrink-0 flex-none pl-1 border-l border-white/25" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        onClick={onToggle}
        className="flex items-center p-1 hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-white/50 rounded-lg shrink-0"
        aria-label="User menu"
        aria-expanded={open}
      >
        <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-full bg-white/20 flex items-center justify-center text-white font-semibold text-xs sm:text-sm border-2 border-white/30 ring-2 ring-white/20 shrink-0">
          {initials}
        </div>
      </button>

      {open && menuPos && (
        <div
          className="fixed w-64 bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-[500] overflow-y-auto max-h-[calc(100vh-5rem)]"
          style={{ top: menuPos.top, right: menuPos.right }}
        >
          <div className="px-3 py-3 border-b border-gray-100">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-[#1E73BE] flex items-center justify-center text-white font-semibold text-lg border-2 border-gray-200">
                {initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-900 truncate">
                  {user.name || user.email || 'User'}
                </p>
                {user.email && (
                  <p className="text-xs text-gray-500 truncate mt-0.5">{user.email}</p>
                )}
                {user.is_privileged && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[#1E73BE]/10 text-[#1E73BE] mt-1">
                    Admin
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="h-px bg-gray-100" />
          <div className="px-3 py-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Account</p>
            <button
              type="button"
              onClick={onClose}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 transition-colors rounded-md flex items-center gap-2"
            >
              <SettingsIcon size={16} />
              <span>Settings</span>
            </button>
          </div>
          <div className="h-px bg-gray-100" />
          <button
            type="button"
            onClick={onLogout}
            className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors rounded-md flex items-center gap-2"
          >
            <LogOutIcon size={16} />
            <span>Logout</span>
          </button>
        </div>
      )}
    </div>
  )
}

export default NavbarUserMenu
