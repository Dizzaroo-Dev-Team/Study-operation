/** Canonical monitoring finding categories (dropdown + filters). */
export const FINDING_CATEGORIES = [
  "ICF/Consent Issue",
  "Inclusion/Exclusion",
  "Protocol Deviation",
  "Patient Retention, Completion & Withdrawal",
  "Procedural/Visit Windows",
  "Source Documentation and Data Quality",
  "Safety Reporting",
  "Investigational Product (IP)",
  "Regulatory Essential Documents (ISF)",
  "Site Staffing, Training and Delegation",
  "Other",
] as const;

const LEGACY_TO_CANONICAL: Record<string, string> = {
  Consent: "ICF/Consent Issue",
  Regulatory: "Regulatory/Compliance",
};

/** Map stored legacy labels to current category names for UI and selects. */
export function canonicalFindingCategory(raw: string): string {
  const t = (raw || "").trim();
  return LEGACY_TO_CANONICAL[t] ?? t;
}

export function categoryMatchesFilter(findingCategory: string, filter: string): boolean {
  if (filter === "All Categories") return true;
  return canonicalFindingCategory(findingCategory) === filter;
}
