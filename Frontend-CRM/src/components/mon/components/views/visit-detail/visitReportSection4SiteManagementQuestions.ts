/** Section 4 — Site Management & General Site Assessment checklist items. */
export const SECTION4_SITE_MANAGEMENT_QUESTIONS = [
  {
    id: "q401",
    label:
      "Was the monitoring visit conducted in accordance with the approved Monitoring Plan and study requirements?",
  },
  {
    id: "q402",
    label:
      "Were appropriate interactions conducted with the Principal Investigator and/or delegated site personnel during this visit?",
  },
  {
    id: "q403",
    label:
      "Does the Principal Investigator provide adequate oversight and supervision of study conduct at the site?",
  },
  {
    id: "q404",
    label: "Have there been any changes to site personnel since the previous monitoring visit?",
  },
  {
    id: "q405",
    label:
      "If site personnel changes occurred, were required training and study documentation completed and maintained?",
    showWhen: { field: "q404", value: "Yes" },
  },
  {
    id: "q406",
    label:
      "Have there been any changes to site facilities, equipment, or study-related resources since the previous visit?",
  },
  {
    id: "q407",
    label:
      "If site facility or equipment changes occurred, were required assessments, approvals, and documentation completed?",
    showWhen: { field: "q406", value: "Yes" },
  },
  {
    id: "q408",
    label: "Are site personnel following protocol requirements, GCP, and study procedures?",
  },
  {
    id: "q409",
    label: "Is participant recruitment/enrollment progressing according to study expectations?",
  },
  {
    id: "q410",
    label:
      "Are there any risks or concerns that may impact subject safety, data integrity, study conduct, or recruitment at the site?",
  },
] as const;

export type Section4SiteManagementQuestionId =
  (typeof SECTION4_SITE_MANAGEMENT_QUESTIONS)[number]["id"];

export type Section4SiteManagementQuestion =
  (typeof SECTION4_SITE_MANAGEMENT_QUESTIONS)[number];

export const SECTION4_SITE_MANAGEMENT_QUESTION_IDS: Section4SiteManagementQuestionId[] =
  SECTION4_SITE_MANAGEMENT_QUESTIONS.map((q) => q.id);

type Section4SiteManagementValues = Record<Section4SiteManagementQuestionId, string>;

export function isSection4SiteManagementQuestionVisible(
  question: Section4SiteManagementQuestion,
  values: Section4SiteManagementValues,
): boolean {
  if (!("showWhen" in question) || !question.showWhen) return true;
  return values[question.showWhen.field] === question.showWhen.value;
}
