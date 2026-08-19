/** Default when none selected (US/Canada). */
export const DEFAULT_PHONE_COUNTRY = '+1'

/**
 * Common dialing codes. `value` is the ITU prefix; `label` shows code + full country/region name in the dropdown.
 */
export const PHONE_COUNTRY_OPTIONS = [
  { value: '+1', label: '+1 — United States & Canada' },
  { value: '+20', label: '+20 — Egypt' },
  { value: '+27', label: '+27 — South Africa' },
  { value: '+31', label: '+31 — Netherlands' },
  { value: '+32', label: '+32 — Belgium' },
  { value: '+33', label: '+33 — France' },
  { value: '+34', label: '+34 — Spain' },
  { value: '+39', label: '+39 — Italy' },
  { value: '+41', label: '+41 — Switzerland' },
  { value: '+43', label: '+43 — Austria' },
  { value: '+44', label: '+44 — United Kingdom' },
  { value: '+45', label: '+45 — Denmark' },
  { value: '+46', label: '+46 — Sweden' },
  { value: '+47', label: '+47 — Norway' },
  { value: '+48', label: '+48 — Poland' },
  { value: '+49', label: '+49 — Germany' },
  { value: '+52', label: '+52 — Mexico' },
  { value: '+54', label: '+54 — Argentina' },
  { value: '+55', label: '+55 — Brazil' },
  { value: '+60', label: '+60 — Malaysia' },
  { value: '+61', label: '+61 — Australia' },
  { value: '+63', label: '+63 — Philippines' },
  { value: '+64', label: '+64 — New Zealand' },
  { value: '+65', label: '+65 — Singapore' },
  { value: '+66', label: '+66 — Thailand' },
  { value: '+81', label: '+81 — Japan' },
  { value: '+82', label: '+82 — South Korea' },
  { value: '+84', label: '+84 — Vietnam' },
  { value: '+86', label: '+86 — China' },
  { value: '+91', label: '+91 — India' },
  { value: '+234', label: '+234 — Nigeria' },
  { value: '+254', label: '+254 — Kenya' },
  { value: '+351', label: '+351 — Portugal' },
  { value: '+353', label: '+353 — Ireland' },
  { value: '+852', label: '+852 — Hong Kong' },
  { value: '+966', label: '+966 — Saudi Arabia' },
  { value: '+971', label: '+971 — United Arab Emirates' },
].sort((a, b) => a.label.localeCompare(b.label))

const _sortedCodes = () =>
  [...PHONE_COUNTRY_OPTIONS.map((o) => o.value)].sort((a, b) => b.length - a.length)

/**
 * Combine country code and national digits into one stored string (E.164-style, no spaces).
 */
export function combineInternationalPhone(countryCode, nationalDigits) {
  const rawCc = String(countryCode || '').trim() || DEFAULT_PHONE_COUNTRY
  const cc = rawCc.startsWith('+') ? rawCc : `+${rawCc.replace(/^\+/, '')}`
  const nat = String(nationalDigits || '').replace(/\D/g, '')
  if (!nat) return null
  return `${cc}${nat}`
}

/**
 * Parse a stored phone value from the API into country code + national digits for the form.
 */
export function splitStoredPhone(stored) {
  const s = String(stored || '').trim()
  if (!s) {
    return { countryCode: DEFAULT_PHONE_COUNTRY, national: '' }
  }
  if (s.startsWith('+')) {
    for (const code of _sortedCodes()) {
      if (s.startsWith(code)) {
        return {
          countryCode: code,
          national: s.slice(code.length).replace(/\D/g, ''),
        }
      }
    }
    if (s.startsWith('+1') && s.length > 2) {
      return { countryCode: '+1', national: s.slice(2).replace(/\D/g, '') }
    }
    const digits = s.replace(/\D/g, '')
    return { countryCode: DEFAULT_PHONE_COUNTRY, national: digits }
  }
  const digits = s.replace(/\D/g, '')
  return { countryCode: DEFAULT_PHONE_COUNTRY, national: digits }
}
