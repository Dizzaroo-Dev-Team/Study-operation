/**
 * Conversations + threads query hooks.
 *
 * Sample migration sketches:
 *
 *     // Listing
 *     const { data: conversations = [] } = useConversationsList({ study_id, site_id })
 *
 *     // Detail
 *     const { data: conversation } = useConversation(conversationId)
 *
 *     // Force re-fetch after sending a message:
 *     queryClient.invalidateQueries({ queryKey: QK.conversation(conversationId) })
 *
 * Today the conversations endpoint is the hottest route in the app
 * (UnifiedInbox + ConversationDetail + ConversationList all hammer it
 * independently). With this hook they all share one in-flight request.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryClient'

export interface ConversationListFilters {
  study_id?: string | null
  site_id?: string | null
  channel?: string | null
  limit?: number
  offset?: number
}

export function useConversationsList(
  filters: ConversationListFilters = {},
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: QK.conversations(filters as Record<string, unknown>),
    queryFn: async () => {
      const params: Record<string, unknown> = {}
      if (filters.study_id) params.study_id = filters.study_id
      if (filters.site_id) params.site_id = filters.site_id
      if (filters.channel) params.channel = filters.channel
      if (filters.limit) params.limit = filters.limit
      if (filters.offset) params.offset = filters.offset
      const res = await api.get('/conversations', { params })
      return res.data ?? []
    },
    enabled: options?.enabled ?? true,
    // Conversations refresh on send/receive via WS-driven invalidation. A
    // short staleTime keeps polling-style remounts cheap without serving
    // truly stale data.
    staleTime: 15_000,
  })
}

export function useConversation(
  conversationId: string | null | undefined,
  options?: { limit?: number; offset?: number },
) {
  return useQuery({
    queryKey: QK.conversation(conversationId ?? ''),
    queryFn: async () => {
      if (!conversationId) return null
      const params: Record<string, number> = {}
      if (options?.limit) params.limit = options.limit
      if (options?.offset) params.offset = options.offset
      const res = await api.get(`/conversations/${conversationId}`, { params })
      return res.data
    },
    enabled: Boolean(conversationId),
    // Conversation detail (messages) is updated by WS push; staleTime is a
    // small buffer so quick re-mounts (tab switch + back) don't refetch.
    staleTime: 5_000,
  })
}

/**
 * Create-conversation mutation.
 *
 * On success: invalidates the conversation list so the new row shows up in
 * every consumer of `useConversationsList` (sidebar, command palette, …)
 * without manual refetch calls.
 *
 * Usage:
 *     const createConv = useCreateConversation()
 *     createConv.mutate(payload, {
 *       onSuccess: (newConv) => setSelectedConversationId(newConv.id)
 *     })
 */
export interface CreateConversationPayload {
  participant_phone?: string
  participant_email?: string
  participant_emails?: string[]
  subject?: string
  study_id?: string | null
  site_id?: string | null
}

export function useCreateConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: CreateConversationPayload) => {
      const res = await api.post('/conversations', payload)
      return res.data
    },
    onSuccess: () => {
      // Invalidate every conversation-list query, not just one filter combo,
      // because we don't know which filters are currently open in other
      // components (notice board view, all-sites view, etc.).
      qc.invalidateQueries({ queryKey: ['conversations'] })
    },
  })
}

export function useDeleteConversation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (conversationId: string) => {
      await api.delete(`/conversations/${conversationId}`)
      return conversationId
    },
    onSuccess: (conversationId) => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      qc.removeQueries({ queryKey: QK.conversation(conversationId) })
    },
  })
}

// -----------------------------------------------------------------------------
// Per-conversation access-grant list + mutations
// -----------------------------------------------------------------------------
// Used by PrivilegedActions: the modal shows who currently has explicit
// access to a confidential conversation, plus grant/revoke/patch buttons.
// Loose typing — the caller defines its own ConversationAccess shape.
export type ConversationAccess = any

export function useConversationAccess(
  conversationId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<ConversationAccess[]>({
    queryKey: ['conversation-access', conversationId],
    queryFn: async () => {
      if (!conversationId) return []
      const res = await api.get<ConversationAccess[]>(
        `/conversations/${conversationId}/access`,
      )
      return res.data ?? []
    },
    enabled: Boolean(conversationId) && (options?.enabled ?? true),
    staleTime: 30_000,
  })
}

export function useGrantConversationAccess(conversationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { user_id: string; access_type: string }) => {
      const res = await api.post(
        `/conversations/${conversationId}/grant-access`,
        payload,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversation-access', conversationId] })
    },
  })
}

export function useRevokeConversationAccess(conversationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (userId: string) => {
      const res = await api.delete(
        `/conversations/${conversationId}/revoke-access/${userId}`,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversation-access', conversationId] })
    },
  })
}

// -----------------------------------------------------------------------------
// AI summary for a conversation
// -----------------------------------------------------------------------------
// On-demand fetch backing InlineAISummary. Auto-fires once the conversation
// has enough messages; consumers can also force a refetch via `query.refetch()`.
export function useConversationSummary(
  conversationId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery<string | null>({
    queryKey: ['conversation-summary', conversationId],
    queryFn: async () => {
      const res = await api.get(`/conversations/${conversationId}/summary`)
      return res.data?.summary ?? null
    },
    enabled: Boolean(conversationId) && (options?.enabled ?? true),
    // Summaries are expensive to compute server-side; once we have one, let
    // it ride for the rest of the session. WS-pushed live updates from the
    // consumer bypass the cache via local state.
    staleTime: 5 * 60_000,
    retry: 0,
  })
}

export function usePatchConversationAccessFlags(conversationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { is_confidential?: boolean; is_restricted?: boolean }) => {
      const res = await api.patch(
        `/conversations/${conversationId}/access`,
        payload,
      )
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conversation-access', conversationId] })
      qc.invalidateQueries({ queryKey: ['conversations'] })
      qc.invalidateQueries({ queryKey: QK.conversation(conversationId) })
    },
  })
}
