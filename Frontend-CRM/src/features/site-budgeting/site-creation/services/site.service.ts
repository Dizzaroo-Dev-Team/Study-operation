/**
 * Site service — wraps /api/budgeting/site/sites endpoints.
 * Converted from Site-Creation/frontend/services/site.service.js.
 * ONLY the base path changed (/sites → /api/budgeting/site/sites).
 * All method signatures and return shapes are preserved exactly.
 */
import { api } from '../../../../lib/api'

const BASE = '/budgeting/site/sites'

class SiteService {
  async getAllSites(params: Record<string, unknown> = {}) {
    try {
      const response = await api.get(BASE, { params })
      return response.data
    } catch (error) {
      console.error('Error fetching sites:', error)
      throw error
    }
  }

  async getSite(id: string) {
    try {
      const response = await api.get(`${BASE}/${id}`)
      return response.data
    } catch (error) {
      console.error('Error fetching site:', error)
      throw error
    }
  }

  async createSite(siteData: Record<string, unknown>) {
    try {
      const response = await api.post(BASE, siteData)
      return response.data
    } catch (error) {
      console.error('Error creating site:', error)
      throw error
    }
  }

  async updateSite(id: string, updateData: Record<string, unknown>) {
    try {
      const response = await api.patch(`${BASE}/${id}`, updateData)
      return response.data
    } catch (error) {
      console.error('Error updating site:', error)
      throw error
    }
  }

  async deleteSite(id: string) {
    try {
      const response = await api.delete(`${BASE}/${id}`)
      return response.data
    } catch (error) {
      console.error('Error deleting site:', error)
      throw error
    }
  }

  async addPersonnel(id: string, personnelData: Record<string, unknown>) {
    try {
      const response = await api.post(`${BASE}/${id}/personnel`, personnelData)
      return response.data
    } catch (error) {
      console.error('Error adding personnel:', error)
      throw error
    }
  }

  async removePersonnel(id: string, userId: string) {
    try {
      const response = await api.delete(`${BASE}/${id}/personnel/${userId}`)
      return response.data
    } catch (error) {
      console.error('Error removing personnel:', error)
      throw error
    }
  }

  async getSitesByStudy(studyId: string) {
    try {
      const response = await api.get(`${BASE}/study/${studyId}`)
      return response.data
    } catch (error) {
      console.error('Error fetching sites by study:', error)
      throw error
    }
  }

  async getSitesByFacility(facilityId: string) {
    try {
      const response = await api.get(`${BASE}/facility/${facilityId}`)
      return response.data
    } catch (error) {
      console.error('Error fetching sites by facility:', error)
      throw error
    }
  }

  async getSitesByPrincipalInvestigator(userId: string) {
    try {
      const response = await api.get(`${BASE}/investigator/${userId}`)
      return response.data
    } catch (error) {
      console.error('Error fetching sites by investigator:', error)
      throw error
    }
  }

  // ── Utility methods (no API calls — preserved verbatim) ──────────────────

  generateSiteCode(
    study: { studyId?: string } | null,
    facility: { facilityId?: string } | null,
    principalInvestigator: { userId?: string } | null
  ) {
    if (!study || !facility || !principalInvestigator) return null
    const studyCode = study.studyId ? study.studyId.slice(-3) : 'STD'
    const facilityCode = facility.facilityId ? facility.facilityId.slice(-3) : 'FAC'
    const piCode = principalInvestigator.userId ? principalInvestigator.userId.slice(-3) : 'PI'
    return `SITE-${studyCode}-${facilityCode}-${piCode}`
  }

  transformSiteForForm(site: Record<string, any>) {
    return {
      siteCode: site.siteCode || '',
      study: site.study?._id || site.study?.id || (typeof site.study === 'string' ? site.study : '') || '',
      facility: site.facility?._id || site.facility?.id || (typeof site.facility === 'string' ? site.facility : '') || '',
      principalInvestigator: site.principalInvestigator?._id || site.principalInvestigator?.id || (typeof site.principalInvestigator === 'string' ? site.principalInvestigator : '') || '',
      status: site.status || 'PENDING',
      sitePersonnel: site.sitePersonnel?.map((personnel: any) => ({
        user: personnel.user?._id || '',
        role: personnel.role || ''
      })) || [],
      regulatoryApprovals: site.regulatoryApprovals || [],
      monitoring: site.monitoring || {},
      qualityMetrics: site.qualityMetrics || {},
      metadata: site.metadata || {}
    }
  }

  transformFormForAPI(formData: Record<string, any>) {
    return {
      siteCode: formData.siteCode,
      study: formData.study,
      facility: formData.facility,
      principalInvestigator: formData.principalInvestigator,
      status: formData.status,
      sitePersonnel: formData.sitePersonnel?.filter((p: any) => p.user && p.role) || [],
      regulatoryApprovals: formData.regulatoryApprovals || [],
      monitoring: formData.monitoring || {},
      qualityMetrics: formData.qualityMetrics || {},
      metadata: formData.metadata || {}
    }
  }

  getStatusOptions() {
    return [
      { value: 'PENDING', label: 'Pending', color: 'yellow' },
      { value: 'ACTIVE', label: 'Active', color: 'green' },
      { value: 'COMPLETED', label: 'Completed', color: 'blue' },
      { value: 'SUSPENDED', label: 'Suspended', color: 'orange' },
      { value: 'TERMINATED', label: 'Terminated', color: 'red' }
    ]
  }

  getPersonnelRoleOptions() {
    return [
      { value: 'PRINCIPAL_INVESTIGATOR', label: 'Principal Investigator' },
      { value: 'SUB_INVESTIGATOR', label: 'Sub Investigator' },
      { value: 'STUDY_COORDINATOR', label: 'Study Coordinator' },
      { value: 'RESEARCH_NURSE', label: 'Research Nurse' },
      { value: 'DATA_MANAGER', label: 'Data Manager' },
      { value: 'MONITOR', label: 'Monitor' },
      { value: 'PHARMACIST', label: 'Pharmacist' },
      { value: 'LAB_TECHNICIAN', label: 'Lab Technician' },
      { value: 'REGULATORY_SPECIALIST', label: 'Regulatory Specialist' }
    ]
  }

  getRegulatoryApprovalTypeOptions() {
    return [
      { value: 'IRB', label: 'IRB (Institutional Review Board)' },
      { value: 'EC', label: 'EC (Ethics Committee)' },
      { value: 'FDA', label: 'FDA (Food and Drug Administration)' },
      { value: 'EMA', label: 'EMA (European Medicines Agency)' },
      { value: 'OTHER', label: 'Other' }
    ]
  }

  getMonitoringFrequencyOptions() {
    return [
      { value: 'WEEKLY', label: 'Weekly' },
      { value: 'BIWEEKLY', label: 'Bi-weekly' },
      { value: 'MONTHLY', label: 'Monthly' },
      { value: 'QUARTERLY', label: 'Quarterly' },
      { value: 'CUSTOM', label: 'Custom' }
    ]
  }

  validateSiteData(siteData: Record<string, any>) {
    const errors: Record<string, string> = {}
    if (!siteData.study) errors.study = 'Study is required'
    if (!siteData.facility) errors.facility = 'Facility is required'
    if (!siteData.principalInvestigator) errors.principalInvestigator = 'Principal Investigator is required'
    return { isValid: Object.keys(errors).length === 0, errors }
  }

  getStatusColor(status: string) {
    switch (status) {
      case 'ACTIVE': return 'green'
      case 'PENDING': return 'yellow'
      case 'COMPLETED': return 'blue'
      case 'SUSPENDED': return 'orange'
      case 'TERMINATED': return 'red'
      default: return 'gray'
    }
  }

  formatSiteForDisplay(site: Record<string, any>) {
    return {
      ...site,
      statusColor: this.getStatusColor(site.status),
      fullSiteName: `${site.siteCode} - ${site.facility?.name || 'Unknown Facility'}`,
      principalInvestigatorName: site.principalInvestigator
        ? (site.principalInvestigator.name ||
           `${site.principalInvestigator.firstName || ''} ${site.principalInvestigator.lastName || ''}`.trim() ||
           site.principalInvestigator.user_id || 'Unknown')
        : 'Not Assigned',
      studyTitle: site.study?.title || 'Unknown Study',
      facilityName: site.facility?.name || 'Unknown Facility'
    }
  }
}

export default new SiteService()
