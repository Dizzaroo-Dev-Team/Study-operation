import React from 'react'
import AgreementTab from '@/features/agreements/components/AgreementTab'

type Props = {
  apiBase?: string
}

const AgreementsTab: React.FC<Props> = ({ apiBase = '/api' }) => (
  <div className="h-full min-h-0">
    <AgreementTab apiBase={apiBase} />
  </div>
)

export default AgreementsTab
