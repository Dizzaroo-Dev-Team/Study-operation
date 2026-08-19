import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { useForm } from 'react-hook-form'
import {
  Building2,
  MapPin,
  Users,
  UserCheck,
  CalendarDays,
  FileText,
  Landmark,
  Pencil,
  Save,
  Shield,
  Loader2,
  Info,
} from 'lucide-react'

import { api } from '@/lib/api'
import sitePackageService from '@/modules/site-packages/services/sitePackageService'
import { Button } from '@/components/ui/button'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { useToast } from '@/components/ui/use-toast'
import { useStudySite } from '@/contexts/StudySiteContext'
import { cn } from '@/lib/utils'

import BasicDemographics from '@/features/sites/forms/IRBForm/BasicDemographics'
import PhysicalAddress from '@/features/sites/forms/IRBForm/PhysicalAddress'
import ContactPersonnel from '@/features/sites/forms/IRBForm/ContactPersonnel'
import MembershipComposition from '@/features/sites/forms/IRBForm/MembershipComposition'
import MeetingSchedule from '@/features/sites/forms/IRBForm/MeetingSchedule'
import SubmissionRequirements from '@/features/sites/forms/IRBForm/SubmissionRequirements'
import BankingFeePaymentDetails from '@/features/sites/forms/IRBForm/BankingFeePaymentDetails'
import {
  normalizeIecTypeForDisplay,
  normalizeIrbTypeForDisplay,
  SUBMISSION_METHOD_HARD_COPY,
} from '@/features/sites/forms/IRBForm/formFields'
import {
  combineInternationalPhone,
  DEFAULT_PHONE_COUNTRY,
  splitStoredPhone,
} from '@/features/sites/forms/IRBForm/irbPhoneCountryCodes'

const defaultValues = {
  basic: {
    organizationType: '',
    irbName: '',
    iecName: '',
    irbType: '',
    iecType: '',
    registrationId: '',
    fwaNumber: '',
    ohrpRegistrationNumber: '',
    accreditationBody: '',
    accreditationNumber: '',
    accreditationExpiry: '',
    irbStatus: '',
    dateEstablished: '',
    country: '',
  },
  address: {
    line1: '',
    line2: '',
    city: '',
    state: '',
    zip: '',
    country: '',
    officeHours: '',
    timeZone: '',
  },
  contacts: {
    primary: {
      fullName: '',
      jobTitle: '',
      email: '',
      phoneCountryCode: DEFAULT_PHONE_COUNTRY,
      phone: '',
    },
    secondary: {
      fullName: '',
      jobTitle: '',
      email: '',
      phoneCountryCode: DEFAULT_PHONE_COUNTRY,
      phone: '',
    },
  },
  membership: {
    chairName: '',
    viceChairName: '',
    numberOfMembers: '',
    numberOfAlternates: '',
    quorumRequired: 'no',
    quorumThresholdPercent: '',
    quorumMinimumMembersPresent: '',
  },
  meetingSchedule: {
    fullBoardFrequency: '',
    usualMeetingDay: '',
    meetingDate: '',
    submissionDeadline: '',
  },
  submissionRequirements: {
    submissionType: '',
    submissionDate: '',
    submissionMethod: '',
    numberOfCopiesRequired: '',
    submissionFeeCurrency: 'USD',
    submissionFeeAmount: '',
    paymentMethod: '',
  },
  bankingFeePayment: {
    bankName: '',
    accountName: '',
    accountNumber: '',
    routingSwift: '',
    iban: '',
    currency: '',
    invoiceAddress: '',
  },
  reviewTypesStatus: {
    reviewCatalog: '',
    qualityMet: '',
    irbMeetingReviewDate: '',
    decisionOutcome: '',
    decisionDate: '',
    decisionLetterReference: '',
    approvalDate: '',
  },
}

const FORM_SECTIONS = [
  {
    id: 'basic',
    num: 1,
    title: 'Basic Demographics',
    description: 'Organization identity, status, and accreditation',
    icon: Building2,
    tone: 'from-sky-500 to-blue-600',
    bg: 'bg-sky-50 text-sky-700',
    component: BasicDemographics,
  },
  {
    id: 'address',
    num: 2,
    title: 'Physical Address',
    description: 'Administrative office location and hours',
    icon: MapPin,
    tone: 'from-emerald-500 to-teal-600',
    bg: 'bg-emerald-50 text-emerald-700',
    component: PhysicalAddress,
  },
  {
    id: 'contacts',
    num: 3,
    title: 'Contact Personnel',
    description: 'Primary and alternate administrative contacts',
    icon: Users,
    tone: 'from-violet-500 to-purple-600',
    bg: 'bg-violet-50 text-violet-700',
    component: ContactPersonnel,
  },
  {
    id: 'membership',
    num: 4,
    title: 'Membership Composition',
    description: 'Leadership, member counts, and quorum rules',
    icon: UserCheck,
    tone: 'from-amber-500 to-orange-600',
    bg: 'bg-amber-50 text-amber-700',
    component: MembershipComposition,
  },
  {
    id: 'meeting',
    num: 5,
    title: 'Meeting Schedule',
    description: 'Board cadence and submission deadlines',
    icon: CalendarDays,
    tone: 'from-rose-500 to-pink-600',
    bg: 'bg-rose-50 text-rose-700',
    component: MeetingSchedule,
  },
  {
    id: 'submission',
    num: 6,
    title: 'Submission Requirements',
    description: 'How and when submissions are accepted',
    icon: FileText,
    tone: 'from-indigo-500 to-blue-600',
    bg: 'bg-indigo-50 text-indigo-700',
    component: SubmissionRequirements,
  },
  {
    id: 'banking',
    num: 7,
    title: 'Banking & Fee Payment',
    description: 'Bank account and invoice details',
    icon: Landmark,
    tone: 'from-slate-600 to-slate-800',
    bg: 'bg-slate-100 text-slate-700',
    component: BankingFeePaymentDetails,
  },
]

const SECTION_IDS = FORM_SECTIONS.map((s) => s.id)

function accordionStorageKey(siteId) {
  return `crm.irb-admin.open-sections.${siteId || 'none'}`
}

function readOpenSections(siteId) {
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

function writeOpenSections(siteId, openIds) {
  try {
    localStorage.setItem(accordionStorageKey(siteId), JSON.stringify(openIds))
  } catch {
    // ignore quota / private mode
  }
}

function SectionTrigger({ section }) {
  const Icon = section.icon
  return (
    <div className="flex flex-1 items-center gap-4 min-w-0">
      <div
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl shadow-sm',
          section.bg,
        )}
      >
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

const IRBAdministrativeInfo = () => {
  const { toast } = useToast()
  const { selectedSiteId, sites, filteredSites } = useStudySite()
  const [saving, setSaving] = useState(false)
  const [loadingSaved, setLoadingSaved] = useState(false)
  const [savedIrbId, setSavedIrbId] = useState(null)
  const [isEditing, setIsEditing] = useState(false)
  const [openSections, setOpenSections] = useState(() => readOpenSections(selectedSiteId))
  const [activeSection, setActiveSection] = useState(FORM_SECTIONS[0].id)
  const savingRef = useRef(false)

  useEffect(() => {
    setOpenSections(readOpenSections(selectedSiteId))
    setActiveSection(FORM_SECTIONS[0].id)
  }, [selectedSiteId])

  const scrollToSection = useCallback((sectionId) => {
    setActiveSection(sectionId)
    setOpenSections((prev) => (prev.includes(sectionId) ? prev : [...prev, sectionId]))
    requestAnimationFrame(() => {
      setTimeout(() => {
        document.getElementById(`irb-admin-section-${sectionId}`)?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        })
      }, 120)
    })
  }, [])

  useEffect(() => {
    writeOpenSections(selectedSiteId, openSections)
  }, [selectedSiteId, openSections])

  const handleAccordionChange = (next) => {
    setOpenSections(Array.isArray(next) ? next : [])
  }

  const form = useForm({
    mode: 'onBlur',
    defaultValues,
  })

  const {
    handleSubmit,
    reset,
    watch,
    formState: { isSubmitting, isDirty },
  } = form

  const orgType = watch('basic.organizationType')
  const irbName = watch('basic.irbName')
  const iecName = watch('basic.iecName')

  const siteLabel = useMemo(() => {
    if (!selectedSiteId) return null
    const row =
      (filteredSites || []).find((s) => s.site_id === selectedSiteId || s.id === selectedSiteId) ||
      (sites || []).find((s) => s.site_id === selectedSiteId || s.id === selectedSiteId)
    return row?.name || selectedSiteId
  }, [selectedSiteId, filteredSites, sites])

  const displayOrgName = useMemo(() => {
    if (orgType === 'IEC' && iecName) return iecName
    if (orgType === 'IRB' && irbName) return irbName
    return null
  }, [orgType, irbName, iecName])

  const onInvalid = (errors) => {
    const firstKey = errors ? Object.keys(errors)[0] : null
    toast({
      title: 'Please fix validation errors',
      description: firstKey
        ? 'Some required fields are missing or invalid. Please review the highlighted fields.'
        : 'Form is invalid.',
      variant: 'destructive',
    })
  }

  const resolveSelectedSiteUuid = () => {
    if (!selectedSiteId) return null
    const siteRow =
      (Array.isArray(filteredSites) ? filteredSites : []).find(
        (s) => s.site_id === selectedSiteId || s.id === selectedSiteId,
      ) ||
      (Array.isArray(sites) ? sites : []).find(
        (s) => s.site_id === selectedSiteId || s.id === selectedSiteId,
      )
    return siteRow?.id || null
  }

  useEffect(() => {
    const loadLatest = async () => {
      setIsEditing(false)
      const siteUuid = resolveSelectedSiteUuid()
      if (!siteUuid) {
        setSavedIrbId(null)
        return
      }

      setLoadingSaved(true)
      setSavedIrbId(null)
      try {
        const mapping = await sitePackageService.getSiteIrbMapping(siteUuid)
        const rawIrbId = mapping?.data?.irb_id ?? mapping?.irb_id
        if (rawIrbId == null || rawIrbId === '') {
          reset(defaultValues)
          return
        }
        const irbIdNum = Number(rawIrbId)
        if (!Number.isFinite(irbIdNum)) {
          reset(defaultValues)
          return
        }
        setSavedIrbId(irbIdNum)

        const res = await api.get('/irb-administrative-info/latest', {
          params: { irb_id: irbIdNum },
        })

        if (!res?.data) {
          reset(defaultValues)
          return
        }

        const d = res.data
        const rawOrgType = String(d.organization_type || '').toUpperCase()
        const organizationType =
          rawOrgType === 'BOTH' ? 'IRB' : rawOrgType === 'IEC' ? 'IEC' : rawOrgType === 'IRB' ? 'IRB' : ''

        reset({
          basic: {
            organizationType,
            irbName: d.irb_name || '',
            iecName: d.iec_name || '',
            irbType: normalizeIrbTypeForDisplay(d.irb_type),
            iecType: normalizeIecTypeForDisplay(d.iec_type),
            registrationId: d.registration_id || '',
            fwaNumber: d.fwa_number || '',
            ohrpRegistrationNumber: d.ohrp_number || '',
            accreditationBody: d.accreditation_body || '',
            accreditationNumber: d.accreditation_number || '',
            accreditationExpiry: d.accreditation_expiry || '',
            irbStatus: d.irb_status || '',
            dateEstablished: d.date_established || '',
            country: d.jurisdiction || '',
          },
          address: {
            line1: d.address_line_1 || '',
            line2: d.address_line_2 || '',
            city: d.city || '',
            state: d.state || '',
            zip: d.zip_code || '',
            country: d.country || '',
            officeHours: d.office_hours || '',
            timeZone: d.time_zone || '',
          },
          contacts: {
            primary: {
              fullName: d.primary_contact_name || '',
              jobTitle: d.primary_contact_job_title || '',
              email: d.primary_contact_email || '',
              ...(() => {
                const sp = splitStoredPhone(d.primary_contact_phone)
                return { phoneCountryCode: sp.countryCode, phone: sp.national }
              })(),
            },
            secondary: {
              fullName: d.secondary_contact_name || '',
              jobTitle: d.secondary_contact_job_title || '',
              email: d.secondary_contact_email || '',
              ...(() => {
                const sp = splitStoredPhone(d.secondary_contact_phone)
                return { phoneCountryCode: sp.countryCode, phone: sp.national }
              })(),
            },
          },
          membership: {
            chairName: d.chair_name || '',
            viceChairName: d.vice_chair_name || '',
            numberOfMembers: d.number_of_members != null ? String(d.number_of_members) : '',
            numberOfAlternates: d.number_of_alternates != null ? String(d.number_of_alternates) : '',
            quorumRequired: d.quorum_required === true ? 'yes' : 'no',
            quorumThresholdPercent:
              d.quorum_threshold_percent != null && d.quorum_threshold_percent !== ''
                ? String(d.quorum_threshold_percent).replace(/%$/, '')
                : '',
            quorumMinimumMembersPresent:
              d.quorum_minimum_members_present != null
                ? String(d.quorum_minimum_members_present)
                : '',
          },
          meetingSchedule: {
            fullBoardFrequency: d.full_board_meeting_frequency || '',
            usualMeetingDay: d.usual_meeting_day || '',
            meetingDate: d.meeting_date || '',
            submissionDeadline: d.submission_deadline_before_meeting || '',
          },
          submissionRequirements: {
            submissionType: d.submission_type || '',
            submissionDate: d.submission_date || '',
            submissionMethod: d.submission_method || '',
            numberOfCopiesRequired:
              d.number_of_copies_required != null && d.number_of_copies_required !== ''
                ? String(d.number_of_copies_required)
                : '',
            submissionFeeCurrency: d.submission_fee_currency || 'USD',
            submissionFeeAmount:
              d.submission_fee_amount != null && d.submission_fee_amount !== ''
                ? String(d.submission_fee_amount)
                : '',
            paymentMethod: d.payment_method || '',
          },
          bankingFeePayment: {
            bankName: d.bank_name || '',
            accountName: d.bank_account_name || '',
            accountNumber: d.bank_account_number || '',
            routingSwift: d.routing_swift_code || '',
            iban: d.iban || '',
            currency: d.banking_currency || '',
            invoiceAddress: d.invoice_address_alt || '',
          },
          reviewTypesStatus: {
            reviewCatalog: d.review_catalog || '',
            qualityMet: d.quality_met || '',
            irbMeetingReviewDate: d.irb_meeting_review_date || '',
            decisionOutcome: d.decision_outcome || '',
            decisionDate: d.decision_date || '',
            decisionLetterReference: d.decision_letter_reference || '',
            approvalDate: d.approval_date || '',
          },
        })
        if (d.irb_id != null) setSavedIrbId(Number(d.irb_id))
      } catch (e) {
        console.warn('Failed to load saved IRB Administrative Info:', e)
      } finally {
        setLoadingSaved(false)
      }
    }

    loadLatest()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSiteId, sites, filteredSites])

  const submit = async (data) => {
    if (savingRef.current) return
    savingRef.current = true
    setSaving(true)
    toast({ title: 'Saving…', description: 'Submitting IRB Administrative Info.' })
    if (!selectedSiteId) {
      toast({
        title: 'Site required',
        description: 'Please select a site from the top bar before saving IRB Administrative Info.',
        variant: 'destructive',
      })
      savingRef.current = false
      setSaving(false)
      return
    }

    const siteUuid = resolveSelectedSiteUuid()
    if (!siteUuid) {
      toast({
        title: 'Invalid site selection',
        description: 'Could not resolve the selected site UUID. Please re-select the site and try again.',
        variant: 'destructive',
      })
      savingRef.current = false
      setSaving(false)
      return
    }

    const payload = {
      irb_id: savedIrbId != null && Number.isFinite(Number(savedIrbId)) ? Number(savedIrbId) : null,
      organization_type: data?.basic?.organizationType || '',
      irb_name: data?.basic?.irbName || null,
      iec_name: data?.basic?.iecName || null,
      irb_type: data?.basic?.irbType || null,
      iec_type: data?.basic?.iecType || null,
      registration_id: data?.basic?.registrationId || null,
      fwa_number: data?.basic?.fwaNumber || null,
      ohrp_number: data?.basic?.ohrpRegistrationNumber || null,
      accreditation_body: data?.basic?.accreditationBody || null,
      accreditation_number: data?.basic?.accreditationNumber || null,
      accreditation_expiry: data?.basic?.accreditationExpiry || null,
      irb_status: data?.basic?.irbStatus || null,
      date_established: data?.basic?.dateEstablished || null,
      jurisdiction: data?.basic?.country || null,
      address_line_1: data?.address?.line1 || null,
      address_line_2: data?.address?.line2 || null,
      city: data?.address?.city || null,
      state: data?.address?.state || null,
      zip_code: data?.address?.zip || null,
      country: data?.address?.country || null,
      office_hours: data?.address?.officeHours || null,
      time_zone: data?.address?.timeZone || null,
      primary_contact_name: data?.contacts?.primary?.fullName || null,
      primary_contact_job_title: data?.contacts?.primary?.jobTitle || null,
      primary_contact_email: data?.contacts?.primary?.email || null,
      primary_contact_phone: combineInternationalPhone(
        data?.contacts?.primary?.phoneCountryCode,
        data?.contacts?.primary?.phone,
      ),
      secondary_contact_name: data?.contacts?.secondary?.fullName || null,
      secondary_contact_job_title: data?.contacts?.secondary?.jobTitle || null,
      secondary_contact_email: data?.contacts?.secondary?.email || null,
      secondary_contact_phone: (() => {
        const nat = String(data?.contacts?.secondary?.phone || '').replace(/\D/g, '')
        if (!nat) return null
        return combineInternationalPhone(
          data?.contacts?.secondary?.phoneCountryCode || DEFAULT_PHONE_COUNTRY,
          nat,
        )
      })(),
      chair_name: data?.membership?.chairName || null,
      vice_chair_name: data?.membership?.viceChairName || null,
      number_of_members:
        data?.membership?.numberOfMembers !== '' && data?.membership?.numberOfMembers != null
          ? Number(data.membership.numberOfMembers)
          : null,
      number_of_alternates:
        data?.membership?.numberOfAlternates !== '' && data?.membership?.numberOfAlternates != null
          ? Number(data.membership.numberOfAlternates)
          : null,
      quorum_required: data?.membership?.quorumRequired === 'yes',
      quorum_threshold_percent: (() => {
        if (data?.membership?.quorumRequired !== 'yes') return null
        const s = String(data.membership?.quorumThresholdPercent ?? '').trim().replace(/%+\s*$/, '')
        if (!s) return null
        const n = Number(s)
        return Number.isFinite(n) ? n : null
      })(),
      quorum_minimum_members_present:
        data?.membership?.quorumRequired === 'yes' &&
        data?.membership?.quorumMinimumMembersPresent !== '' &&
        data?.membership?.quorumMinimumMembersPresent != null
          ? Number(data.membership.quorumMinimumMembersPresent)
          : null,
      full_board_meeting_frequency: data?.meetingSchedule?.fullBoardFrequency || '',
      usual_meeting_day: data?.meetingSchedule?.usualMeetingDay || null,
      meeting_date: data?.meetingSchedule?.meetingDate || null,
      submission_deadline_before_meeting: data?.meetingSchedule?.submissionDeadline || null,
      submission_type: data?.submissionRequirements?.submissionType || null,
      submission_date: data?.submissionRequirements?.submissionDate || null,
      submission_method: data?.submissionRequirements?.submissionMethod || null,
      number_of_copies_required:
        data?.submissionRequirements?.submissionMethod === SUBMISSION_METHOD_HARD_COPY &&
        data?.submissionRequirements?.numberOfCopiesRequired !== '' &&
        data?.submissionRequirements?.numberOfCopiesRequired != null
          ? Number(data.submissionRequirements.numberOfCopiesRequired)
          : null,
      ...(() => {
        const raw = String(data?.submissionRequirements?.submissionFeeAmount ?? '').trim()
        if (raw === '') {
          return { submission_fee_currency: null, submission_fee_amount: null }
        }
        const n = Number(raw)
        if (!Number.isFinite(n) || n < 0) {
          return { submission_fee_currency: null, submission_fee_amount: null }
        }
        return {
          submission_fee_currency: data?.submissionRequirements?.submissionFeeCurrency || null,
          submission_fee_amount: n,
        }
      })(),
      payment_method: data?.submissionRequirements?.paymentMethod || null,
      review_catalog: data?.reviewTypesStatus?.reviewCatalog || null,
      quality_met: data?.reviewTypesStatus?.qualityMet || null,
      irb_meeting_review_date: data?.reviewTypesStatus?.irbMeetingReviewDate || null,
      decision_outcome: data?.reviewTypesStatus?.decisionOutcome || null,
      decision_date: data?.reviewTypesStatus?.decisionDate || null,
      decision_letter_reference: data?.reviewTypesStatus?.decisionLetterReference || null,
      approval_date: data?.reviewTypesStatus?.approvalDate || null,
      bank_name: data?.bankingFeePayment?.bankName || null,
      bank_account_name: data?.bankingFeePayment?.accountName || null,
      bank_account_number: data?.bankingFeePayment?.accountNumber || null,
      routing_swift_code: data?.bankingFeePayment?.routingSwift || null,
      iban: data?.bankingFeePayment?.iban || null,
      banking_currency: data?.bankingFeePayment?.currency || null,
      invoice_address_alt: data?.bankingFeePayment?.invoiceAddress || null,
    }

    try {
      const res = await api.post('/irb-administrative-info', payload)
      const newIrbId = res?.data?.irb_id
      if (newIrbId != null && newIrbId !== '') setSavedIrbId(Number(newIrbId))
      toast({
        title: 'Saved',
        description: res?.data?.irb_created
          ? 'Saved successfully. IRB record created for this site.'
          : 'Saved successfully.',
      })
      window.dispatchEvent(new Event('irb-list-updated'))
      setIsEditing(false)
    } catch (e) {
      const rawDetail = e?.response?.data?.detail
      const detail =
        Array.isArray(rawDetail)
          ? rawDetail
              .map((x) => {
                const path = Array.isArray(x?.loc) ? x.loc.join('.') : ''
                const msg = x?.msg || 'Invalid value'
                return path ? `${path}: ${msg}` : msg
              })
              .join(' | ')
          : rawDetail || e?.message || 'Failed to save IRB Administrative Info.'
      toast({
        title: 'Save failed',
        description: String(detail),
        variant: 'destructive',
      })
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  const fieldsDisabled = !isEditing || saving || loadingSaved

  return (
    <div className="h-full min-h-0 w-full overflow-y-auto bg-gradient-to-b from-slate-50 via-white to-slate-50/80">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 pb-28 space-y-6">
        {/* Hero header */}
        <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm" data-testid="irb-header">
          <div
            className="absolute inset-0 opacity-[0.07]"
            style={{
              background: 'linear-gradient(135deg, #168AAD 0%, #76C893 100%)',
            }}
          />
          <div className="absolute -right-8 -top-8 h-40 w-40 rounded-full bg-[#168AAD]/10 blur-2xl" />
          <div className="absolute -left-6 bottom-0 h-32 w-32 rounded-full bg-[#76C893]/10 blur-2xl" />

          <div className="relative px-6 py-6 sm:px-8 sm:py-7">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-start gap-4 min-w-0">
                <div
                  className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl text-white shadow-md"
                  style={{ background: 'linear-gradient(135deg, #168AAD 0%, #76C893 100%)' }}
                >
                  <Shield className="h-6 w-6" />
                </div>
                <div className="min-w-0">
                  <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#168AAD] mb-1">
                    Ethics Committee Registry
                  </p>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                    IRB Administrative Info
                  </h1>
                  <p className="text-sm text-slate-600 mt-1.5 max-w-xl leading-relaxed">
                    Administrative details for the IRB linked to your site. Updates apply to the
                    ethics committee selected in Site Profile.
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {siteLabel && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-medium text-slate-600 shadow-sm">
                    <MapPin className="h-3.5 w-3.5 text-[#168AAD]" />
                    {siteLabel}
                  </span>
                )}
                {displayOrgName && (
                  <span className="inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-800">
                    {displayOrgName}
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

            {loadingSaved && (
              <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin text-[#168AAD]" />
                Loading saved IRB data…
              </div>
            )}
          </div>
        </div>

        {/* Section overview chips */}
        <div className="flex flex-wrap gap-2">
          {FORM_SECTIONS.map((s) => (
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

        <form onSubmit={handleSubmit(submit, onInvalid)} className="space-y-3">
            <Accordion
              type="multiple"
              value={openSections}
              onValueChange={handleAccordionChange}
              className="space-y-3"
            >
              {FORM_SECTIONS.map((section) => {
                const SectionBody = section.component
                return (
                  <AccordionItem
                    key={section.id}
                    id={`irb-admin-section-${section.id}`}
                    value={section.id}
                    className="rounded-2xl border border-slate-200/90 bg-white shadow-sm overflow-hidden data-[state=open]:shadow-md transition-shadow scroll-mt-24"
                  >
                    <AccordionTrigger className="hover:no-underline px-5 py-4 sm:px-6 sm:py-5 [&[data-state=open]]:bg-gradient-to-r [&[data-state=open]]:from-slate-50/80 [&[data-state=open]]:to-white">
                      <SectionTrigger section={section} />
                    </AccordionTrigger>
                    <AccordionContent className="px-4 sm:px-5 pb-4 pt-1">
                      <fieldset
                        disabled={fieldsDisabled}
                        className="rounded-xl border border-slate-100 bg-slate-50/40 p-3 sm:p-4 disabled:[&_input]:bg-slate-50/90 disabled:[&_textarea]:bg-slate-50/90"
                      >
                        <SectionBody form={form} />
                      </fieldset>
                    </AccordionContent>
                  </AccordionItem>
                )
              })}
            </Accordion>

          {!isDirty && !isEditing && (
            <div className="flex items-start gap-2 rounded-xl border border-sky-100 bg-sky-50/60 px-4 py-3 text-xs text-sky-800">
              <Info className="h-4 w-4 shrink-0 mt-0.5 text-sky-600" />
              <span>
                Click <strong>Edit</strong> to make changes. Validation runs when you leave a field.
              </span>
            </div>
          )}

          {/* Sticky action bar */}
          <div className="sticky bottom-0 z-20 -mx-4 sm:-mx-6 mt-4 px-4 sm:px-6 py-4 rounded-2xl border border-slate-200/80 bg-white/95 backdrop-blur-md shadow-lg">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-slate-500 hidden sm:block">
                {savedIrbId ? `IRB record #${savedIrbId}` : 'No saved IRB record yet'}
                {isDirty && isEditing && (
                  <span className="ml-2 text-amber-600 font-medium">· Unsaved changes</span>
                )}
              </p>
              <div className="flex items-center gap-2 ml-auto">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsEditing(true)}
                  disabled={isEditing || saving || loadingSaved}
                  className="rounded-xl border-slate-200 hover:bg-slate-50 gap-2"
                >
                  <Pencil className="h-4 w-4" />
                  Edit
                </Button>
                <Button
                  type="submit"
                  disabled={isSubmitting || saving || !isEditing}
                  className="rounded-xl gap-2 text-white border-0 shadow-md hover:opacity-95 transition-opacity"
                  style={{ background: 'linear-gradient(135deg, #168AAD 0%, #76C893 100%)' }}
                >
                  {saving ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Saving…
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
        </form>
      </div>
    </div>
  )
}

export default IRBAdministrativeInfo
