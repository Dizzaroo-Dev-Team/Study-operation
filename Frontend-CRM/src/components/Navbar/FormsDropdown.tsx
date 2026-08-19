import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'

export type FormsNavItemId = 'site-profile' | 'site-staff-details' | 'irb-administrative-info'

export type FormsNavItem = {
  id: FormsNavItemId
  label: string
  icon: string
}

export const FORMS_NAV_ITEMS: FormsNavItem[] = [
  { id: 'site-profile', label: 'Site Profile', icon: '📋' },
  { id: 'site-staff-details', label: 'Site Staff Details', icon: '👥' },
  { id: 'irb-administrative-info', label: 'IRB Administrative Info', icon: '📝' },
]

interface FormsDropdownProps {
  isOpen: boolean
  isActive: boolean
  currentMode: string
  onToggle: (e: React.MouseEvent<HTMLButtonElement>) => void
  onClose: () => void
  onSelect: (id: FormsNavItemId) => void
  /** Hide label text below xl to save navbar width. */
  compact?: boolean
}

const ChevronDownIcon = ({ size = 12, className = '' }: { size?: number; className?: string }) => (
  <svg width={size} height={size} fill="none" stroke="currentColor" viewBox="0 0 24 24" className={className}>
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
  </svg>
)

const FormsDropdown: React.FC<FormsDropdownProps> = ({
  isOpen,
  isActive,
  currentMode,
  onToggle,
  onClose,
  onSelect,
  compact = false,
}) => {
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null)

  useEffect(() => {
    if (!isOpen) return
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [isOpen, onClose])

  useLayoutEffect(() => {
    if (!isOpen || !buttonRef.current) {
      setMenuPos(null)
      return
    }
    const rect = buttonRef.current.getBoundingClientRect()
    setMenuPos({
      top: rect.bottom + 6,
      left: rect.left,
    })
  }, [isOpen])

  return (
    <div className="relative shrink-0" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className={`px-2 lg:px-2.5 py-1.5 text-xs lg:text-sm font-medium transition-all relative flex items-center gap-1 whitespace-nowrap ${
          isActive ? 'text-white' : 'text-white/80 hover:text-white'
        }`}
        onClick={onToggle}
        onMouseDown={(e) => e.stopPropagation()}
        title="Site Profile"
        aria-expanded={isOpen}
        aria-haspopup="menu"
        data-testid="nav-forms-dropdown"
      >
        <span aria-hidden="true">📋</span>
        <span className={compact ? 'hidden xl:inline' : undefined}>Site Profile</span>
        <ChevronDownIcon size={12} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        {isActive && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-white rounded-full" />}
      </button>

      {isOpen && menuPos && (
        <div
          role="menu"
          className="fixed bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-[500] min-w-[220px]"
          style={{ top: menuPos.top, left: menuPos.left }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {FORMS_NAV_ITEMS.map((item) => {
            const selected = currentMode === item.id
            return (
              <button
                key={item.id}
                type="button"
                role="menuitem"
                data-testid={`nav-form-${item.id}`}
                className={`w-full text-left px-4 py-2 text-sm transition-colors flex items-center gap-2 ${
                  selected ? 'bg-[#168AAD]/10 text-[#168AAD] font-medium' : 'text-gray-700 hover:bg-gray-50'
                }`}
                onClick={() => onSelect(item.id)}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default FormsDropdown
