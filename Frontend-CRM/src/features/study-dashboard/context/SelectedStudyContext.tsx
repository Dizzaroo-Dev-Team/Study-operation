/*
 * SelectedStudyContext — shared state for the dashboard's study selector.
 *
 * On mount it fetches the active studies from the Data Platform Study Registry
 * (via the backend proxy) and prepends the hardcoded study_db_01 study, which
 * stays the default selection so existing dashboard behavior is unchanged.
 * If the registry is unreachable the dropdown still offers the local study and
 * the dashboard remains fully functional.
 */
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { DashboardStudy } from '../types'
import { LOCAL_STUDY, getStudies } from '../services/studyRegistry.api'

interface SelectedStudyContextValue {
  /** Local study first, then active registry studies (name-sorted). */
  studies: DashboardStudy[]
  selectedStudy: DashboardStudy
  setSelectedStudy: (study: DashboardStudy) => void
  /** True while the registry list is being fetched. */
  studiesLoading: boolean
  /** Non-null when the registry fetch failed (local study still usable). */
  studiesError: string | null
}

const SelectedStudyContext = createContext<SelectedStudyContextValue | undefined>(undefined)

export const useSelectedStudy = (): SelectedStudyContextValue => {
  const ctx = useContext(SelectedStudyContext)
  if (!ctx) {
    throw new Error('useSelectedStudy must be used within SelectedStudyProvider')
  }
  return ctx
}

export const SelectedStudyProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [registryStudies, setRegistryStudies] = useState<DashboardStudy[]>([])
  const [selectedStudy, setSelectedStudy] = useState<DashboardStudy>(LOCAL_STUDY)
  const [studiesLoading, setStudiesLoading] = useState(true)
  const [studiesError, setStudiesError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    getStudies()
      .then((items) => {
        if (!alive) return
        const sorted = [...items].sort((a, b) => a.studyName.localeCompare(b.studyName))
        setRegistryStudies(sorted)
      })
      .catch((e: any) => {
        if (!alive) return
        setStudiesError(e?.response?.data?.detail ?? e?.message ?? 'Unable to load studies.')
      })
      .finally(() => {
        if (alive) setStudiesLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  const value = useMemo<SelectedStudyContextValue>(
    () => ({
      studies: [LOCAL_STUDY, ...registryStudies],
      selectedStudy,
      setSelectedStudy,
      studiesLoading,
      studiesError,
    }),
    [registryStudies, selectedStudy, studiesLoading, studiesError],
  )

  return <SelectedStudyContext.Provider value={value}>{children}</SelectedStudyContext.Provider>
}
