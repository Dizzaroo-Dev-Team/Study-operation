import React, { createContext, useContext, useEffect, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  refetchVisitWorkflowQueries,
  useConfirmationLetter,
  useFollowUpLetter,
  usePreVisitData,
  useVisitOverview,
  useVisitReport,
  type ConfirmationLetterPayload,
  type FollowUpLetterPayload,
  type PreVisitData,
  type VisitReportQueryData,
} from '@/lib/queries/useMonitoring'
import type { VisitOverviewPayload } from '../types'
import { computeWorkflowPollIntervalMs } from '../utils/visitWorkflowPoll'

export interface VisitWorkflowContextValue {
  visitId: string
  overview: VisitOverviewPayload | null
  overviewLoading: boolean
  report: VisitReportQueryData | null
  reportLoading: boolean
  preVisit: PreVisitData | null
  preVisitLoading: boolean
  followUp: FollowUpLetterPayload | null
  followUpLoading: boolean
  confirmationLetter: ConfirmationLetterPayload | null
  confirmationLetterLoading: boolean
  visitReportStatus: string
  preVisitReportStatus: string
  preVisitReviewedAt: string | null
  isFollowUpAcknowledged: boolean
  confirmationLetterConfirmedAt: string | null
}

const VisitWorkflowContext = createContext<VisitWorkflowContextValue | null>(null)

const WORKFLOW_QUERY_OPTS = {
  staleTime: 30_000,
  refetchOnWindowFocus: true as const,
}

export function VisitWorkflowProvider({
  visitId,
  children,
}: {
  visitId: string
  children: React.ReactNode
}) {
  const queryClient = useQueryClient()
  const overviewQuery = useVisitOverview(visitId, WORKFLOW_QUERY_OPTS)
  const reportQuery = useVisitReport(visitId, WORKFLOW_QUERY_OPTS)
  const preVisitQuery = usePreVisitData(visitId, WORKFLOW_QUERY_OPTS)
  const followUpQuery = useFollowUpLetter(visitId, WORKFLOW_QUERY_OPTS)
  const confirmationQuery = useConfirmationLetter(visitId, WORKFLOW_QUERY_OPTS)

  const pollInterval = useMemo(
    () =>
      computeWorkflowPollIntervalMs({
        overview: overviewQuery.data,
        confirmationLetter: confirmationQuery.data,
        preVisit: preVisitQuery.data,
        followUp: followUpQuery.data,
        report: reportQuery.data,
      }),
    [
      overviewQuery.data,
      confirmationQuery.data,
      preVisitQuery.data,
      followUpQuery.data,
      reportQuery.data,
    ],
  )

  useEffect(() => {
    if (!pollInterval) return undefined
    const timer = window.setInterval(() => {
      void refetchVisitWorkflowQueries(queryClient, visitId)
    }, pollInterval)
    return () => window.clearInterval(timer)
  }, [pollInterval, queryClient, visitId])

  const value = useMemo((): VisitWorkflowContextValue => {
    const preVisit = preVisitQuery.data ?? null
    const preVisitReportStatus =
      String(preVisit?.preVisitReportStatus || 'DRAFT')
        .trim()
        .toUpperCase() || 'DRAFT'
    const preVisitReviewedAt =
      typeof preVisit?.preVisitReviewedAt === 'string' && preVisit.preVisitReviewedAt.trim()
        ? preVisit.preVisitReviewedAt.trim()
        : null

    const followUp = followUpQuery.data ?? null
    const confirmationLetter = confirmationQuery.data ?? null
    const confirmedAt = confirmationLetter?.confirmed_at
    const confirmationLetterConfirmedAt =
      typeof confirmedAt === 'string' && confirmedAt.trim() ? confirmedAt.trim() : null

    return {
      visitId,
      overview: overviewQuery.data ?? null,
      overviewLoading: overviewQuery.isPending,
      report: reportQuery.data ?? null,
      reportLoading: reportQuery.isPending,
      preVisit,
      preVisitLoading: preVisitQuery.isPending,
      followUp,
      followUpLoading: followUpQuery.isPending,
      confirmationLetter,
      confirmationLetterLoading: confirmationQuery.isPending,
      visitReportStatus: String(reportQuery.data?.payload?.reportStatus ?? 'Draft'),
      preVisitReportStatus,
      preVisitReviewedAt,
      isFollowUpAcknowledged: followUp?.ack_status === 'acknowledged',
      confirmationLetterConfirmedAt,
    }
  }, [
    visitId,
    overviewQuery.data,
    overviewQuery.isPending,
    reportQuery.data,
    reportQuery.isPending,
    preVisitQuery.data,
    preVisitQuery.isPending,
    followUpQuery.data,
    followUpQuery.isPending,
    confirmationQuery.data,
    confirmationQuery.isPending,
  ])

  return (
    <VisitWorkflowContext.Provider value={value}>
      {children}
    </VisitWorkflowContext.Provider>
  )
}

export function useVisitWorkflow(): VisitWorkflowContextValue {
  const ctx = useContext(VisitWorkflowContext)
  if (!ctx) {
    throw new Error('useVisitWorkflow must be used within VisitWorkflowProvider')
  }
  return ctx
}
