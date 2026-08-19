import React, { useState, FormEvent, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { useStudySite } from '@/contexts/StudySiteContext'
import { useAssignableUsers } from '@/lib/queries/useAssignableUsers'
import { displayAssignableUser } from '@/lib/users/assignableUsers'
import { TaskLinks, TaskMode } from '@/types'
import { ModalOverlay } from '@/components/ui/ModalOverlay'

export interface AppUser {
  user_id: string
  name?: string | null
  email?: string | null
  role?: string | null
}

interface TaskFormModalProps {
  isOpen: boolean
  onClose: () => void
  onTaskCreated?: (task: any) => void
  initialTitle?: string
  initialDescription?: string
  initialRequestedBy?: string
  initialAssignedToUserId?: string
  /** Users available as assignees. If omitted, the modal fetches them itself. */
  users?: AppUser[]
  defaultLinks?: TaskLinks
  apiBase: string
}

const displayUser = (u: AppUser): string => displayAssignableUser(u)

const TaskFormModal: React.FC<TaskFormModalProps> = ({
  isOpen,
  onClose,
  onTaskCreated,
  initialTitle = '',
  initialDescription = '',
  initialRequestedBy = '',
  initialAssignedToUserId = '',
  users: usersProp,
  defaultLinks,
  apiBase
}) => {
  const { user, token } = useAuth()
  const { selectedStudyId } = useStudySite()
  const [requestedBy, setRequestedBy] = useState(initialRequestedBy)
  const [assigneeUserId, setAssigneeUserId] = useState(initialAssignedToUserId)
  const [description, setDescription] = useState(initialDescription || initialTitle)
  const [dueDate, setDueDate] = useState<string>('')
  const [taskMode, setTaskMode] = useState<TaskMode | ''>('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const assignableQuery = useAssignableUsers(selectedStudyId, {
    enabled: isOpen && !usersProp,
    includeUserIds: initialAssignedToUserId ? [initialAssignedToUserId] : [],
  })

  const users = usersProp ?? assignableQuery.users
  const usersLoading = !usersProp && assignableQuery.isPending

  useEffect(() => {
    if (isOpen) {
      setRequestedBy(initialRequestedBy)
      setAssigneeUserId(initialAssignedToUserId)
      setDescription(initialDescription || initialTitle)
      setDueDate('')
      setTaskMode('')
    }
  }, [isOpen, initialRequestedBy, initialAssignedToUserId, initialDescription, initialTitle])

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()

    if (!description.trim()) {
      alert('Description is required')
      return
    }

    setIsSubmitting(true)

    try {
      const assignee = assigneeUserId
        ? users.find((u) => u.user_id === assigneeUserId)
        : undefined
      const assigneeDisplayName = assignee ? displayUser(assignee) : undefined

      const taskData = {
        // Backend still accepts an optional title; keep the first line of
        // description as a sensible fallback so legacy list views still read.
        title: description.trim().split('\n')[0].slice(0, 120),
        description: description.trim(),
        requestedBy: requestedBy.trim() || undefined,
        assigneeId: assigneeUserId || undefined,
        assigneeName: assigneeDisplayName,
        assignedTo: assigneeDisplayName,
        status: 'open',
        taskMode: taskMode || undefined,
        dueDate: dueDate || undefined,
        createdByUserId: user?.user_id,
        links: defaultLinks || undefined,
        siteId: defaultLinks?.siteId,
        monitoringVisitId: defaultLinks?.monitoringVisitId,
        monitoringReportId: defaultLinks?.monitoringReportId,
        sourceConversationId: defaultLinks?.conversationId,
      }

      const response = await fetch(`${apiBase}/tasks`, {
        method: 'POST',
        // Send the SSO session cookie (prod auth is a cookie, not a bearer) AND
        // the bearer token when present (local-token mode). Without
        // credentials:'include' this POST went out unauthenticated -> 401.
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify(taskData)
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to create task' }))
        throw new Error(errorData.detail || 'Failed to create task')
      }

      const createdTask = await response.json()
      onTaskCreated?.(createdTask)
      onClose()
    } catch (error: any) {
      console.error('Error creating task:', error)
      alert(error.message || 'Failed to create task')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (!isOpen) return null

  return (
    <ModalOverlay onClose={onClose}>
      <div
        className="bg-white rounded-lg p-6 max-w-xl w-full mx-4 max-h-[90vh] overflow-y-auto my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Add Task</h2>
          <button
            className="text-2xl text-gray-500 hover:text-gray-700"
            onClick={onClose}
            disabled={isSubmitting}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" data-testid="task-create-form">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Task Requested By</label>
              <input
                type="text"
                value={requestedBy}
                onChange={(e) => setRequestedBy(e.target.value)}
                placeholder="e.g. Dr Shanu Modi"
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                disabled={isSubmitting}
                data-testid="task-field-requested-by"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Task Assigned To</label>
              <select
                value={assigneeUserId}
                onChange={(e) => setAssigneeUserId(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue bg-white"
                disabled={isSubmitting || usersLoading || users.length === 0}
              >
                <option value="">
                  {usersLoading
                    ? 'Loading team…'
                    : !selectedStudyId && !usersProp
                      ? 'Select a study first'
                      : users.length === 0
                        ? 'No team members for this study'
                        : '— Unassigned —'}
                </option>
                {users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {displayUser(u)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Task Description *</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
              placeholder="Describe the task..."
              rows={4}
              className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue resize-y"
              disabled={isSubmitting}
              data-testid="task-field-description"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Due Date</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                disabled={isSubmitting}
                data-testid="task-field-due-date"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Task Mode</label>
              <select
                value={taskMode}
                onChange={(e) => setTaskMode(e.target.value as TaskMode | '')}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue bg-white"
                disabled={isSubmitting}
                data-testid="task-field-mode"
              >
                <option value="">— Select —</option>
                <option value="remote">Remote</option>
                <option value="on-site">On-site</option>
              </select>
            </div>
          </div>

          {defaultLinks?.conversationId && (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs text-gray-600">
              Linked to conversation: {defaultLinks.conversationId.substring(0, 8)}…
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-semibold hover:bg-gray-300 disabled:opacity-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !description.trim()}
              className="px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-xl font-semibold hover:bg-dizzaroo-blue-green disabled:opacity-50 disabled:cursor-not-allowed transition"
              data-testid="task-submit"
            >
              {isSubmitting ? 'Creating...' : 'Create Task'}
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  )
}

export default TaskFormModal
