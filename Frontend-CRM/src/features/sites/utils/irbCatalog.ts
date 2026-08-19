/** IRB catalog: no client-side exclusions. */

export function normalizeIrbListName(name: string | null | undefined): string {
  return String(name ?? '')
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .join(' ')
}

/** Hide from dropdowns; treat mappings to these as invalid. */
export function isIrbExcludedFromCatalog(
  _name: string | null | undefined,
  _uniqueCode?: string | null | undefined
): boolean {
  return false
}
