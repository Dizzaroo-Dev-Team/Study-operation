/** Section 10 — Investigational Medical Product (IMP) checklist items. */
export const SECTION10_IMP_QUESTIONS = [
  {
    id: "q81",
    label:
      "Was IMP stored, handled, and controlled in accordance with the protocol, pharmacy manual, and applicable regulatory requirements?",
  },
  {
    id: "q82",
    label:
      "Were required temperature monitoring records, storage conditions, and excursion management documentation reviewed and found acceptable?",
  },
  {
    id: "q83",
    label:
      "Was IMP accountability (receipt, dispensing, return, reconciliation, and inventory) complete, accurate, and up to date?",
  },
  {
    id: "q84",
    label:
      "Was IMP dispensed only to eligible and appropriately randomized/enrolled participants in accordance with protocol requirements?",
  },
  {
    id: "q85",
    label:
      "Were participant compliance & instructions regarding IMP administration, storage, compliance, and return appropriately documented?",
  },
  {
    id: "q86",
    label:
      "Was the study blind remained intact and maintained according to protocol requirements?",
  },
] as const;

export type Section10ImpQuestionId = (typeof SECTION10_IMP_QUESTIONS)[number]["id"];

export const SECTION10_IMP_QUESTION_IDS: Section10ImpQuestionId[] =
  SECTION10_IMP_QUESTIONS.map((q) => q.id);
