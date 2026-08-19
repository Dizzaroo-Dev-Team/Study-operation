export const organizationTypes = [
  { value: 'IRB', label: 'IRB' },
  { value: 'IEC', label: 'IEC' },
]

export const fullBoardMeetingFrequencies = [
  { value: 'Weekly', label: 'Weekly' },
  { value: 'Bi-weekly', label: 'Bi-weekly' },
  { value: 'Monthly', label: 'Monthly' },
  { value: 'Quarterly', label: 'Quarterly' },
  { value: 'As needed', label: 'As needed' },
]

export const submissionTypes = [
  { value: 'Initial', label: 'Initial' },
  { value: 'Amendment', label: 'Amendment' },
]

export const submissionMethods = [
  { value: 'Online – Portal', label: 'Online – Portal' },
  { value: 'Email', label: 'Email' },
  { value: 'Hard Copy (Paper)', label: 'Hard Copy (Paper)' },
  { value: 'Regulatory System', label: 'Regulatory System' },
]

export const submissionFeeCurrencies = [
  { value: 'USD', label: 'USD — US Dollar' },
  { value: 'EUR', label: 'EUR — Euro' },
  { value: 'GBP', label: 'GBP — British Pound' },
  { value: 'INR', label: 'INR — Indian Rupee' },
  { value: 'JPY', label: 'JPY — Japanese Yen' },
  { value: 'AUD', label: 'AUD — Australian Dollar' },
  { value: 'CAD', label: 'CAD — Canadian Dollar' },
  { value: 'CNY', label: 'CNY — Chinese Yuan' },
  { value: 'SGD', label: 'SGD — Singapore Dollar' },
  { value: 'KRW', label: 'KRW — South Korean Won' },
  { value: 'BRL', label: 'BRL — Brazilian Real' },
  { value: 'MXN', label: 'MXN — Mexican Peso' },
  { value: 'AED', label: 'AED — UAE Dirham' },
]

/** Banking section — must stay in sync with backend BANKING_CURRENCIES_ALLOWED */
export const bankingCurrencies = [
  { value: 'USD', label: 'USD — US Dollar' },
  { value: 'INR', label: 'INR — Indian Rupee' },
  { value: 'EUR', label: 'EUR — Euro' },
  { value: 'GBP', label: 'GBP — British Pound' },
  { value: 'CAD', label: 'CAD — Canadian Dollar' },
  { value: 'AUD', label: 'AUD — Australian Dollar' },
  { value: 'JPY', label: 'JPY — Japanese Yen' },
  { value: 'CHF', label: 'CHF — Swiss Franc' },
  { value: 'SGD', label: 'SGD — Singapore Dollar' },
  { value: 'AED', label: 'AED — UAE Dirham' },
]

export const paymentMethods = [
  { value: 'Credit/Debit Card', label: 'Credit/Debit Card' },
  { value: 'Bank/Wire Transfer', label: 'Bank/Wire Transfer' },
  // Value kept for API / existing rows; label is the user-facing name.
  { value: 'Online Payment Catalog', label: 'Online Payment Gateway' },
]

/** Value must match `submissionMethods` hard-copy option for conditional UI. */
export const SUBMISSION_METHOD_HARD_COPY = 'Hard Copy (Paper)'

export const irbTypes = [
  { value: 'Central', label: 'Central' },
  { value: 'Institutional', label: 'Institutional' },
  { value: 'Independent', label: 'Independent' },
]

/** Maps legacy IRB Type values saved before the rename / removal. */
export const normalizeIrbTypeForDisplay = (raw) => {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  const legacy = {
    'Local / Institutional': 'Institutional',
    'Commercial / Independent': 'Independent',
    'Government / Regulatory': 'Institutional',
  }
  return legacy[s] || s
}

export const iecTypes = [
  { value: 'Institutional', label: 'Institutional' },
  { value: 'Independent', label: 'Independent' },
]

/** Maps legacy IEC Type values saved before the rename. */
export const normalizeIecTypeForDisplay = (raw) => {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  const legacy = {
    'Local / Institutional': 'Institutional',
    'Commercial / Independent': 'Independent',
  }
  return legacy[s] || s
}

export const irbStatuses = [
  { value: 'Active', label: 'Active' },
  { value: 'Inactive', label: 'Inactive' },
  { value: 'Suspended', label: 'Suspended' },
  { value: 'Under Review', label: 'Under Review' },
]

export const accreditationBodies = [
  { value: 'None/N/A', label: 'None / N/A' },
  { value: 'NHMRC', label: 'NHMRC' },
  { value: 'SIDCER-FERCAP', label: 'SIDCER-FERCAP' },
  { value: 'MHLW', label: 'MHLW' },
  { value: 'AAHRPP(US)', label: 'AAHRPP (US)' },
  { value: 'NABH(India)', label: 'NABH (India)' },
]

export const countries = [
  'Australia',
  'Brazil',
  'Canada',
  'China',
  'Europe',
  'France',
  'Germany',
  'India',
  'Italy',
  'Japan',
  'Mexico',
  'Singapore',
  'South Korea',
  'Spain',
  'United Arab Emirates',
  'United Kingdom',
  'United States',
].map((c) => ({ value: c, label: c }))

export const timeZones = [
  'UTC',
  // United States
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  // Canada
  'America/Toronto',
  'America/Vancouver',
  // Mexico
  'America/Mexico_City',
  // Brazil
  'America/Sao_Paulo',
  // United Kingdom
  'Europe/London',
  // France
  'Europe/Paris',
  // Germany
  'Europe/Berlin',
  // Italy
  'Europe/Rome',
  // Spain
  'Europe/Madrid',
  // United Arab Emirates
  'Asia/Dubai',
  // India
  'Asia/Kolkata',
  // China
  'Asia/Shanghai',
  // Singapore
  'Asia/Singapore',
  // South Korea
  'Asia/Seoul',
  // Japan
  'Asia/Tokyo',
  // Australia
  'Australia/Sydney',
  'Australia/Perth',
].map((z) => ({ value: z, label: z }))

export const twoDigitNumberPattern = /^[0-9]{1,2}$/

