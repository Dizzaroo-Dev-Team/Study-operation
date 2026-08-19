/**
 * Facility service.
 * - getFacilities: pulls from local backend /facilities (sourced from Azure Postgres).
 * - createFacility: writes to local /budgeting/site/facilities (used by SiteAssignmentForm).
 */
import { api } from '../../../../lib/api'

const BASE = '/budgeting/site/facilities'

// Backend returns flat camelCase fields; UI table reads facility.address?.city.
// Adapt by nesting address + aliasing siteType so existing components work unchanged.
const adaptFacility = (raw: Record<string, any>) => ({
  ...raw,
  // UI reads `facility.facilityId` for the displayed Facility ID column.
  // Backend ships the same string under `facilityCode`, so alias it.
  facilityId: raw.facilityCode,
  siteType: raw.facilityType,
  address: {
    street: raw.street ?? '',
    addressLine2: raw.addressLine2 ?? '',
    city: raw.city ?? '',
    state: raw.state ?? '',
    country: raw.country ?? '',
    postalCode: raw.postalCode ?? '',
  },
})

const generateFacilityCode = (facilityType: string, name: string): string => {
  const typePrefix = facilityType.substring(0, 4).toUpperCase()
  const namePrefix = name.substring(0, 4).toUpperCase()
  const randomStr = Math.random().toString(36).substring(2, 6).toUpperCase()
  return `${typePrefix}-${namePrefix}-${randomStr}`
}

class FacilityService {
  async getFacilities(params: Record<string, unknown> = {}) {
    try {
      const response = await api.get('/facilities', { params })
      const rawList: any[] = response.data?.data || []
      return {
        success: true,
        data: rawList.map(adaptFacility),
        pagination: response.data.pagination || {
          page: response.data.page || 1,
          limit: response.data.limit || 20,
          total: response.data.total || 0,
          pages: response.data.pages
            || Math.ceil((response.data.total || 0) / (response.data.limit || 20))
        },
        total: response.data.total || 0
      }
    } catch (error: any) {
      return {
        success: false,
        error: error.response?.data?.error || error.response?.data?.detail || 'Failed to fetch facilities'
      }
    }
  }

  async createFacility(facilityData: Record<string, unknown>) {
    try {
      const name = facilityData.name as string || ''
      const siteType = (facilityData.facilityType as string) || 'FACILITY'
      const facilityCode = generateFacilityCode(siteType, name)
      const facilityDataWithCode = {
        ...facilityData,
        facilityId: facilityCode
      }
      const response = await api.post(BASE, facilityDataWithCode)
      return {
        success: true,
        data: response.data
      }
    } catch (error: any) {
      return {
        success: false,
        error: error.response?.data?.error || 'Failed to create facility'
      }
    }
  }
}

export default new FacilityService()
