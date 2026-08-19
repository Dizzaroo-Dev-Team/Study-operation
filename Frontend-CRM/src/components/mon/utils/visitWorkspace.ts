import type { Visit } from "../types";

type StudyRow = { id: string; study_id: string };
type SiteRow = { id: string; site_id: string; name?: string };

/** True when the visit belongs to the globally selected study/site (ID-only, fail closed). */
export function visitMatchesWorkspace(
  visit: Visit,
  selectedStudyId: string | null,
  selectedSiteId: string | null,
  filteredSites: SiteRow[],
  studies: StudyRow[],
): boolean {
  const visitStudyId = visit.studyId?.trim();
  const visitSiteId = visit.siteId?.trim();
  if (!selectedStudyId || !selectedSiteId || !visitStudyId || !visitSiteId) {
    return false;
  }

  const study = studies.find((s) => s.id === selectedStudyId);
  const studyMatches =
    visitStudyId === selectedStudyId ||
    visitStudyId === study?.id ||
    visitStudyId === study?.study_id;
  if (!studyMatches) return false;

  const site = filteredSites.find(
    (s) => s.id === selectedSiteId || s.site_id === selectedSiteId,
  );
  const siteMatches =
    visitSiteId === selectedSiteId ||
    visitSiteId === site?.site_id ||
    visitSiteId === site?.id;
  return siteMatches;
}
