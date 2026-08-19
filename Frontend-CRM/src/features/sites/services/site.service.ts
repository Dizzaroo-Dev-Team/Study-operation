import { api } from '@/lib/api'

class SiteService {
  /**
   * Matches the standalone Site Packages module's contract.
   * Expects: { study: string, limit?: number }
   */
  async getAllSites(params: { study?: string; limit?: number }) {
    const study = params?.study
    const response = await api.get('/sites', {
      params: study ? { study_id: study } : undefined,
    })

    const sites = (response.data || []) as any[]
    const normalized = sites.map((s) => ({
      _id: s.id,
      siteId: s.site_id,
      siteCode: s.code,
      name: s.name,
      code: s.code,
      location: s.location,
      study_id: s.study_id,
      id: s.id,
      site_id: s.site_id,
    }))

    const limit = params?.limit ? Number(params.limit) : undefined
    const finalList = limit ? normalized.slice(0, limit) : normalized

    // Standalone module checks: resp?.data || resp?.sites || resp
    return { data: finalList, sites: finalList }
  }
}

export default new SiteService()

