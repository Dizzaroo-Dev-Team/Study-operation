import React from 'react'
import SiteAssignmentManagement from '../../site-budgeting/site-creation/SiteAssignmentManagement'

const SiteSetup: React.FC = () => {
  return (
    <div className="p-6 space-y-8" data-testid="site-setup-root">
      <SiteAssignmentManagement />
    </div>
  )
}

export default SiteSetup
