// ISO-3 country code → ISO-4217 currency code.
// Matches the 8 countries seeded in seed_data.py COUNTRY_FACTORS and the FX rates
// seeded in currency_exchange_rate.
export const COUNTRY_TO_CURRENCY: Record<string, string> = {
  USA: 'USD',
  GBR: 'GBP',
  DEU: 'EUR',
  JPN: 'JPY',
  IND: 'INR',
  BRA: 'BRL',
  AUS: 'AUD',
  POL: 'PLN',
}

export function currencyForCountry(countryCode: string | null | undefined): string {
  if (!countryCode) return 'USD'
  return COUNTRY_TO_CURRENCY[countryCode.toUpperCase()] ?? 'USD'
}
