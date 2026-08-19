import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import {
  Building2,
  MapPin,
  Users,
  UserRound,
  FileText,
  Shield,
  Pencil,
  Save,
  Loader2,
  Info,
  Landmark,
} from 'lucide-react'
import { useStudySite } from '@/contexts/StudySiteContext'
import SiteRequiredPrompt from '@/components/SiteRequiredPrompt'
import { Button } from '@/components/ui/button'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { cn } from '@/lib/utils'
import {
  SiteProfile,
  useSiteProfile,
  useUpsertSiteProfile,
} from '@/lib/queries/useSiteProfile'
import sitePackageService from '@/modules/site-packages/services/sitePackageService'
import { useStudyTeam } from '@/lib/queries/useStudies'
import { isIrbExcludedFromCatalog } from '@/features/sites/utils/irbCatalog'
import { countries as irbFormCountries } from '@/features/sites/forms/IRBForm/formFields'
import { FormField, FORM_GRID } from '@/features/sites/forms/IRBForm/SectionShell'

interface SiteProfileTabProps {
  apiBase?: string
}

interface IrbOption {
  id: number
  name: string
  unique_code?: string | null
  country?: string | null
}

interface StaffOption {
  id: string
  staff_name: string
  email: string | null
  study_role: string
}

const PROFILE_SECTIONS = [
  { id: 'identification', num: 1, title: 'Identification', description: 'Site and hospital names', icon: Building2, bg: 'bg-sky-50 text-sky-700' },
  { id: 'pi', num: 2, title: 'Principal Investigator', description: 'PI contact and department details', icon: UserRound, bg: 'bg-violet-50 text-violet-700' },
  { id: 'sub_investigator', num: 3, title: 'Sub Investigator', description: 'Sub-I contact and department details', icon: UserRound, bg: 'bg-fuchsia-50 text-fuchsia-700' },
  { id: 'contract', num: 4, title: 'Contract Details', description: 'Contracting entity and signatory', icon: FileText, bg: 'bg-amber-50 text-amber-700' },
  { id: 'address', num: 5, title: 'Address', description: 'Site location and country', icon: MapPin, bg: 'bg-emerald-50 text-emerald-700' },
  { id: 'contacts', num: 6, title: 'Operational Contacts', description: 'Coordinator and site head', icon: Users, bg: 'bg-rose-50 text-rose-700' },
  { id: 'irb', num: 7, title: 'Ethics Review IRB/IEC', description: 'IRB mapping for this site', icon: Shield, bg: 'bg-indigo-50 text-indigo-700' },
] as const

const SECTION_IDS = PROFILE_SECTIONS.map((s) => s.id)

const normalizeRoleKey = (role: string) => role.trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')

const PI_ROLE_KEYS = ['principal investigator'].map(normalizeRoleKey)
const SUB_INVESTIGATOR_ROLE_KEYS = ['sub investigator'].map(normalizeRoleKey)
const SITE_COORDINATOR_ROLE_KEYS = ['clinical research coordinator', 'study coordinator', 'crc'].map(
  normalizeRoleKey,
)

function accordionStorageKey(siteId: string | null) {
  return `crm.site-profile.open-sections.${siteId || 'none'}`
}

function readOpenSections(siteId: string | null) {
  try {
    const raw = localStorage.getItem(accordionStorageKey(siteId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((id) => SECTION_IDS.includes(id))
  } catch {
    return []
  }
}

function writeOpenSections(siteId: string | null, openIds: string[]) {
  try {
    localStorage.setItem(accordionStorageKey(siteId), JSON.stringify(openIds))
  } catch {
    // ignore
  }
}

function fieldClass(hasError?: boolean, readOnly?: boolean) {
  return cn(
    'w-full h-10 px-3 rounded-lg border text-sm shadow-sm transition focus:outline-none focus:ring-2 focus:ring-[#168AAD]/30 focus:border-[#168AAD]',
    readOnly
      ? 'border-slate-200 bg-slate-50 text-slate-600 cursor-not-allowed'
      : hasError
        ? 'border-rose-400 bg-rose-50/40'
        : 'border-slate-200 bg-white',
  )
}

function SectionTrigger({ section }: { section: (typeof PROFILE_SECTIONS)[number] }) {
  const Icon = section.icon
  return (
    <div className="flex flex-1 items-center gap-4 min-w-0">
      <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl shadow-sm', section.bg)}>
        <Icon className="h-5 w-5" strokeWidth={2} />
      </div>
      <div className="min-w-0 text-left">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
            Section {section.num}
          </span>
          <span className="text-base font-semibold text-slate-900">{section.title}</span>
        </div>
        <p className="text-xs text-slate-500 mt-0.5 truncate">{section.description}</p>
      </div>
    </div>
  )
}

const SiteProfileTab: React.FC<SiteProfileTabProps> = () => {
  const { selectedSiteId, selectedStudyId, filteredSites } = useStudySite()
  const profileQuery = useSiteProfile(selectedSiteId)
  const upsertMutation = useUpsertSiteProfile(selectedSiteId)
  const teamQuery = useStudyTeam(selectedStudyId)
  const staffList: StaffOption[] = useMemo(() => {
    const rows = teamQuery.data?.data ?? []
    return rows.map((r: any) => {
      const studies = Array.isArray(r.studies) ? r.studies : []
      const match =
        studies.find((s: any) => s.study_id === selectedStudyId || s.id === selectedStudyId) || studies[0]
      return {
        id: r.user_id,
        staff_name: r.name,
        email: r.email ?? null,
        study_role: match?.role || '',
      }
    })
  }, [teamQuery.data, selectedStudyId])
  const profile: SiteProfile | null = profileQuery.data ?? null
  const loading = Boolean(selectedSiteId) && profileQuery.isLoading
  const saving = upsertMutation.isPending
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({})

  const [irbs, setIrbs] = useState<IrbOption[]>([])
  const [loadingIrbs, setLoadingIrbs] = useState(false)
  const [selectedIrbId, setSelectedIrbId] = useState<string>('')
  const [loadingIrbMapping, setLoadingIrbMapping] = useState(false)
  const [savingIrbMapping, setSavingIrbMapping] = useState(false)
  const [irbRefreshTrigger, setIrbRefreshTrigger] = useState(0)
  const [isEditing, setIsEditing] = useState(false)
  const [openSections, setOpenSections] = useState(() => readOpenSections(selectedSiteId))
  const [activeSection, setActiveSection] = useState<string>(PROFILE_SECTIONS[0].id)
  const prevCountryRef = useRef<string>('')

  const selectedSite = useMemo(() => {
    if (!selectedSiteId) return null
    return (
      filteredSites.find(
        (x) => x.id === selectedSiteId || x.site_id === selectedSiteId
      ) ?? null
    )
  }, [filteredSites, selectedSiteId])

  const siteUuid = useMemo(() => {
    return selectedSite?.id ? String(selectedSite.id) : null
  }, [selectedSite])

  const selectedSiteName = useMemo(() => selectedSite?.name?.trim() || '', [selectedSite])

  const countryOptions = useMemo(() => {
    // Build a comprehensive country list from browser Intl data when available.
    const intlAny = Intl as any
    const hasDisplayNames = typeof intlAny?.DisplayNames === 'function'
    const hasSupportedValuesOf = typeof intlAny?.supportedValuesOf === 'function'
    if (hasDisplayNames && hasSupportedValuesOf) {
      try {
        const display = new intlAny.DisplayNames(['en'], { type: 'region' })
        const regions: string[] = intlAny.supportedValuesOf('region') || []
        const options = regions
          .map((code) => String(display.of(code) || '').trim())
          .filter((name) => name && name.length > 1 && !/^\d+$/.test(name))
          .map((name) => ({ value: name, label: name }))
          .sort((a, b) => a.label.localeCompare(b.label))
        if (options.length > 0) return options
      } catch {
        // Fallback below.
      }
    }
    // Fallback to shared list from IRB form fields.
    return (irbFormCountries || []).map((c: any) => ({
      value: String(c?.value || ''),
      label: String(c?.label || c?.value || ''),
    }))
  }, [])

  // Form state
  const [formData, setFormData] = useState<Partial<SiteProfile>>({
    site_name: '',
    hospital_name: '',
    pi_name: '',
    pi_email: '',
    pi_phone: '',
    primary_contracting_entity: '',
    authorized_signatory_name: '',
    authorized_signatory_email: '',
    authorized_signatory_title: '',
    address_line_1: '',
    city: '',
    state: '',
    country: '',
    postal_code: '',
    site_coordinator_name: '',
    site_coordinator_email: '',
    site_coordinator_phone: '',
    site_head_name: '',
    site_head_email: '',
    site_head_phone: '',
    pi_designation: '',
    pi_department: '',
    sub_investigator_name: '',
    sub_investigator_email: '',
    sub_investigator_phone: '',
    sub_investigator_designation: '',
    sub_investigator_department: '',
  })

  // Reset editing UI + clear stale form when the site changes; the actual
  // profile fetch lives in useSiteProfile() above.
  useEffect(() => {
    setIsEditing(false)
    if (!selectedSiteId) {
      setFormData({
        site_name: '',
        hospital_name: '',
        pi_name: '',
        pi_email: '',
        pi_phone: '',
        primary_contracting_entity: '',
        authorized_signatory_name: '',
        authorized_signatory_email: '',
        authorized_signatory_title: '',
        address_line_1: '',
        city: '',
        state: '',
        country: '',
        postal_code: '',
        site_coordinator_name: '',
        site_coordinator_email: '',
        site_coordinator_phone: '',
        site_head_name: '',
        site_head_email: '',
        site_head_phone: '',
        pi_designation: '',
        pi_department: '',
        sub_investigator_name: '',
        sub_investigator_email: '',
        sub_investigator_phone: '',
        sub_investigator_designation: '',
        sub_investigator_department: '',
      })
    }
  }, [selectedSiteId])

  useEffect(() => {
    setOpenSections(readOpenSections(selectedSiteId))
    setActiveSection(PROFILE_SECTIONS[0].id)
  }, [selectedSiteId])

  const scrollToSection = useCallback((sectionId: string) => {
    setActiveSection(sectionId)
    setOpenSections((prev) => (prev.includes(sectionId) ? prev : [...prev, sectionId]))
    requestAnimationFrame(() => {
      setTimeout(() => {
        document.getElementById(`site-profile-section-${sectionId}`)?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        })
      }, 120)
    })
  }, [])

  useEffect(() => {
    writeOpenSections(selectedSiteId, openSections)
  }, [selectedSiteId, openSections])

  useEffect(() => {
    if (!selectedSiteName) return
    setFormData((prev) => ({ ...prev, site_name: selectedSiteName }))
  }, [selectedSiteName])

  // Seed the editable form fields from the freshly-loaded profile. Subsequent
  // edits stay in local state until handleSave fires the mutation.
  useEffect(() => {
    if (!profileQuery.isSuccess) return
    const data = profileQuery.data
    if (!data) return
    setFormData({
      site_name: data.site_name || selectedSiteName,
      hospital_name: data.hospital_name || '',
      pi_name: data.pi_name || '',
      pi_email: data.pi_email || '',
      pi_phone: data.pi_phone || '',
      primary_contracting_entity: data.primary_contracting_entity || '',
      authorized_signatory_name: data.authorized_signatory_name || '',
      authorized_signatory_email: data.authorized_signatory_email || '',
      authorized_signatory_title: data.authorized_signatory_title || '',
      address_line_1: data.address_line_1 || '',
      city: data.city || '',
      state: data.state || '',
      country: data.country || selectedSite?.country || '',
      postal_code: data.postal_code || '',
      site_coordinator_name: data.site_coordinator_name || '',
      site_coordinator_email: data.site_coordinator_email || '',
      site_coordinator_phone: data.site_coordinator_phone || '',
      site_head_name: data.site_head_name || '',
      site_head_email: data.site_head_email || '',
      site_head_phone: data.site_head_phone || '',
      pi_designation: data.pi_designation || '',
      pi_department: data.pi_department || '',
      sub_investigator_name: data.sub_investigator_name || '',
      sub_investigator_email: data.sub_investigator_email || '',
      sub_investigator_phone: data.sub_investigator_phone || '',
      sub_investigator_designation: data.sub_investigator_designation || '',
      sub_investigator_department: data.sub_investigator_department || '',
    })
  }, [profileQuery.isSuccess, profileQuery.data, selectedSiteName, selectedSite?.country])

  // Surface a non-404 fetch error.
  useEffect(() => {
    if (!profileQuery.isError) return
    const err = profileQuery.error as any
    setError(err?.response?.data?.detail || 'Failed to load site profile')
  }, [profileQuery.isError, profileQuery.error])

  // Listen for IRB list updates (e.g., when IRB name changes in IRBAdministrativeInfo)
  useEffect(() => {
    const handleIrbListUpdate = () => {
      setIrbRefreshTrigger((prev) => prev + 1)
    }
    window.addEventListener('irb-list-updated', handleIrbListUpdate)
    return () => {
      window.removeEventListener('irb-list-updated', handleIrbListUpdate)
    }
  }, [])

  const normalizeCountry = (value?: string | null) =>
    String(value || '')
      .trim()
      .toLowerCase()
      .replace(/\s+/g, ' ')

  const selectedCountry = String(formData.country || '').trim()
  const normalizedSelectedCountry = normalizeCountry(selectedCountry)

  useEffect(() => {
    let cancelled = false
    const fetchIrbs = async () => {
      if (!normalizedSelectedCountry) {
        if (!cancelled) setIrbs([])
        return
      }
      setLoadingIrbs(true)
      try {
        const res = await sitePackageService.listIrbs({ country: selectedCountry })
        const raw = (res as any)?.data
        const list = Array.isArray(raw) ? raw : []
        const filtered = (list as IrbOption[]).filter(
          (i) => !isIrbExcludedFromCatalog(i?.name, i?.unique_code)
        )
        if (!cancelled) setIrbs(filtered)
      } catch {
        if (!cancelled) setIrbs([])
      } finally {
        if (!cancelled) setLoadingIrbs(false)
      }
    }
    fetchIrbs()
    return () => {
      cancelled = true
    }
  }, [irbRefreshTrigger, normalizedSelectedCountry, selectedCountry])

  useEffect(() => {
    let cancelled = false
    const fetchMapping = async () => {
      if (!siteUuid) {
        setSelectedIrbId('')
        return
      }
      setLoadingIrbMapping(true)
      try {
        const res = await sitePackageService.getSiteIrbMapping(siteUuid)
        const data = (res as any)?.data
        if (!cancelled && (res as any)?.cleared_country_mismatch) {
          setSuccess(
            (res as any)?.message ||
              'Previous IRB selection did not match site country and was cleared. Please select again.'
          )
          setTimeout(() => setSuccess(null), 5000)
        }
        const id = data?.irb_id
        if (!cancelled) setSelectedIrbId(id != null && id !== '' ? String(id) : '')
      } catch {
        if (!cancelled) setSelectedIrbId('')
      } finally {
        if (!cancelled) setLoadingIrbMapping(false)
      }
    }
    fetchMapping()
    return () => {
      cancelled = true
    }
  }, [siteUuid])

  const filteredIrbs = useMemo(() => {
    if (!normalizedSelectedCountry) return []
    return irbs.filter(
      (i) => normalizeCountry(i.country) === normalizedSelectedCountry
    )
  }, [irbs, normalizedSelectedCountry])

  useEffect(() => {
    const currentCountry = normalizedSelectedCountry
    if (!isEditing) {
      prevCountryRef.current = currentCountry
      return
    }

    const prevCountry = prevCountryRef.current
    if (prevCountry && prevCountry !== currentCountry && selectedIrbId) {
      setSelectedIrbId('')
      setSuccess('Country changed. Please re-select IRB/IEC for this country.')
      setTimeout(() => setSuccess(null), 3500)
    }
    prevCountryRef.current = currentCountry
  }, [normalizedSelectedCountry, isEditing, selectedIrbId])

  const handleIrbChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value
    setSelectedIrbId(v)
    if (!siteUuid || v === '') return
    const irbId = parseInt(v, 10)
    if (Number.isNaN(irbId)) return
    setSavingIrbMapping(true)
    setError(null)
    try {
      await sitePackageService.saveSiteIrbMapping({
        site_id: siteUuid,
        irb_id: irbId,
      })
      window.dispatchEvent(new Event('site-irb-mapping-changed'))
      setSuccess('IRB selection saved for this site.')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      const d = err?.response?.data?.detail
      const msg =
        typeof d === 'string'
          ? d
          : Array.isArray(d)
            ? d.map((x: { msg?: string }) => x?.msg || String(x)).join('; ')
            : err?.message || 'Failed to save IRB mapping'
      setError(msg)
    } finally {
      setSavingIrbMapping(false)
    }
  }


  const validateForm = (): boolean => {
    const errors: Record<string, string> = {}

    if (!formData.pi_name?.trim()) {
      errors.pi_name = 'PI Name is required'
    }

    if (!formData.pi_email?.trim()) {
      errors.pi_email = 'PI Email is required'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.pi_email)) {
      errors.pi_email = 'Invalid email format'
    }

    if (!formData.pi_phone?.trim()) {
      errors.pi_phone = 'PI Phone is required'
    }

    if (!formData.pi_designation?.trim()) {
      errors.pi_designation = 'PI Designation is required'
    }

    if (!formData.pi_department?.trim()) {
      errors.pi_department = 'PI Department is required'
    }

    if (!formData.authorized_signatory_name?.trim()) {
      errors.authorized_signatory_name = 'Authorized Signatory Name is required'
    }

    if (!formData.authorized_signatory_email?.trim()) {
      errors.authorized_signatory_email = 'Authorized Signatory Email is required'
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.authorized_signatory_email)) {
      errors.authorized_signatory_email = 'Invalid email format'
    }

    if (!formData.hospital_name?.trim()) {
      errors.hospital_name = 'Hospital Name is required'
    }

    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSave = async () => {
    if (!selectedSiteId) {
      setError('No site selected')
      return
    }

    if (!validateForm()) {
      setError('Please fix validation errors before saving')
      return
    }

    setError(null)
    setSuccess(null)

    try {
      const isUpdate = Boolean(profile)
      await upsertMutation.mutateAsync({
        payload: { ...formData, site_name: selectedSiteName || formData.site_name },
        isUpdate,
      })
      setSuccess(isUpdate ? 'Site profile updated successfully' : 'Site profile created successfully')

      // Clear success message after 3 seconds
      setTimeout(() => setSuccess(null), 3000)
      setIsEditing(false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save site profile')
    }
  }

  const handleInputChange = (field: keyof SiteProfile, value: string) => {
    if (!isEditing) return
    setFormData((prev) => ({ ...prev, [field]: value }))
    // Clear validation error for this field
    if (validationErrors[field]) {
      setValidationErrors((prev) => {
        const newErrors = { ...prev }
        delete newErrors[field]
        return newErrors
      })
    }
  }

  const piStaff = useMemo(
    () => staffList.filter((s) => PI_ROLE_KEYS.includes(normalizeRoleKey(s.study_role || ''))),
    [staffList],
  )
  const subInvestigatorStaff = useMemo(
    () => staffList.filter((s) => SUB_INVESTIGATOR_ROLE_KEYS.includes(normalizeRoleKey(s.study_role || ''))),
    [staffList],
  )
  const siteCoordinatorStaff = useMemo(
    () => staffList.filter((s) => SITE_COORDINATOR_ROLE_KEYS.includes(normalizeRoleKey(s.study_role || ''))),
    [staffList],
  )

  const handleStaffNameSelect = (
    nameField: keyof SiteProfile,
    emailField: keyof SiteProfile,
    roleStaff: typeof staffList,
    value: string,
  ) => {
    if (!isEditing) return
    const match = roleStaff.find((s) => s.staff_name === value)
    setFormData((prev) => ({
      ...prev,
      [nameField]: value,
      [emailField]: match?.email || '',
    }))
    setValidationErrors((prev) => {
      if (!prev[nameField] && !prev[emailField]) return prev
      const newErrors = { ...prev }
      delete newErrors[nameField]
      delete newErrors[emailField]
      return newErrors
    })
  }

  const fieldsDisabled = !isEditing || saving
  const panelClass = 'space-y-2'

  const renderSectionContent = (sectionId: string) => {
    switch (sectionId) {
      case 'identification':
        return (
          <div className={FORM_GRID}>
            <FormField label="Site Name">
              <input
                type="text"
                value={formData.site_name || selectedSiteName || ''}
                readOnly
                className={fieldClass(false, true)}
              />
            </FormField>
            <FormField label="Hospital Name" required error={validationErrors.hospital_name}>
              <input
                type="text"
                value={formData.hospital_name || ''}
                onChange={(e) => handleInputChange('hospital_name', e.target.value)}
                disabled={fieldsDisabled}
                className={fieldClass(Boolean(validationErrors.hospital_name))}
              />
            </FormField>
          </div>
        )
      case 'pi':
        return (
          <div className={FORM_GRID}>
            <FormField label="PI Name" required error={validationErrors.pi_name}>
              <select
                value={String(formData.pi_name || '')}
                onChange={(e) => handleStaffNameSelect('pi_name', 'pi_email', piStaff, e.target.value)}
                disabled={fieldsDisabled}
                className={fieldClass(Boolean(validationErrors.pi_name))}
              >
                <option value="">Select PI</option>
                {piStaff.map((s) => (
                  <option key={s.id} value={s.staff_name}>
                    {s.staff_name}
                  </option>
                ))}
              </select>
            </FormField>
            {(
              [
                ['pi_email', 'PI Email', true, 'email'],
                ['pi_phone', 'PI Phone', true, 'tel'],
                ['pi_designation', 'Designation', true, 'text'],
                ['pi_department', 'Department', true, 'text'],
              ] as const
            ).map(([field, label, required, type]) => (
              <FormField key={field} label={label} required={required} error={validationErrors[field]}>
                <input
                  type={type}
                  value={String(formData[field] || '')}
                  onChange={(e) => handleInputChange(field, e.target.value)}
                  disabled={fieldsDisabled}
                  className={fieldClass(Boolean(validationErrors[field]))}
                />
              </FormField>
            ))}
          </div>
        )
      case 'sub_investigator':
        return (
          <div className={FORM_GRID}>
            <FormField label="Sub Investigator Name" error={validationErrors.sub_investigator_name}>
              <select
                value={String(formData.sub_investigator_name || '')}
                onChange={(e) =>
                  handleStaffNameSelect('sub_investigator_name', 'sub_investigator_email', subInvestigatorStaff, e.target.value)
                }
                disabled={fieldsDisabled}
                className={fieldClass(Boolean(validationErrors.sub_investigator_name))}
              >
                <option value="">Select Sub Investigator</option>
                {subInvestigatorStaff.map((s) => (
                  <option key={s.id} value={s.staff_name}>
                    {s.staff_name}
                  </option>
                ))}
              </select>
            </FormField>
            {(
              [
                ['sub_investigator_email', 'Sub Investigator Email', 'email'],
                ['sub_investigator_phone', 'Sub Investigator Phone', 'tel'],
                ['sub_investigator_designation', 'Designation', 'text'],
                ['sub_investigator_department', 'Department', 'text'],
              ] as const
            ).map(([field, label, type]) => (
              <FormField key={field} label={label} error={validationErrors[field]}>
                <input
                  type={type}
                  value={String(formData[field] || '')}
                  onChange={(e) => handleInputChange(field, e.target.value)}
                  disabled={fieldsDisabled}
                  className={fieldClass(Boolean(validationErrors[field]))}
                />
              </FormField>
            ))}
          </div>
        )
      case 'contract':
        return (
          <div className={FORM_GRID}>
            <FormField label="Primary Contracting Entity">
              <input
                type="text"
                value={formData.primary_contracting_entity || ''}
                onChange={(e) => handleInputChange('primary_contracting_entity', e.target.value)}
                disabled={fieldsDisabled}
                className={fieldClass()}
              />
            </FormField>
            <FormField label="Authorized Signatory Name" required error={validationErrors.authorized_signatory_name}>
              <input
                type="text"
                value={formData.authorized_signatory_name || ''}
                onChange={(e) => handleInputChange('authorized_signatory_name', e.target.value)}
                disabled={fieldsDisabled}
                className={fieldClass(Boolean(validationErrors.authorized_signatory_name))}
              />
            </FormField>
            <FormField label="Authorized Signatory Email" required error={validationErrors.authorized_signatory_email}>
              <input
                type="email"
                value={formData.authorized_signatory_email || ''}
                onChange={(e) => handleInputChange('authorized_signatory_email', e.target.value)}
                disabled={fieldsDisabled}
                className={fieldClass(Boolean(validationErrors.authorized_signatory_email))}
              />
            </FormField>
            <FormField label="Authorized Signatory Title">
              <input
                type="text"
                value={formData.authorized_signatory_title || ''}
                onChange={(e) => handleInputChange('authorized_signatory_title', e.target.value)}
                disabled={fieldsDisabled}
                className={fieldClass()}
              />
            </FormField>
          </div>
        )
      case 'address':
        return (
          <div className={panelClass}>
            <FormField label="Address Line 1">
              <input
                type="text"
                value={formData.address_line_1 || ''}
                onChange={(e) => handleInputChange('address_line_1', e.target.value)}
                disabled={fieldsDisabled}
                className={fieldClass()}
              />
            </FormField>
            <div className={FORM_GRID}>
              <FormField label="City">
                <input
                  type="text"
                  value={formData.city || ''}
                  onChange={(e) => handleInputChange('city', e.target.value)}
                  disabled={fieldsDisabled}
                  className={fieldClass()}
                />
              </FormField>
              <FormField label="State">
                <input
                  type="text"
                  value={formData.state || ''}
                  onChange={(e) => handleInputChange('state', e.target.value)}
                  disabled={fieldsDisabled}
                  className={fieldClass()}
                />
              </FormField>
              <FormField label="Country">
                <select
                  value={formData.country || ''}
                  onChange={(e) => handleInputChange('country', e.target.value)}
                  disabled={fieldsDisabled}
                  className={fieldClass()}
                >
                  <option value="">Select country</option>
                  {countryOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                  {formData.country &&
                  !countryOptions.some((opt) => opt.value === formData.country) ? (
                    <option value={formData.country}>{formData.country}</option>
                  ) : null}
                </select>
              </FormField>
              <FormField label="Postal Code">
                <input
                  type="text"
                  value={formData.postal_code || ''}
                  onChange={(e) => handleInputChange('postal_code', e.target.value)}
                  disabled={fieldsDisabled}
                  className={fieldClass()}
                />
              </FormField>
            </div>
          </div>
        )
      case 'contacts':
        return (
          <div className={FORM_GRID}>
            <FormField label="Site Coordinator Name (CRC)">
              <select
                value={String(formData.site_coordinator_name || '')}
                onChange={(e) =>
                  handleStaffNameSelect('site_coordinator_name', 'site_coordinator_email', siteCoordinatorStaff, e.target.value)
                }
                disabled={fieldsDisabled}
                className={fieldClass()}
              >
                <option value="">Select Site Coordinator</option>
                {siteCoordinatorStaff.map((s) => (
                  <option key={s.id} value={s.staff_name}>
                    {s.staff_name}
                  </option>
                ))}
              </select>
            </FormField>
            {(
              [
                ['site_coordinator_email', 'Site Coordinator Email', 'email'],
                ['site_coordinator_phone', 'Site Coordinator Phone', 'tel'],
                ['site_head_name', 'Site Head Name', 'text'],
                ['site_head_email', 'Site Head Email', 'email'],
                ['site_head_phone', 'Site Head Phone', 'tel'],
              ] as const
            ).map(([field, label, type]) => (
              <FormField key={field} label={label}>
                <input
                  type={type}
                  value={String(formData[field] || '')}
                  onChange={(e) => handleInputChange(field, e.target.value)}
                  disabled={fieldsDisabled}
                  className={fieldClass()}
                />
              </FormField>
            ))}
          </div>
        )
      case 'irb':
        return (
          <div className={panelClass}>
            <p className="text-sm text-slate-600 mb-4">
              Select the IRB for this site. Site Package uses this mapping automatically.
            </p>
            <FormField label="IRB / IEC" className="max-w-md">
              <select
                value={selectedIrbId}
                onChange={handleIrbChange}
                disabled={
                  fieldsDisabled ||
                  !siteUuid ||
                  !normalizedSelectedCountry ||
                  loadingIrbs ||
                  loadingIrbMapping ||
                  savingIrbMapping
                }
                className={fieldClass()}
              >
                <option value="">
                  {!normalizedSelectedCountry
                    ? 'Please select a country first.'
                    : loadingIrbMapping
                      ? 'Loading...'
                      : 'Select IRB'}
                </option>
                {filteredIrbs.map((irb) => (
                  <option key={irb.id} value={String(irb.id)}>
                    {irb.name}
                  </option>
                ))}
              </select>
              {!normalizedSelectedCountry ? (
                <p className="text-xs text-slate-500 mt-1">Please select a country in the Address section first.</p>
              ) : null}
              {savingIrbMapping ? (
                <p className="text-xs text-slate-500 mt-1">Saving mapping...</p>
              ) : null}
            </FormField>
          </div>
        )
      default:
        return null
    }
  }

  if (!selectedSiteId) {
    return <SiteRequiredPrompt fullPage feature="the site profile" />
  }

  if (loading) {
    return (
      <div className="h-full min-h-0 w-full flex items-center justify-center bg-gradient-to-b from-slate-50 to-white">
        <div className="flex items-center gap-3 text-slate-600">
          <Loader2 className="h-5 w-5 animate-spin text-[#168AAD]" />
          Loading site profileâ€¦
        </div>
      </div>
    )
  }

  return (
    <div className="h-full min-h-0 w-full overflow-y-auto bg-gradient-to-b from-slate-50 via-white to-slate-50/80">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 pb-8 space-y-6">
        <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm" data-testid="site-profile-header">
          <div
            className="absolute inset-0 opacity-[0.07]"
            style={{ background: 'linear-gradient(135deg, #168AAD 0%, #76C893 100%)' }}
          />
          <div className="relative px-6 py-6 sm:px-8 sm:py-7">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-start gap-4 min-w-0">
                <div
                  className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl text-white shadow-md"
                  style={{ background: 'linear-gradient(135deg, #168AAD 0%, #76C893 100%)' }}
                >
                  <Landmark className="h-6 w-6" />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#168AAD] mb-1">
                    Site Registry
                  </p>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Site Profile</h1>
                  <p className="text-sm text-slate-600 mt-1.5 max-w-xl leading-relaxed">
                    Core site identity, contacts, and ethics committee mapping for the selected site.
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {selectedSiteName && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-medium text-slate-600 shadow-sm">
                    <MapPin className="h-3.5 w-3.5 text-[#168AAD]" />
                    {selectedSiteName}
                  </span>
                )}
                <span
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold border',
                    isEditing
                      ? 'bg-amber-50 text-amber-800 border-amber-200'
                      : 'bg-slate-100 text-slate-600 border-slate-200',
                  )}
                >
                  {isEditing ? (
                    <>
                      <Pencil className="h-3 w-3" />
                      Editing
                    </>
                  ) : (
                    <>
                      <Shield className="h-3 w-3" />
                      View only
                    </>
                  )}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2" data-testid="site-profile-sections">
          {PROFILE_SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => scrollToSection(s.id)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[11px] font-medium shadow-sm transition cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#168AAD]/30',
                activeSection === s.id
                  ? 'border-[#168AAD] bg-sky-50 text-[#168AAD] ring-1 ring-[#168AAD]/25'
                  : 'text-slate-600 bg-white hover:border-slate-300 hover:bg-slate-50',
              )}
            >
              <span className={cn('flex h-5 w-5 items-center justify-center rounded-md text-[10px] font-bold', s.bg)}>
                {s.num}
              </span>
              {s.title}
            </button>
          ))}
        </div>

        {!profile && (
          <div className="flex items-start gap-2 rounded-xl border border-sky-100 bg-sky-50/60 px-4 py-3 text-sm text-sky-800">
            <Info className="h-4 w-4 shrink-0 mt-0.5 text-sky-600" />
            No profile yet â€” fill in the sections below and click Save to create one.
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {success && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {success}
          </div>
        )}

        <Accordion
          type="multiple"
          value={openSections}
          onValueChange={(next) => setOpenSections(Array.isArray(next) ? next : [])}
          className="space-y-3"
        >
          {PROFILE_SECTIONS.map((section) => (
            <AccordionItem
              key={section.id}
              id={`site-profile-section-${section.id}`}
              value={section.id}
              className="rounded-2xl border border-slate-200/90 bg-white shadow-sm overflow-hidden data-[state=open]:shadow-md transition-shadow scroll-mt-24"
            >
              <AccordionTrigger className="hover:no-underline px-5 py-4 sm:px-6 sm:py-5 [&[data-state=open]]:bg-gradient-to-r [&[data-state=open]]:from-slate-50/80 [&[data-state=open]]:to-white">
                <SectionTrigger section={section} />
              </AccordionTrigger>
              <AccordionContent className="px-4 sm:px-5 pb-4 pt-1">
                <div className="rounded-xl border border-slate-100 bg-slate-50/40 p-3 sm:p-4">
                  {renderSectionContent(section.id)}
                </div>
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>

        {!isEditing && (
          <div className="flex items-start gap-2 rounded-xl border border-sky-100 bg-sky-50/60 px-4 py-3 text-xs text-sky-800">
            <Info className="h-4 w-4 shrink-0 mt-0.5 text-sky-600" />
            Click <strong>Edit</strong> to update site profile fields.
          </div>
        )}

        <div className="sticky bottom-0 z-10 rounded-2xl border border-slate-200/80 bg-white/95 backdrop-blur-md shadow-lg px-4 sm:px-6 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-slate-500 hidden sm:block">
              {profile ? 'Profile saved' : 'New profile â€” not saved yet'}
            </p>
            <div className="flex items-center gap-2 ml-auto">
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsEditing(true)}
                disabled={isEditing || saving}
                className="rounded-xl border-slate-200 hover:bg-slate-50 gap-2"
              >
                <Pencil className="h-4 w-4" />
                Edit
              </Button>
              <Button
                type="button"
                onClick={handleSave}
                disabled={saving || !isEditing}
                className="rounded-xl gap-2 text-white border-0 shadow-md hover:opacity-95 transition-opacity"
                style={{ background: 'linear-gradient(135deg, #168AAD 0%, #76C893 100%)' }}
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Savingâ€¦
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Save
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SiteProfileTab
