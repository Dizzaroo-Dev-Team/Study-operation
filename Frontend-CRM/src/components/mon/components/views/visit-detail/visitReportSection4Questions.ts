/** Section 4 — Participants Informed Consent / Enrolment checklist items. */
export const SECTION4_CONSENT_QUESTIONS = [
  {
    id: "q51",
    label:
      "Were all participants reviewed during this visit consented using the current IRB/EC-approved ICF version?",
  },
  {
    id: "q52",
    label:
      "Was informed consent obtained prior to the performance of any study-specific procedures?",
  },
  {
    id: "q53",
    label: "Were all required signatures and dates completed correctly on the ICFs reviewed?",
  },
  {
    id: "q54",
    label:
      "Was the individual obtaining informed consent authorized and documented on the Delegation of Authority Log?",
  },
  {
    id: "q55",
    label:
      "Was the informed consent process adequately documented in the participant's source records?",
  },
  {
    id: "q56",
    label: "Were participants provided a copy of the signed informed consent form?",
  },
  {
    id: "q57",
    label: "Were revised consent forms obtained and documented where required?",
  },
  {
    id: "q58",
    label:
      "Were any informed consent findings, deficiencies, or deviations identified during this review?",
  },
  {
    id: "q59",
    label: "Is the Screening and Enrollment Log current, complete, and accurate?",
  },
  {
    id: "q510",
    label:
      "Did all enrolled/randomized participants reviewed meet protocol eligibility criteria?",
  },
  {
    id: "q511",
    label:
      "Was randomization/intervention assignment performed according to protocol requirements and documented appropriately?",
  },
] as const;

export type Section4ConsentQuestionId = (typeof SECTION4_CONSENT_QUESTIONS)[number]["id"];

export const SECTION4_CONSENT_QUESTION_IDS: Section4ConsentQuestionId[] =
  SECTION4_CONSENT_QUESTIONS.map((q) => q.id);
