export function fmtCurrency(value: string | number | null | undefined, currency: string): string {
  const n = Number(typeof value === 'string' ? value : (value ?? 0))
  const fixed = Number.isFinite(n) ? n.toFixed(2) : '0.00'
  return currency === 'USD'
    ? `$${Number(fixed).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
    : `${currency} ${fixed}`
}
