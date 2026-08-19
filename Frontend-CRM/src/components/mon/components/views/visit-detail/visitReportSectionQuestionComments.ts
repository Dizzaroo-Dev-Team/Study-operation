import { SECTION4_CONSENT_QUESTION_IDS } from "./visitReportSection4Questions";
import {
  SECTION4_SITE_MANAGEMENT_QUESTION_IDS,
} from "./visitReportSection4SiteManagementQuestions";
import { SECTION6_SDV_QUESTION_IDS } from "./visitReportSection6SdvQuestions";
import { SECTION9_BIOLOGICAL_SAMPLE_QUESTION_IDS } from "./visitReportSection9BiologicalSampleQuestions";
import { SECTION10_ESSENTIAL_DOCS_QUESTION_IDS } from "./visitReportSection10EssentialDocsQuestions";
import { SECTION10_IMP_QUESTION_IDS } from "./visitReportSection10ImpQuestions";

/** Question ids in sections 4–9 that support an inline comment field. */
export const SECTIONS_4_TO_9_QUESTION_IDS = [
  ...SECTION4_SITE_MANAGEMENT_QUESTION_IDS,
  ...SECTION4_CONSENT_QUESTION_IDS,
  ...SECTION6_SDV_QUESTION_IDS,
  ...SECTION10_ESSENTIAL_DOCS_QUESTION_IDS,
  ...SECTION10_IMP_QUESTION_IDS,
  ...SECTION9_BIOLOGICAL_SAMPLE_QUESTION_IDS,
] as const;

export type Sections4To9QuestionId = (typeof SECTIONS_4_TO_9_QUESTION_IDS)[number];

export function questionCommentKey(questionId: string): string {
  return `${questionId}Comment`;
}

export const QUESTION_COMMENT_FIELD_IDS = SECTIONS_4_TO_9_QUESTION_IDS.map((id) =>
  questionCommentKey(id),
);

export function createEmptyQuestionComments(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const id of SECTIONS_4_TO_9_QUESTION_IDS) {
    out[questionCommentKey(id)] = "";
  }
  return out;
}

export function mergeQuestionComments(raw: unknown): Record<string, string> {
  const base = createEmptyQuestionComments();
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return base;
  for (const key of QUESTION_COMMENT_FIELD_IDS) {
    const val = (raw as Record<string, unknown>)[key];
    if (typeof val === "string") base[key] = val;
  }
  return base;
}
