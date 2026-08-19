import React from 'react'
import { SiteLogistics } from '@/types'

interface SiteLogisticsDetailProps {
  logistics: SiteLogistics
  onBack: () => void
}

const SiteLogisticsDetail: React.FC<SiteLogisticsDetailProps> = ({
  logistics,
  onBack,
}) => {
  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount)
  }

  return (
    <div className="flex flex-col h-full bg-gray-50 p-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <button
            onClick={onBack}
            className="text-dizzaroo-deep-blue hover:text-dizzaroo-blue-green mb-2 text-sm font-medium flex items-center gap-1"
          >
            ← Back to Logistics
          </button>
          <h1 className="text-3xl font-bold text-gray-900">{logistics.siteName}</h1>
          {logistics.location && (
            <p className="text-gray-600 mt-1">📍 {logistics.location}</p>
          )}
        </div>
      </div>

      {/* Patients Section */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <h2 className="text-xl font-bold text-gray-800 mb-4">Patients</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-1">
              Total Patients
            </div>
            <div className="text-2xl font-bold text-blue-800">{logistics.totalPatients}</div>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="text-xs font-semibold text-green-600 uppercase tracking-wide mb-1">
              Active Patients
            </div>
            <div className="text-2xl font-bold text-green-800">
              {logistics.activePatients}
            </div>
          </div>
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">
              Completed Patients
            </div>
            <div className="text-2xl font-bold text-gray-800">
              {logistics.completedPatients}
            </div>
          </div>
        </div>
      </div>

      {/* Drug Inventory Section */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
        <h2 className="text-xl font-bold text-gray-800 mb-4">Drug Inventory</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <div className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-1">
              Drug Received
            </div>
            <div className="text-2xl font-bold text-blue-800">
              {logistics.drugReceived}
            </div>
          </div>
          <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
            <div className="text-xs font-semibold text-orange-600 uppercase tracking-wide mb-1">
              Drug Used
            </div>
            <div className="text-2xl font-bold text-orange-800">{logistics.drugUsed}</div>
          </div>
          <div
            className={`rounded-lg p-4 ${
              logistics.isDrugLow
                ? 'bg-red-50 border-red-200 border-2'
                : 'bg-green-50 border-green-200'
            }`}
          >
            <div
              className={`text-xs font-semibold uppercase tracking-wide mb-1 ${
                logistics.isDrugLow ? 'text-red-600' : 'text-green-600'
              }`}
            >
              Drug Remaining
            </div>
            <div
              className={`text-2xl font-bold ${
                logistics.isDrugLow ? 'text-red-800' : 'text-green-800'
              }`}
            >
              {logistics.drugRemaining}
            </div>
            {logistics.isDrugLow && (
              <div className="mt-2 px-2 py-1 bg-red-100 text-red-800 rounded text-xs font-semibold">
                ⚠️ Low Inventory Warning
              </div>
            )}
          </div>
          {logistics.drugReorderThreshold !== undefined && (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
              <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">
                Reorder Threshold
              </div>
              <div className="text-2xl font-bold text-gray-800">
                {logistics.drugReorderThreshold}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Payments Section */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h2 className="text-xl font-bold text-gray-800 mb-4">Payments</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {logistics.totalBudget !== undefined && (
            <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
              <div className="text-xs font-semibold text-purple-600 uppercase tracking-wide mb-1">
                Total Budget
              </div>
              <div className="text-2xl font-bold text-purple-800">
                {formatCurrency(logistics.totalBudget)}
              </div>
            </div>
          )}
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <div className="text-xs font-semibold text-green-600 uppercase tracking-wide mb-1">
              Amount Paid
            </div>
            <div className="text-2xl font-bold text-green-800">
              {formatCurrency(logistics.amountPaid || 0)}
            </div>
          </div>
          <div className="bg-orange-50 border border-orange-200 rounded-lg p-4">
            <div className="text-xs font-semibold text-orange-600 uppercase tracking-wide mb-1">
              Amount Due
            </div>
            <div className="text-2xl font-bold text-orange-800">
              {formatCurrency(logistics.amountDue || 0)}
            </div>
          </div>
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">
              Last Payment Date
            </div>
            <div className="text-lg font-bold text-gray-800">
              {logistics.lastPaymentDate
                ? new Date(logistics.lastPaymentDate).toLocaleDateString()
                : 'N/A'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SiteLogisticsDetail

