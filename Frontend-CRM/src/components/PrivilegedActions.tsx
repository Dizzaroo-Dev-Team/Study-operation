import React, { useState } from 'react'
import {
  useConversationAccess,
  useGrantConversationAccess,
  useRevokeConversationAccess,
  usePatchConversationAccessFlags,
} from '@/lib/queries/useConversations'
import { Conversation, ConversationAccess } from '../types'

interface PrivilegedActionsProps {
  conversation: Conversation
  currentUserId: string
  apiBase: string
  onUpdate: () => void
}

const PrivilegedActions: React.FC<PrivilegedActionsProps> = ({
  conversation,
  currentUserId,
  onUpdate
}) => {
  const [showModal, setShowModal] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState('')
  const [accessType, setAccessType] = useState<'read' | 'write' | 'admin'>('read')
  const [error, setError] = useState<string | null>(null)

  // Access list — always loaded for canManage check; auto-refetches when
  // mutations invalidate the key.
  const accessQuery = useConversationAccess(conversation.id)
  const accessList: ConversationAccess[] = (accessQuery.data ?? []) as ConversationAccess[]

  const grantAccess = useGrantConversationAccess(conversation.id)
  const revokeAccess = useRevokeConversationAccess(conversation.id)
  const patchFlags = usePatchConversationAccessFlags(conversation.id)

  const loading =
    grantAccess.isPending || revokeAccess.isPending || patchFlags.isPending

  const canManage =
    conversation.created_by === currentUserId ||
    (accessList.length > 0 &&
      accessList.some(
        access =>
          access.user_id === currentUserId && access.access_type === 'admin'
      ))

  // Flip the conversation's confidential flag. Marking it confidential locks it
  // down to the people in the access list below (the current admin keeps access).
  const handleToggleConfidential = async () => {
    const makeConfidential = conversation.is_confidential !== 'true'
    setError(null)
    try {
      await patchFlags.mutateAsync({ is_confidential: makeConfidential })
      onUpdate()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update confidentiality')
    }
  }

  const handleGrantAccess = async () => {
    if (!selectedUserId.trim()) {
      setError('Please enter a user ID')
      return
    }

    setError(null)
    try {
      await grantAccess.mutateAsync({
        user_id: selectedUserId,
        access_type: accessType,
      })
      setSelectedUserId('')
      onUpdate()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to grant access')
    }
  }

  const handleRevokeAccess = async (userId: string) => {
    if (!confirm('Are you sure you want to revoke access for this user?')) {
      return
    }

    try {
      await revokeAccess.mutateAsync(userId)
      onUpdate()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to revoke access')
    }
  }

  // Tiny inline SVGs — keeps the toolbar visually uniform with the other
  // header buttons (which also use small stroke icons).
  const svgProps = {
    width: 14,
    height: 14,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }

  const baseOutlineBtn =
    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium ' +
    'transition whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed'

  return (
    <>
      <div className="flex gap-1.5">
        <button
          onClick={() => setShowModal(true)}
          className={`${baseOutlineBtn} bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400`}
          title="Manage who can access this conversation"
          aria-label="Manage access"
        >
          <svg {...svgProps} aria-hidden="true">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </svg>
          <span className="hidden sm:inline">Manage Access</span>
        </button>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col">
            {/* Header */}
            <div className="bg-dizzaroo-deep-blue text-white px-6 py-4 rounded-t-2xl">
              <h2 className="text-xl font-bold">Manage Conversation Access</h2>
              <p className="text-sm opacity-90 mt-1">{conversation.subject || 'Conversation'}</p>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* Current Status + confidentiality toggle */}
              <div className="bg-gray-50 p-4 rounded-lg">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-gray-700 mb-2">Current Status</h3>
                    <div className="flex gap-2 flex-wrap">
                      <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                        conversation.is_confidential === 'true'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-green-100 text-green-700'
                      }`}>
                        {conversation.is_confidential === 'true' ? '🔐 Confidential' : '🌐 Public'}
                      </span>
                      <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                        conversation.is_restricted === 'true'
                          ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-gray-100 text-gray-700'
                      }`}>
                        {conversation.is_restricted === 'true' ? '🔒 Restricted' : 'Open'}
                      </span>
                    </div>
                  </div>
                  {canManage && (
                    <button
                      onClick={handleToggleConfidential}
                      disabled={loading}
                      className={`${baseOutlineBtn} shrink-0 ${
                        conversation.is_confidential === 'true'
                          ? 'bg-amber-50 border border-amber-300 text-amber-800 hover:bg-amber-100'
                          : 'bg-red-50 border border-red-300 text-red-700 hover:bg-red-100'
                      }`}
                      title={
                        conversation.is_confidential === 'true'
                          ? 'Make this conversation public (visible to everyone on the site)'
                          : 'Mark this conversation confidential (only users below can access it)'
                      }
                    >
                      <svg {...svgProps} aria-hidden="true">
                        <rect x="3" y="11" width="18" height="11" rx="2" />
                        <path
                          d={
                            conversation.is_confidential === 'true'
                              ? 'M7 11V7a5 5 0 0 1 9.9-1'
                              : 'M7 11V7a5 5 0 0 1 10 0v4'
                          }
                        />
                      </svg>
                      {conversation.is_confidential === 'true' ? 'Make Public' : 'Mark Confidential'}
                    </button>
                  )}
                </div>
                {conversation.is_confidential === 'true' && (
                  <p className="text-xs text-gray-500 mt-3">
                    Only the users listed below can access this conversation. Add readers in “Grant Access”.
                  </p>
                )}
              </div>

              {/* Grant Access */}
              <div className="border-2 border-gray-200 rounded-lg p-4">
                <h3 className="font-semibold text-gray-700 mb-3">Grant Access</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      User ID
                    </label>
                    <input
                      type="text"
                      value={selectedUserId}
                      onChange={(e) => setSelectedUserId(e.target.value)}
                      className="w-full px-3 py-2 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue"
                      placeholder="Enter user ID or email"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Access Type
                    </label>
                    <select
                      value={accessType}
                      onChange={(e) => setAccessType(e.target.value as 'read' | 'write' | 'admin')}
                      className="w-full px-3 py-2 border-2 border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue text-gray-900 bg-white"
                    >
                      <option value="read">Read Only</option>
                      <option value="write">Read & Write</option>
                      <option value="admin">Admin (Full Access)</option>
                    </select>
                  </div>
                  <button
                    onClick={handleGrantAccess}
                    disabled={loading || !selectedUserId.trim()}
                    className="w-full px-4 py-2 bg-dizzaroo-deep-blue text-white rounded-xl font-semibold hover:bg-dizzaroo-blue-green transition disabled:opacity-50"
                  >
                    Grant Access
                  </button>
                </div>
              </div>

              {/* Access List */}
              <div>
                <h3 className="font-semibold text-gray-700 mb-3">Users with Access</h3>
                {accessList.length === 0 ? (
                  <p className="text-gray-500 text-sm">No explicit access grants</p>
                ) : (
                  <div className="space-y-2">
                    {accessList.map((access) => (
                      <div
                        key={access.id}
                        className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                      >
                        <div>
                          <div className="font-medium text-sm text-gray-800">{access.user_id}</div>
                          <div className="text-xs text-gray-500">
                            {access.access_type} • Granted by {access.granted_by || 'System'}
                          </div>
                        </div>
                        <button
                          onClick={() => handleRevokeAccess(access.user_id)}
                          disabled={loading}
                          className="px-3 py-1 bg-red-500 text-white text-xs rounded hover:bg-red-600 transition disabled:opacity-50"
                        >
                          Revoke
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {error && (
                <div className="bg-red-50 border-2 border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="border-t-2 border-gray-200 px-6 py-4 flex justify-end">
              <button
                onClick={() => {
                  setShowModal(false)
                  setError(null)
                }}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-semibold hover:bg-gray-300 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default PrivilegedActions

