/** Section 9 — Biological Sample / Laboratory Sample Review checklist items. */
export const SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS = [
  {
    id: "q91",
    label:
      "Were protocol-required PK/PD, biomarker, central laboratory, genetic/genomic, and other study-specific samples collected in accordance with protocol and laboratory manual requirements?",
  },
  {
    id: "q92",
    label:
      "Were protocol-required samples processed, stored, and shipped within required timelines and conditions?",
  },
] as const;

export type Section9BiologicalSampleQuestionId =
  (typeof SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS)[number]["id"];

export const SECTION9_BIOLOGICAL_SAMPLE_QUESTION_IDS: Section9BiologicalSampleQuestionId[] =
  SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS.map((q) => q.id);
