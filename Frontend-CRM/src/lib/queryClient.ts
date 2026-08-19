/**
 * Shared TanStack Query client.
 *
 * Lives at the top of the app tree (App.tsx). Exists for two reasons:
 *
 * 1. **De-duplicate concurrent requests.** Today 5 components mounting in the
 *    same render tick all call /api/studies, getting back 5 identical
 *    responses. With a query client, identical queryKeys share a single
 *    in-flight request and a single cache entry.
 *
 * 2. **Replace hand-rolled `useEffect + setLoading + setData` boilerplate**
 *    that the perf audit found in 31 files. Each of those does its own
 *    caching, retry, abort, and error handling — badly, mostly. Query hooks
 *    centralize that.
 *
 * `staleTime` defaults err on the side of "stale is fine for a few seconds"
 * because the data this app shows (studies, sites, conversations,
 * agreements) changes on user actions that already invalidate the relevant
 * keys. Long staleTime + targeted invalidation is the cheap path.
 */
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Most reads are "show me whatever you have, refetch quietly if stale".
      // staleTime: 30s means re-mounts within 30s are instant cache hits;
      // anything older triggers a background refetch.
      staleTime: 30_000,
      // gcTime: keep cache around 5 min after the last subscriber unmounts so
      // route changes don't lose their data.
      gcTime: 5 * 60_000,
      // Refocus refetch is great for chat-style UIs (returning to the tab
      // pulls fresh data) but can be noisy on dashboards — keep it on for
      // now and disable per-hook if needed.
      refetchOnWindowFocus: true,
      // Retry once. The default 3 is too aggressive for an internal API.
      retry: 1,
    },
    mutations: {
      // Mutations should NOT retry by default — most are non-idempotent
      // (POST /conversations would create duplicates on retry).
      retry: 0,
    },
  },
})

// Query-key registry. Centralizing keys here means a `useStudies` invalidation
// from one file reaches every consumer in another file, without each having
// to remember the same string.
export const QK = {
  studies: () => ['studies'] as const,
  sites: (studyId: string | null | undefined) => ['sites', studyId] as const,
  conversations: (filters: Record<string, unknown> = {}) =>
    ['conversations', filters] as const,
  conversation: (id: string) => ['conversation', id] as const,
  threads: (filters: Record<string, unknown> = {}) =>
    ['threads', filters] as const,
  thread: (id: string) => ['thread', id] as const,
  agreement: (id: string) => ['agreement', id] as const,
  notifications: () => ['notifications'] as const,
  // CTA workflow
  ctaState: (agreementId: string) => ['cta-state', agreementId] as const,
  ctaPlaceholders: (agreementId: string) => ['cta-placeholders', agreementId] as const,
  myAssignments: () => ['cta-my-assignments'] as const,
} as const
