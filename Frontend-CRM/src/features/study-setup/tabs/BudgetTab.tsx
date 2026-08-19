import React from 'react'
import { CreateBudgetContainer } from '../../site-budgeting/CreateBudgetContainer'
import { useStudySite } from '../../../contexts/StudySiteContext'

const BudgetTab: React.FC = () => {
  const { selectedStudyId } = useStudySite()
  if (!selectedStudyId) {
    return <div className="p-6 text-sm text-slate-500">Select a study to build a budget.</div>
  }
  return <CreateBudgetContainer studyId={selectedStudyId} />
}

export default BudgetTab
