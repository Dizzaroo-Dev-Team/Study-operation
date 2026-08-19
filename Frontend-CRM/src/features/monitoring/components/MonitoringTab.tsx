import React from 'react'
import MonitoringModule from '@/components/mon/App.tsx'
import SiteScopedTab from '@/components/workspace/SiteScopedTab'

const MonitoringTab: React.FC = () => {
  return (
    <SiteScopedTab featureName="Monitoring">
      <div className="h-full min-h-0" data-testid="monitoring-root">
        <MonitoringModule />
      </div>
    </SiteScopedTab>
  )
}

export default MonitoringTab

