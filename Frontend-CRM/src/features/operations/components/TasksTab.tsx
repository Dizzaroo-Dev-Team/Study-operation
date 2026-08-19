import React, { useState, useMemo, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTasksList, useDeleteTask, useUpdateTask } from '@/lib/queries/useTasks'
import { useAssignableUsers } from '@/lib/queries/useAssignableUsers'
import { useUsersList } from '@/lib/queries/useUsers'
import { displayAssignableUser } from '@/lib/users/assignableUsers'
import { MonitoringTask, TaskMode, TaskStatus } from '@/types'
import TaskFormModal, { AppUser } from './TaskFormModal'
import { useStudySite } from '@/contexts/StudySiteContext'
import { useStudyTeamAssigneeNames } from '@/components/mon/hooks/useStudyTeamAssigneeNames'
import { ModalOverlay } from '@/components/ui/ModalOverlay'

const displayUser = (u: AppUser): string => displayAssignableUser(u)

type SortDir = 'asc' | 'desc'
type FilterOption = { value: string; label: string }

const STATUS_LABEL: Record<TaskStatus, string> = {
  'open': 'Pending',
  'in-progress': 'In Progress',
  'done': 'Done',
  'cancelled': 'Cancelled',
}

const STATUS_PILL: Record<TaskStatus, string> = {
  'open': 'bg-yellow-50 text-yellow-700 border-yellow-200',
  'in-progress': 'bg-blue-50 text-blue-700 border-blue-200',
  'done': 'bg-green-50 text-green-700 border-green-200',
  'cancelled': 'bg-gray-100 text-gray-600 border-gray-200',
}

const TASK_MODE_LABEL: Record<TaskMode, string> = {
  'remote': 'Remote',
  'on-site': 'On-site',
}

const TASK_MODE_PILL: Record<TaskMode, string> = {
  'remote': 'bg-sky-50 text-sky-700 border-sky-200',
  'on-site': 'bg-purple-50 text-purple-700 border-purple-200',
}

const CLINICAL_ROLE_OPTIONS: FilterOption[] = [
  { value: 'cra', label: 'CRA' },
  { value: 'pi', label: 'PI' },
  { value: 'coordinator', label: 'Coordinator' },
  { value: 'study manager', label: 'Study Manager' },
  { value: 'medical monitor', label: 'Medical Monitor' },
  { value: 'sponsor', label: 'Sponsor' },
]

const APP_ONLY_ROLES = new Set(['participant', 'user', 'admin', 'system_admin'])

const ROLE_LABELS: Record<string, string> = {
  cra: 'CRA',
  clinical_research_associate: 'CRA',
  principal_investigator: 'PI',
  investigator: 'PI',
  pi: 'PI',
  study_coordinator: 'Coordinator',
  site_coordinator: 'Coordinator',
  coordinator: 'Coordinator',
  study_manager: 'Study Manager',
  medical_monitor: 'Medical Monitor',
  sponsor: 'Sponsor',
}

const normalize = (value: unknown): string => String(value ?? '').trim()

const normalizeRole = (value: unknown): string => {
  const raw = normalize(value)
  if (!raw) return ''
  const key = raw.toLowerCase().replace(/[\s-]+/g, '_')
  if (APP_ONLY_ROLES.has(key)) return ''
  return ROLE_LABELS[key] || raw
}

const uniqueOptions = (values: Array<string | undefined | null>): FilterOption[] => {
  const seen = new Map<string, string>()
  values.forEach((raw) => {
    const label = normalize(raw)
    if (!label) return
    const key = label.toLowerCase()
    if (!seen.has(key)) seen.set(key, label)
  })
  return [...seen.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label))
}

const TasksTab: React.FC<{ apiBase: string }> = ({ apiBase }) => {
  const qc = useQueryClient()
  const { selectedStudyId } = useStudySite()
  const { options: studyTeamAssigneeOptions } = useStudyTeamAssigneeNames(selectedStudyId)
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all')
  const [roleFilter, setRoleFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingTask, setEditingTask] = useState<MonitoringTask | null>(null)
  // Orbit deep-link: `crm:select-task` opens a specific task's detail (the edit
  // modal — the app's per-task view). Held as a pending id until the list loads.
  const [pendingSelectId, setPendingSelectId] = useState<string | null>(null)

  const tasksQuery = useTasksList({ status: statusFilter, limit: 500 })
  const tasks: MonitoringTask[] = tasksQuery.data ?? []
  const usersQuery = useUsersList({ limit: 500 })
  const assignableUsersQuery = useAssignableUsers(selectedStudyId, {
    enabled: Boolean(selectedStudyId),
    includeUserIds: [
      ...(editingTask?.assigneeId ? [editingTask.assigneeId] : []),
      ...(tasks.map((t) => t.assigneeId).filter(Boolean) as string[]),
    ],
    extraUsers: (usersQuery.data ?? []) as AppUser[],
  })
  const deleteMutation = useDeleteTask()

  const users: AppUser[] = (usersQuery.data ?? []) as AppUser[]
  const assignableUsers: AppUser[] = assignableUsersQuery.users
  const usersById = useMemo(() => new Map(users.map((u) => [u.user_id, u])), [users])
  const usersByDisplayName = useMemo(
    () => new Map(users.map((u) => [displayUser(u).toLowerCase(), u])),
    [users],
  )
  const studyTeamRoleByName = useMemo(() => {
    const map = new Map<string, string>()
    studyTeamAssigneeOptions.forEach((option) => {
      if (option.role) map.set(option.name.toLowerCase(), option.role)
    })
    return map
  }, [studyTeamAssigneeOptions])
  const loading = tasksQuery.isFetching
  const error = useMemo(() => {
    if (!tasksQuery.isError) return null
    const err = tasksQuery.error as any
    return err?.response?.data?.detail || 'Failed to load tasks'
  }, [tasksQuery.isError, tasksQuery.error])

  useEffect(() => {
    const onSelect = (e: Event) => {
      const id = (e as CustomEvent).detail?.id
      if (id) setPendingSelectId(String(id))
    }
    window.addEventListener('crm:select-task', onSelect)
    return () => window.removeEventListener('crm:select-task', onSelect)
  }, [])

  useEffect(() => {
    if (!pendingSelectId || tasks.length === 0) return
    const match = tasks.find((t) => String(t.id) === pendingSelectId)
    if (match) {
      setEditingTask(match)
      setPendingSelectId(null)
    }
  }, [pendingSelectId, tasks])

  const handleTaskCreated = (_task: MonitoringTask) => {
    // Modal seeds the new row; invalidate to merge with the source of truth.
    qc.invalidateQueries({ queryKey: ['tasks'] })
    setShowCreateModal(false)
  }

  const handleDeleteTask = async (e: React.MouseEvent, taskId: string) => {
    e.stopPropagation()
    if (!confirm('Delete this task?')) return
    try {
      await deleteMutation.mutateAsync(taskId)
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to delete task')
    }
  }

  const formatDate = (date: string | Date | undefined) => {
    if (!date) return '—'
    const d = new Date(date)
    if (isNaN(d.getTime())) return '—'
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  const roleForTask = (task: MonitoringTask): string => {
    const assignedName = normalize(task.assigneeName || task.assignedTo)
    const studyTeamRole = assignedName ? studyTeamRoleByName.get(assignedName.toLowerCase()) : ''
    if (studyTeamRole) return studyTeamRole

    const explicitRole = normalizeRole(task.role || (task as any).assigneeRole || (task as any).assignedRole)
    if (explicitRole) return explicitRole

    const assignedLower = assignedName.toLowerCase()
    if (/^dr\.?\s/.test(assignedLower) || assignedLower.includes('principal investigator')) return 'PI'
    if (assignedLower.includes('coordinator')) return 'Coordinator'

    return normalizeRole(
      (task.assigneeId ? usersById.get(task.assigneeId)?.role : '') ||
      (assignedName ? usersByDisplayName.get(assignedName.toLowerCase())?.role : ''),
    )
  }

  const roleOptions = useMemo(() => {
    const dynamic = uniqueOptions(tasks.map(roleForTask))
    const merged = new Map(CLINICAL_ROLE_OPTIONS.map((option) => [option.value, option]))
    dynamic.forEach((option) => {
      if (!merged.has(option.value)) merged.set(option.value, option)
    })
    return [...merged.values()]
  }, [tasks, usersById, usersByDisplayName, studyTeamRoleByName])

  const filteredAndSorted = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = tasks.filter(t => {
      const role = roleForTask(t)
      const matchesRole = roleFilter === 'all' || role.toLowerCase() === roleFilter
      const matchesSearch = !q ||
          (t.description || '').toLowerCase().includes(q) ||
          (t.title || '').toLowerCase().includes(q) ||
          (t.requestedBy || '').toLowerCase().includes(q) ||
          (t.assignedTo || '').toLowerCase().includes(q) ||
          (t.assigneeName || '').toLowerCase().includes(q) ||
          (t.statusUpdate || '').toLowerCase().includes(q) ||
          role.toLowerCase().includes(q)
      return matchesRole && matchesSearch
    })

    const sorted = [...filtered].sort((a, b) => {
      const aTime = a.dueDate ? new Date(a.dueDate).getTime() : Number.POSITIVE_INFINITY
      const bTime = b.dueDate ? new Date(b.dueDate).getTime() : Number.POSITIVE_INFINITY
      return sortDir === 'asc' ? aTime - bTime : bTime - aTime
    })
    return sorted
  }, [tasks, search, sortDir, roleFilter, usersById, usersByDisplayName, studyTeamRoleByName])

  const toggleSort = () => setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))

  return (
    <div className="flex flex-col h-full bg-white overflow-hidden">
      <div className="flex-1 overflow-y-auto px-6 py-6" style={{ minHeight: 0 }}>
        <div className="mb-4 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-900">Tasks</h1>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 rounded-lg font-semibold text-white shadow-sm transition"
            style={{ background: '#6C5CE7' }}
            data-testid="tasks-add-button"
          >
            Add Task
          </button>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[260px] max-w-2xl">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.35-4.35" />
              </svg>
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tasks..."
              className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue"
              data-testid="tasks-search"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as TaskStatus | 'all')}
            className="w-40 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
            data-testid="tasks-status-filter"
          >
            <option value="all">All Status</option>
            <option value="open">Pending</option>
            <option value="in-progress">In Progress</option>
            <option value="done">Done</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="w-40 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
          >
            <option value="all">All Roles</option>
            {roleOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        <div className="border border-gray-200 rounded-lg overflow-hidden" data-testid="tasks-table">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200 text-gray-500 uppercase text-xs">
              <tr>
                <th className="px-4 py-3 text-left font-semibold">
                  <button onClick={toggleSort} className="inline-flex items-center gap-1 hover:text-gray-700">
                    <span aria-hidden>🕒</span>
                    <span>Due Date</span>
                    <span className="text-gray-400">{sortDir === 'asc' ? '↑' : '↓'}</span>
                  </button>
                </th>
                <th className="px-4 py-3 text-left font-semibold">
                  <span className="inline-flex items-center gap-1"><span aria-hidden>🕒</span>Closed Date</span>
                </th>
                <th className="px-4 py-3 text-left font-semibold">
                  <span className="inline-flex items-center gap-1"><span aria-hidden>👤</span>Assigned To</span>
                </th>
                <th className="px-4 py-3 text-left font-semibold">
                  <span className="inline-flex items-center gap-1"><span aria-hidden>👤</span>Requested By</span>
                </th>
                <th className="px-4 py-3 text-left font-semibold">Description</th>
                <th className="px-4 py-3 text-left font-semibold">Status Update</th>
                <th className="px-4 py-3 text-left font-semibold">Status</th>
                <th className="px-4 py-3 text-left font-semibold">Task Mode</th>
                <th className="px-4 py-3 text-left font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={9} className="px-4 py-10 text-center text-gray-500">
                    Loading tasks...
                  </td>
                </tr>
              )}
              {!loading && filteredAndSorted.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-10 text-center text-gray-500">
                    No tasks found. Click <span className="font-semibold">Add Task</span> to create one.
                  </td>
                </tr>
              )}
              {!loading && filteredAndSorted.map((task) => {
                const status = (task.status || 'open') as TaskStatus
                const assigned = task.assignedTo || task.assigneeName || '—'
                const requested = task.requestedBy || '—'
                const desc = task.description || task.title || '—'
                const statusUpdateText = (task.statusUpdate || '').trim() || '—'
                return (
                  <tr key={task.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 text-gray-900 whitespace-nowrap">{formatDate(task.dueDate)}</td>
                    <td className="px-4 py-3 text-gray-900 whitespace-nowrap">{formatDate(task.closedDate)}</td>
                    <td className="px-4 py-3 text-gray-900 whitespace-nowrap">{assigned}</td>
                    <td className="px-4 py-3 text-gray-900 whitespace-nowrap">{requested}</td>
                    <td className="px-4 py-3 text-gray-700">{desc}</td>
                    <td className="px-4 py-3 text-gray-700">{statusUpdateText}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`inline-block px-3 py-0.5 rounded-full text-xs font-semibold border ${STATUS_PILL[status] || STATUS_PILL.open}`}>
                        {STATUS_LABEL[status] || status}
                      </span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {task.taskMode ? (
                        <span className={`inline-block px-3 py-0.5 rounded-full text-xs font-semibold border ${TASK_MODE_PILL[task.taskMode]}`}>
                          {TASK_MODE_LABEL[task.taskMode]}
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <button
                          onClick={(e) => { e.stopPropagation(); setEditingTask(task) }}
                          className="text-indigo-600 hover:text-indigo-800 transition"
                          title="Edit"
                          aria-label="Edit task"
                        >
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                          </svg>
                        </button>
                        <button
                          onClick={(e) => handleDeleteTask(e, task.id)}
                          className="text-red-500 hover:text-red-700 transition"
                          title="Delete"
                          aria-label="Delete task"
                        >
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                            <path d="M10 11v6M14 11v6" />
                            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {showCreateModal && (
        <TaskFormModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onTaskCreated={handleTaskCreated}
          users={assignableUsers}
          apiBase={apiBase}
        />
      )}

      {editingTask && (
        <TaskEditModal
          task={editingTask}
          users={assignableUsers}
          onClose={() => setEditingTask(null)}
          onUpdated={() => {
            qc.invalidateQueries({ queryKey: ['tasks'] })
            setEditingTask(null)
          }}
          apiBase={apiBase}
        />
      )}
    </div>
  )
}

// Inline edit modal — same four fields as create, plus status toggle.
const TaskEditModal: React.FC<{
  task: MonitoringTask
  users: AppUser[]
  onClose: () => void
  onUpdated: () => void
  apiBase: string
}> = ({ task, users, onClose, onUpdated }) => {
  const [requestedBy, setRequestedBy] = useState(task.requestedBy || '')
  const [assigneeUserId, setAssigneeUserId] = useState(task.assigneeId || '')
  const [description, setDescription] = useState(task.description || task.title || '')
  const [status, setStatus] = useState<TaskStatus>(task.status || 'open')
  const [taskMode, setTaskMode] = useState<TaskMode | ''>(task.taskMode || '')
  const [dueDate, setDueDate] = useState<string>(
    task.dueDate ? new Date(task.dueDate).toISOString().split('T')[0] : ''
  )
  const [closedDate, setClosedDate] = useState<string>(
    task.closedDate ? new Date(task.closedDate).toISOString().split('T')[0] : ''
  )
  const [statusUpdate, setStatusUpdate] = useState(task.statusUpdate || '')
  const updateMutation = useUpdateTask()
  const isSubmitting = updateMutation.isPending

  const todayIsoDate = () => new Date().toISOString().split('T')[0]

  const handleStatusChange = (next: TaskStatus) => {
    setStatus(next)
    if (next === 'done' || next === 'cancelled') {
      setClosedDate(todayIsoDate())
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const isTerminal = status === 'done' || status === 'cancelled'
    const resolvedClosedDate = isTerminal ? (closedDate || todayIsoDate()) : closedDate
    // Only send assignee fields when the user picks one; backend will look
    // up the canonical name from assigneeId.
    const payload: Record<string, any> = {
      description: description.trim() || undefined,
      requestedBy: requestedBy.trim() || undefined,
      status,
      taskMode: taskMode || undefined,
      dueDate: dueDate || undefined,
      statusUpdate,
      ...(resolvedClosedDate ? { closedDate: resolvedClosedDate } : {}),
    }
    if (assigneeUserId !== (task.assigneeId || '')) {
      payload.assigneeId = assigneeUserId || null
    }

    try {
      await updateMutation.mutateAsync({ taskId: task.id, updates: payload })
      onUpdated()
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to update task')
    }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-white rounded-lg p-6 max-w-xl w-full mx-4 max-h-[90vh] overflow-y-auto my-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Edit Task</h2>
          <button className="text-2xl text-gray-500 hover:text-gray-700" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Task Requested By</label>
              <input
                type="text"
                value={requestedBy}
                onChange={(e) => setRequestedBy(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                disabled={isSubmitting}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Task Assigned To</label>
              <select
                value={assigneeUserId}
                onChange={(e) => setAssigneeUserId(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue bg-white"
                disabled={isSubmitting || users.length === 0}
              >
                <option value="">{users.length === 0 ? 'Loading team…' : '— Unassigned —'}</option>
                {users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {displayUser(u)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Task Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue resize-y"
              disabled={isSubmitting}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Status</label>
              <select
                value={status}
                onChange={(e) => handleStatusChange(e.target.value as TaskStatus)}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                disabled={isSubmitting}
              >
                <option value="open">Pending</option>
                <option value="in-progress">In Progress</option>
                <option value="done">Done</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Due Date</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Task Mode</label>
              <select
                value={taskMode}
                onChange={(e) => setTaskMode(e.target.value as TaskMode | '')}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue bg-white"
                disabled={isSubmitting}
              >
                <option value="">— Select —</option>
                <option value="remote">Remote</option>
                <option value="on-site">On-site</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-sm font-medium text-gray-700">Closed Date</label>
              <input
                type="date"
                value={closedDate}
                onChange={(e) => setClosedDate(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Status Update</label>
            <textarea
              value={statusUpdate}
              onChange={(e) => setStatusUpdate(e.target.value)}
              rows={3}
              placeholder="Add a status update for this task…"
              className="px-3 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue resize-y"
              disabled={isSubmitting}
            />
          </div>

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
              disabled={isSubmitting}
              className="px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-xl font-semibold hover:bg-dizzaroo-blue-green disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {isSubmitting ? 'Updating...' : 'Update Task'}
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  )
}

export default TasksTab
