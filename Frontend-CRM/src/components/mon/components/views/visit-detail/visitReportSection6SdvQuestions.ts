/** Section 6 — Case Report Form (CRF) / Source Data Verification (SDV) checklist items. */
export const SECTION6_SDV_QUESTIONS = [
  {
    id: "q61",
    label:
      "Was Source Data Verification (SDV) performed in accordance with the Monitoring Plan and monitoring strategy?",
  },
  {
    id: "q62",
    label:
      "Was the source documentation reviewed complete, accurate, attributable, legible, contemporaneous, original (or certified copy), and sufficient to support the data entered in the eCRF/CRF?",
  },
  {
    id: "q63",
    label: "Were eCRF/CRF entries current and consistent with the source documentation reviewed?",
  },
  {
    id: "q64",
    label:
      "Are site personnel compliant with timely completion and maintenance of study data within the eCRF/EDC system?",
  },
  {
    id: "q65",
    label:
      "Have data queries been reviewed and resolved within required timelines, or are adequate actions in place for outstanding queries?",
  },
  {
    id: "q66",
    label:
      "Have Serious Adverse Events (SAEs) been reported and documented in accordance with the protocol and Safety Management Plan?",
  },
  {
    id: "q67",
    label:
      "Are there any outstanding SAE follow-up actions, missing safety information, or unresolved safety queries?",
  },
  {
    id: "q68",
    label:
      "Were any data integrity, source documentation, safety reporting, or eCRF compliance issues identified during this review?",
  },
] as const;

export type Section6SdvQuestionId = (typeof SECTION6_SDV_QUESTIONS)[number]["id"];

export const SECTION6_SDV_QUESTION_IDS: Section6SdvQuestionId[] =
  SECTION6_SDV_QUESTIONS.map((q) => q.id);
