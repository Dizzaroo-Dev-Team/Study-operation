// Dashboard — study-level home page.
// Body is the CTMS Operational Dashboards mockup ported to React (see
// features/study-dashboard/components/MockupDashboard.tsx). Sections are wired
// to live study_db_01 data where the schema supports them; the rest fall back
// to the original mockup demo content until backend endpoints land.
import React from 'react'
import { useStudySite } from '@/contexts/StudySiteContext'
import MockupDashboard from '@/features/study-dashboard/components/MockupDashboard'

const Dashboard: React.FC = () => {
  const { studies, selectedStudyId, loading } = useStudySite()
  const study = studies.find((s) => s.id === selectedStudyId) ?? null

  const studyLabel = loading ? 'Loading…' : study ? study.name : 'Select a study'
  const studyMeta = study?.description ?? ''

  return (
    <div className="flex flex-col h-full">
      <MockupDashboard studyLabel={studyLabel} studyMeta={studyMeta} />
    </div>
  )
}

export default Dashboard
