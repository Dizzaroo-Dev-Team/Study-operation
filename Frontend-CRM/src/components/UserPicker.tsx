import React, { useMemo, useState, useEffect, useRef, useCallback } from 'react'
import { useUsersList } from '@/lib/queries/useUsers'
import { User } from '../types'

interface UserPickerProps {
  selectedUserEmails: string[]
  onSelectionChange: (emails: string[]) => void
  siteId?: string
  excludeEmails?: string[]  // Emails to exclude from selection (e.g., current user if already included)
  placeholder?: string
  className?: string
  /** When true, renders a button-style dropdown — selecting a user closes the
   *  dropdown immediately and replaces any previous selection. The selected
   *  user is shown inline inside the button, not as a chip below. */
  singleSelect?: boolean
}

const UserPicker: React.FC<UserPickerProps> = ({
  selectedUserEmails,
  onSelectionChange,
  siteId,
  excludeEmails = [],
  placeholder = 'Search and select users...',
  className = '',
  singleSelect = false,
}) => {
  const [searchQuery, setSearchQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const [focusedIndex, setFocusedIndex] = useState<number>(-1)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // Users are now fetched via the shared useUsersList hook. Two pickers
  // mounted with the same siteId share one in-flight request and one cache
  // entry; the 5-minute staleTime means opening + closing the dropdown
  // repeatedly doesn't refetch.
  const usersQuery = useUsersList({ site_id: siteId })
  const users: User[] = usersQuery.data ?? []
  const loading = usersQuery.isFetching

  // Derive the filtered list with useMemo — was previously a useEffect +
  // setFilteredUsers, which caused an extra render and double-renderized
  // the dropdown every keystroke.
  const filteredUsers = useMemo<User[]>(() => {
    const q = searchQuery.trim().toLowerCase()
    return users.filter((u) => {
      const email = u.email?.toLowerCase() || ''
      if (excludeEmails.includes(email)) return false
      if (!q) return true
      const name = u.name?.toLowerCase() || ''
      const userId = u.user_id?.toLowerCase() || ''
      return email.includes(q) || name.includes(q) || userId.includes(q)
    })
  }, [searchQuery, users, excludeEmails])

  useEffect(() => {
    // Close dropdown when clicking outside
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
        setSearchQuery('')
        setFocusedIndex(-1)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Reset focused index when filtered list changes
  useEffect(() => {
    setFocusedIndex(-1)
  }, [filteredUsers.length])

  const openDropdown = useCallback(() => {
    setIsOpen(true)
    // Defer focus so the input is visible first
    setTimeout(() => searchInputRef.current?.focus(), 0)
  }, [])

  const closeDropdown = useCallback(() => {
    setIsOpen(false)
    setSearchQuery('')
    setFocusedIndex(-1)
  }, [])

  const toggleUser = (user: User) => {
    const email = user.email?.toLowerCase() || ''
    if (!email) return

    if (singleSelect) {
      // In single-select mode always replace selection and close
      onSelectionChange([email])
      closeDropdown()
      return
    }

    if (selectedUserEmails.includes(email)) {
      onSelectionChange(selectedUserEmails.filter(e => e !== email))
    } else {
      onSelectionChange([...selectedUserEmails, email])
    }
  }

  const removeUser = (email: string) => {
    onSelectionChange(selectedUserEmails.filter(e => e !== email))
  }

  const getSelectedUsers = () => {
    return users.filter(u => selectedUserEmails.includes(u.email?.toLowerCase() || ''))
  }

  // ── Keyboard navigation (used by both modes) ─────────────────────────────

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      closeDropdown()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setFocusedIndex(prev => Math.min(prev + 1, filteredUsers.length - 1))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setFocusedIndex(prev => Math.max(prev - 1, 0))
      return
    }
    if (e.key === 'Enter' && focusedIndex >= 0 && filteredUsers[focusedIndex]) {
      e.preventDefault()
      toggleUser(filteredUsers[focusedIndex])
    }
  }

  const handleTriggerKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      openDropdown()
    }
    if (e.key === 'Escape') {
      closeDropdown()
    }
  }

  // ── Single-select render ──────────────────────────────────────────────────

  if (singleSelect) {
    const selectedUser = getSelectedUsers()[0] ?? null

    return (
      <div className={`relative ${className}`} ref={dropdownRef}>
        {/* Trigger button */}
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          onClick={() => (isOpen ? closeDropdown() : openDropdown())}
          onKeyDown={handleTriggerKeyDown}
          className="w-full flex items-center justify-between gap-2 px-3 py-2 border border-gray-300 rounded-lg bg-white text-sm focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
        >
          <span className={selectedUser ? 'text-gray-900 truncate' : 'text-gray-400 truncate'}>
            {selectedUser ? (selectedUser.name || selectedUser.email) : placeholder}
          </span>
          {/* Chevron */}
          <svg
            className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
              clipRule="evenodd"
            />
          </svg>
        </button>

        {/* Dropdown panel */}
        {isOpen && (
          <div
            role="listbox"
            className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg"
          >
            {/* Search */}
            <div className="p-2 border-b border-gray-200">
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder="Search..."
                className="w-full px-2 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
              />
            </div>
            {/* Options */}
            <div ref={listRef} className="max-h-52 overflow-y-auto py-1">
              {loading ? (
                <div className="px-4 py-3 text-sm text-gray-500 text-center">Loading users...</div>
              ) : filteredUsers.length === 0 ? (
                <div className="px-4 py-3 text-sm text-gray-500 text-center">
                  {searchQuery ? 'No users found' : 'Start typing to search'}
                </div>
              ) : (
                filteredUsers.map((user, idx) => {
                  const email = user.email?.toLowerCase() || ''
                  const isSelected = selectedUserEmails.includes(email)
                  const isFocused = idx === focusedIndex
                  return (
                    <div
                      key={user.user_id}
                      role="option"
                      aria-selected={isSelected}
                      onClick={() => toggleUser(user)}
                      className={`px-4 py-2 cursor-pointer flex items-center justify-between ${
                        isFocused ? 'bg-blue-50' : isSelected ? 'bg-blue-50' : 'hover:bg-gray-100'
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 truncate">
                          {user.name || user.user_id}
                        </div>
                        <div className="text-xs text-gray-500 truncate">{user.email}</div>
                        {user.role && (
                          <div className="text-xs text-gray-400 mt-0.5">{user.role}</div>
                        )}
                      </div>
                      {isSelected && (
                        <span className="ml-2 text-blue-600 font-bold" aria-hidden="true">&#10003;</span>
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── Multi-select render (existing behavior, unchanged) ────────────────────

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Selected Users Display */}
      {getSelectedUsers().length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {getSelectedUsers().map(user => (
            <div
              key={user.email}
              className="flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium"
            >
              <span>{user.name || user.email}</span>
              <button
                onClick={() => removeUser(user.email?.toLowerCase() || '')}
                className="text-blue-600 hover:text-blue-800 font-bold"
                type="button"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Search Input */}
      <div className="relative">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value)
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleSearchKeyDown}
          placeholder={placeholder}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue text-sm"
        />
        {loading && (
          <div className="absolute right-3 top-2.5">
            <span className="animate-spin text-gray-400">&#8987;</span>
          </div>
        )}
      </div>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
          {filteredUsers.length === 0 ? (
            <div className="px-4 py-3 text-sm text-gray-500 text-center">
              {loading ? 'Loading users...' : searchQuery ? 'No users found' : 'Start typing to search'}
            </div>
          ) : (
            <div className="py-1">
              {filteredUsers.map((user, idx) => {
                const email = user.email?.toLowerCase() || ''
                const isSelected = selectedUserEmails.includes(email)
                const isFocused = idx === focusedIndex
                return (
                  <div
                    key={user.user_id}
                    onClick={() => toggleUser(user)}
                    className={`px-4 py-2 cursor-pointer hover:bg-gray-100 flex items-center justify-between ${
                      isSelected || isFocused ? 'bg-blue-50' : ''
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate">
                        {user.name || user.user_id}
                      </div>
                      <div className="text-xs text-gray-500 truncate">{user.email}</div>
                      {user.role && (
                        <div className="text-xs text-gray-400 mt-0.5">{user.role}</div>
                      )}
                    </div>
                    {isSelected && (
                      <span className="ml-2 text-blue-600 font-bold" aria-hidden="true">&#10003;</span>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default UserPicker
