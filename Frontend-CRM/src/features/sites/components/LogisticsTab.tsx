import React, { useState, useMemo } from 'react'
import { useStudySite } from '@/contexts/StudySiteContext'
import { useLogisticsList } from '@/lib/queries/useLogistics'
import { SiteLogistics } from '@/types'
import SiteLogisticsDetail from './SiteLogisticsDetail'
import SiteRequiredPrompt from '@/components/SiteRequiredPrompt'

const LogisticsTab: React.FC = () => {
  const { selectedStudyId, selectedSiteId } = useStudySite()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedSite, setSelectedSite] = useState<SiteLogistics | null>(null)

  // Only fire the fetch once a site is selected (mirrors legacy behavior of
  // skipping the request when selectedSiteId is empty).
  const logisticsQuery = useLogisticsList({ enabled: Boolean(selectedSiteId) })
  const logistics: SiteLogistics[] = logisticsQuery.data ?? []

  // Filter logistics data - ONLY show selected site
  const filteredLogistics = useMemo(() => {
    // If no site selected, return empty array
    if (!selectedSiteId) {
      return []
    }

    // Filter to ONLY the selected site
    let data = logistics.filter((item) => item.siteId === selectedSiteId)

    // Apply search filter (only if needed, but should be empty since we're filtering by site)
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      data = data.filter(
        (item) =>
          item.siteName.toLowerCase().includes(query) ||
          item.location?.toLowerCase().includes(query)
      )
    }

    return data
  }, [logistics, selectedSiteId, searchQuery])

  // Calculate summary statistics for the selected site only
  const summaryStats = useMemo(() => {
    return filteredLogistics.reduce(
      (acc, item) => ({
        totalActivePatients: acc.totalActivePatients + item.activePatients,
        totalDrugRemaining: acc.totalDrugRemaining + item.drugRemaining,
        totalAmountPaid: acc.totalAmountPaid + (item.amountPaid || 0),
        totalAmountDue: acc.totalAmountDue + (item.amountDue || 0),
      }),
      {
        totalActivePatients: 0,
        totalDrugRemaining: 0,
        totalAmountPaid: 0,
        totalAmountDue: 0,
      }
    )
  }, [filteredLogistics])

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount)
  }

  if (!selectedStudyId || !selectedSiteId) {
    return <SiteRequiredPrompt fullPage feature="Logistics" />
  }

  if (selectedSite) {
    return (
      <SiteLogisticsDetail
        logistics={selectedSite}
        onBack={() => setSelectedSite(null)}
      />
    )
  }

  // Get the logistics data for the selected site
  const siteLogistics = filteredLogistics[0]

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden">
      <div className="flex-1 overflow-y-auto p-6" style={{ minHeight: 0 }}>
        {/* Page Header */}
        <div className="mb-6" data-testid="logistics-header">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Logistics</h1>
          <p className="text-gray-600">
            Overview of patients, drug inventory, and payments for this site.
          </p>
        </div>

        {/* Filter Bar - Simplified for single site */}
        <div className="bg-white rounded-lg shadow-sm p-4 mb-6 border border-gray-200">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">
                Search
              </label>
              <input
                type="text"
                placeholder="🔍 Search logistics data..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full px-3 py-2 border-2 border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-dizzaroo-deep-blue focus:border-dizzaroo-deep-blue transition-all"
              />
            </div>
          </div>
        </div>

        {/* Summary Cards - Single Site View */}
        {siteLogistics ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6" data-testid="logistics-stats">
              <div className="bg-gradient-to-br from-dizzaroo-deep-blue to-dizzaroo-blue-green text-white rounded-lg shadow-sm p-4">
                <div className="text-2xl font-bold">{summaryStats.totalActivePatients}</div>
                <div className="text-xs uppercase font-semibold opacity-90 mt-1">
                  Active Patients
                </div>
              </div>
              <div className="bg-gradient-to-br from-dizzaroo-deep-blue to-dizzaroo-blue-green text-white rounded-lg shadow-sm p-4">
                <div className="text-2xl font-bold">{summaryStats.totalDrugRemaining}</div>
                <div className="text-xs uppercase font-semibold opacity-90 mt-1">
                  Drug Remaining
                </div>
              </div>
              <div className="bg-gradient-to-br from-dizzaroo-deep-blue to-dizzaroo-blue-green text-white rounded-lg shadow-sm p-4">
                <div className="text-2xl font-bold">
                  {formatCurrency(summaryStats.totalAmountPaid)}
                </div>
                <div className="text-xs uppercase font-semibold opacity-90 mt-1">
                  Amount Paid
                </div>
              </div>
              <div className="bg-gradient-to-br from-dizzaroo-deep-blue to-dizzaroo-blue-green text-white rounded-lg shadow-sm p-4">
                <div className="text-2xl font-bold">
                  {formatCurrency(summaryStats.totalAmountDue)}
                </div>
                <div className="text-xs uppercase font-semibold opacity-90 mt-1">
                  Amount Due
                </div>
              </div>
            </div>

            {/* Site Logistics Card View */}
            <div
              onClick={() => setSelectedSite(siteLogistics)}
              className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden cursor-pointer hover:shadow-md transition"
            >
              {/* Site Header */}
              <div className="bg-gradient-to-r from-gray-50 to-gray-100 px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-bold text-gray-900">{siteLogistics.siteName}</h2>
                {siteLogistics.location && (
                  <p className="text-sm text-gray-600 mt-1">📍 {siteLogistics.location}</p>
                )}
              </div>

              {/* Logistics Data Grid */}
              <div className="p-6">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {/* Patients Section */}
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <h3 className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-3">
                      Patients
                    </h3>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-700">Total:</span>
                        <span className="text-sm font-bold text-gray-900">{siteLogistics.totalPatients}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-700">Active:</span>
                        <span className="text-sm font-bold text-green-700">{siteLogistics.activePatients}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-700">Completed:</span>
                        <span className="text-sm font-bold text-gray-700">{siteLogistics.completedPatients}</span>
                      </div>
                    </div>
                  </div>

                  {/* Drug Inventory Section */}
                  <div className={`border rounded-lg p-4 ${
                    siteLogistics.isDrugLow 
                      ? 'bg-red-50 border-red-200' 
                      : 'bg-green-50 border-green-200'
                  }`}>
                    <h3 className={`text-xs font-semibold uppercase tracking-wide mb-3 ${
                      siteLogistics.isDrugLow ? 'text-red-600' : 'text-green-600'
                    }`}>
                      Drug Inventory
                    </h3>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-700">Received:</span>
                        <span className="text-sm font-bold text-gray-900">{siteLogistics.drugReceived}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-700">Used:</span>
                        <span className="text-sm font-bold text-gray-900">{siteLogistics.drugUsed}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className={`text-sm font-semibold ${siteLogistics.isDrugLow ? 'text-red-700' : 'text-green-700'}`}>
                          Remaining:
                        </span>
                        <span className={`text-lg font-bold ${siteLogistics.isDrugLow ? 'text-red-800' : 'text-green-800'}`}>
                          {siteLogistics.drugRemaining}
                        </span>
                      </div>
                      {siteLogistics.isDrugLow && (
                        <div className="mt-2 px-2 py-1 bg-red-100 text-red-800 rounded text-xs font-semibold">
                          ⚠️ Low Inventory Warning
                        </div>
                      )}
                      {siteLogistics.drugReorderThreshold && (
                        <div className="text-xs text-gray-600 mt-1">
                          Reorder threshold: {siteLogistics.drugReorderThreshold}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Payments Section */}
                  <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                    <h3 className="text-xs font-semibold text-purple-600 uppercase tracking-wide mb-3">
                      Payments
                    </h3>
                    <div className="space-y-2">
                      {siteLogistics.totalBudget !== undefined && (
                        <div className="flex justify-between">
                          <span className="text-sm text-gray-700">Budget:</span>
                          <span className="text-sm font-bold text-gray-900">
                            {formatCurrency(siteLogistics.totalBudget)}
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-700">Paid:</span>
                        <span className="text-sm font-bold text-green-700">
                          {formatCurrency(siteLogistics.amountPaid || 0)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-gray-700">Due:</span>
                        <span className="text-sm font-bold text-orange-700">
                          {formatCurrency(siteLogistics.amountDue || 0)}
                        </span>
                      </div>
                      {siteLogistics.lastPaymentDate && (
                        <div className="text-xs text-gray-600 mt-2 pt-2 border-t border-purple-200">
                          Last payment: {new Date(siteLogistics.lastPaymentDate).toLocaleDateString()}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
            <div className="text-4xl mb-2">📭</div>
            <p className="text-gray-600">No logistics data found for this site</p>
            <p className="text-sm text-gray-500 mt-1">
              {searchQuery ? 'Try adjusting your search' : 'Logistics data will appear here once available'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

export default LogisticsTab
