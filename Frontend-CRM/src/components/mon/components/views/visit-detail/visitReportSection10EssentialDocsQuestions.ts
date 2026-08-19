/** Section 10 — Essential Documents, ISF or TMF checklist items. */
export const SECTION10_ESSENTIAL_DOCS_QUESTIONS = [
  {
    id: "q111",
    label: "Was the eISF/ISF reviewed during this monitoring visit?",
  },
  {
    id: "q112",
    label:
      "Are current approved versions of the protocol, protocol amendments, informed consent forms, and Investigator Brochure available and appropriately documented?",
  },
  {
    id: "q113",
    label:
      "Are required Ethics Committee/IRB and Regulatory Authority approvals, acknowledgements, and continuing review documentation current and filed appropriately?",
  },
  {
    id: "q114",
    label:
      "Is the Delegation of Authority/Signature Log current, accurate, and reflective of study personnel responsibilities?",
  },
  {
    id: "q115",
    label:
      "Are investigator and site staff qualification documents (e.g., CVs, licenses, GCP training records) current and maintained as required?",
  },
  {
    id: "q116",
    label:
      "Are safety communications (e.g., SUSARs, Investigator Notifications, Safety Letters) and associated site acknowledgements/submissions appropriately maintained?",
  },
  {
    id: "q117",
    label:
      "Is participant identification documentation (e.g., Subject Identification Log, Enrollment Log, Screening Log, where applicable) current, complete, and maintained securely?",
  },
  {
    id: "q118",
    label: "Is study-related correspondence appropriately maintained and filed within the eISF/ISF?",
  },
  {
    id: "q119",
    label:
      "Are laboratory and other vendor-related essential documents (e.g., certifications, reference ranges, accreditations, normal ranges, equipment documentation where applicable) current and appropriately filed?",
  },
] as const;

export type Section10EssentialDocsQuestionId =
  (typeof SECTION10_ESSENTIAL_DOCS_QUESTIONS)[number]["id"];

export const SECTION10_ESSENTIAL_DOCS_QUESTION_IDS: Section10EssentialDocsQuestionId[] =
  SECTION10_ESSENTIAL_DOCS_QUESTIONS.map((q) => q.id);
