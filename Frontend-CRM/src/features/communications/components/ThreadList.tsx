import React from 'react'
import { Thread } from '@/types'
import { useStudySite } from '@/contexts/StudySiteContext'

// -----------------------------------------------------------------------------
// Module-scope helpers
// -----------------------------------------------------------------------------
// Hoisted so they don't get recreated on every parent render. With memoized
// rows below, this guarantees a parent re-render that doesn't actually change
// the threads array can skip rendering every row.

function getStatusColor(status: string): string {
  switch (status) {
    case 'open': return '#28a745'
    case 'in_progress': return '#17a2b8'
    case 'resolved': return '#6c757d'
    case 'closed': return '#dc3545'
    default: return '#666'
  }
}

function getPriorityColor(priority: string): string {
  switch (priority) {
    case 'urgent': return '#dc3545'
    case 'high': return '#fd7e14'
    case 'medium': return '#ffc107'
    case 'low': return '#28a745'
    default: return '#666'
  }
}

function getTypeIcon(type: string): string {
  switch (type) {
    case 'issue': return '🐛'
    case 'patient': return '👤'
    case 'general': return '💬'
    default: return '💬'
  }
}

function formatTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

// -----------------------------------------------------------------------------
// ThreadRow — memoized single row.
// -----------------------------------------------------------------------------
interface ThreadRowProps {
  thread: Thread
  isSelected: boolean
  onSelect: (id: string) => void
}

const ThreadRowImpl: React.FC<ThreadRowProps> = ({ thread, isSelected, onSelect }) => {
  const { studies } = useStudySite()
  const handleClick = () => onSelect(thread.id)
  // Resolve the study id to its human-readable name; never show the raw id.
  const study = thread.related_study_id
    ? studies.find((s) => s.id === thread.related_study_id)
    : undefined
  const studyLabel = study ? (study.name || study.study_id) : null

  return (
    <div
      className={`p-3 rounded-lg border-2 cursor-pointer transition-all ${
        isSelected
          ? 'bg-dizzaroo-dna-gradient/10 border-dizzaroo-deep-blue shadow-md'
          : 'bg-white border-gray-200 hover:border-dizzaroo-deep-blue/50 hover:shadow-sm'
      }`}
      onClick={handleClick}
    >
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <span className="text-base">{getTypeIcon(thread.thread_type)}</span>
          <span className="font-bold text-xs text-gray-800 flex-1 truncate">{thread.title}</span>
        </div>
        <div className="text-xs text-gray-500 flex-shrink-0 ml-1">{formatTime(thread.updated_at)}</div>
      </div>

      <div className="flex gap-1.5 flex-wrap mb-2">
        <span
          className="px-1.5 py-0.5 rounded-full text-white text-xs font-bold"
          style={{ backgroundColor: getStatusColor(thread.status) }}
        >
          {thread.status}
        </span>
        <span
          className="px-1.5 py-0.5 rounded-full text-white text-xs font-bold"
          style={{ backgroundColor: getPriorityColor(thread.priority) }}
        >
          {thread.priority}
        </span>
        {thread.visibility_scope === 'site' ? (
          <span className="px-1.5 py-0.5 rounded-full bg-blue-500 text-white text-xs font-bold">
            🌐 Site
          </span>
        ) : (
          <span className="px-1.5 py-0.5 rounded-full bg-gray-600 text-white text-xs font-bold">
            🔐 Private
          </span>
        )}
        {thread.thread_type && (
          <span className="px-1.5 py-0.5 rounded-full bg-gray-200 text-gray-700 text-xs font-bold">
            {thread.thread_type}
          </span>
        )}
        {studyLabel && (
          <span className="px-1.5 py-0.5 rounded-full bg-dizzaroo-deep-blue text-white text-xs font-bold">
            📋 {studyLabel}
          </span>
        )}
      </div>

      {thread.description && (
        <div className="text-xs text-gray-600 mb-2 line-clamp-2">
          {thread.description.length > 60
            ? `${thread.description.substring(0, 60)}...`
            : thread.description}
        </div>
      )}

      <div className="flex justify-between items-center text-xs text-gray-500 pt-2 border-t border-gray-100">
        <div className="flex items-center gap-1.5">
          <span className="text-sm">👥</span>
          <span>{thread.participants?.length || 0} participants</span>
        </div>
      </div>
    </div>
  )
}

// Skip re-render unless the visible thread fields or selection changed.
// onSelect is referentially stable from the parent (callbacks in JSX usually
// aren't), so it's not in the comparator; if a parent passes a fresh
// arrow function each render it'll force re-renders — that's the parent's
// bug to fix, not ours to mask.
const ThreadRow = React.memo(ThreadRowImpl, (prev, next) => {
  if (prev.isSelected !== next.isSelected) return false
  if (prev.thread.id !== next.thread.id) return false
  if (prev.thread.title !== next.thread.title) return false
  if (prev.thread.status !== next.thread.status) return false
  if (prev.thread.priority !== next.thread.priority) return false
  if (prev.thread.thread_type !== next.thread.thread_type) return false
  if (prev.thread.visibility_scope !== next.thread.visibility_scope) return false
  if (prev.thread.description !== next.thread.description) return false
  if (prev.thread.updated_at !== next.thread.updated_at) return false
  if (prev.thread.related_study_id !== next.thread.related_study_id) return false
  if ((prev.thread.participants?.length || 0) !== (next.thread.participants?.length || 0)) return false
  return true
})

// -----------------------------------------------------------------------------
// ThreadList
// -----------------------------------------------------------------------------
interface ThreadListProps {
  threads: Thread[]
  onSelect: (id: string) => void
  selectedId?: string
}

const ThreadList: React.FC<ThreadListProps> = ({ threads, onSelect, selectedId }) => {
  if (threads.length === 0) {
    return (
      <div className="p-8 text-center text-gray-500">
        <p className="mb-1">No threads found</p>
        <p className="text-xs">Create a new thread to get started</p>
      </div>
    )
  }

  return (
    <div className="p-2 space-y-2" data-testid="threads-list">
      {threads.map((thread) => (
        <ThreadRow
          key={thread.id}
          thread={thread}
          isSelected={selectedId === thread.id}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}

export default ThreadList
