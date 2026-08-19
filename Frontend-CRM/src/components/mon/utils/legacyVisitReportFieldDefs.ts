/** Field ids + labels for the built-in legacy visit report (VisitReportLegacyTab). */
import {
  SECTION4_CONSENT_QUESTION_IDS,
  SECTION4_CONSENT_QUESTIONS,
} from "../components/views/visit-detail/visitReportSection4Questions";
import {
  SECTION4_SITE_MANAGEMENT_QUESTION_IDS,
  SECTION4_SITE_MANAGEMENT_QUESTIONS,
} from "../components/views/visit-detail/visitReportSection4SiteManagementQuestions";
import {
  SECTION6_SDV_QUESTION_IDS,
  SECTION6_SDV_QUESTIONS,
} from "../components/views/visit-detail/visitReportSection6SdvQuestions";
import {
  SECTION10_ESSENTIAL_DOCS_QUESTION_IDS,
  SECTION10_ESSENTIAL_DOCS_QUESTIONS,
} from "../components/views/visit-detail/visitReportSection10EssentialDocsQuestions";
import {
  SECTION10_IMP_QUESTION_IDS,
  SECTION10_IMP_QUESTIONS,
} from "../components/views/visit-detail/visitReportSection10ImpQuestions";
import {
  SECTION9_BIOLOGICAL_SAMPLE_QUESTION_IDS,
  SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS,
} from "../components/views/visit-detail/visitReportSection9BiologicalSampleQuestions";
import {
  QUESTION_COMMENT_FIELD_IDS,
  questionCommentKey,
} from "../components/views/visit-detail/visitReportSectionQuestionComments";

const SITE_MGMT_COMMENT_IDS = SECTION4_SITE_MANAGEMENT_QUESTION_IDS.map(questionCommentKey);
const CONSENT_COMMENT_IDS = SECTION4_CONSENT_QUESTION_IDS.map(questionCommentKey);
const SDV_COMMENT_IDS = SECTION6_SDV_QUESTION_IDS.map(questionCommentKey);
const ESSENTIAL_DOCS_COMMENT_IDS = SECTION10_ESSENTIAL_DOCS_QUESTION_IDS.map(questionCommentKey);
const IMP_COMMENT_IDS = SECTION10_IMP_QUESTION_IDS.map(questionCommentKey);
const BIO_SAMPLE_COMMENT_IDS = SECTION9_BIOLOGICAL_SAMPLE_QUESTION_IDS.map(questionCommentKey);

export type MvrFieldMatchDef = {
  id: string;
  label: string;
  type?: "table";
  columns?: { id: string; label: string }[];
  /** Section-level reviewer comments should unlock the fields inside that section. */
  unlockFieldIds?: string[];
};

export const LEGACY_VISIT_REPORT_FIELD_DEFS: MvrFieldMatchDef[] = [
  {
    id: "section1",
    label: "Study and Visit Details",
    unlockFieldIds: [
      "studyTitle",
      "site",
      "visitStartDate",
      "visitEndDate",
      "prevVisitStartDate",
      "prevVisitEndDate",
      "prevVisitNA",
      "nextVisitStartDate",
      "nextVisitEndDate",
      "nextVisitTbd",
      "sitePersonnelRows",
      "monitorPersonnelRows",
      "otherPersonnelRows",
      "visitPurpose",
    ],
  },
  {
    id: "section2",
    label: "Recruitment Participant Status",
    unlockFieldIds: [
      "ptScreened",
      "ptEnrolled",
      "ptActive",
      "ptDropouts",
      "ptCompleted",
      "s2Comments",
    ],
  },
  {
    id: "section3",
    label: "Findings",
    unlockFieldIds: ["q3", "s3Comments"],
  },
  {
    id: "section4",
    label: "Site Management & General Site Assessment",
    unlockFieldIds: [...SECTION4_SITE_MANAGEMENT_QUESTION_IDS, ...SITE_MGMT_COMMENT_IDS],
  },
  {
    id: "section5",
    label: "Participants Informed Consent / Enrolment",
    unlockFieldIds: ["s5NA", ...SECTION4_CONSENT_QUESTION_IDS, ...CONSENT_COMMENT_IDS, "icfRows"],
  },
  {
    id: "section6",
    label: "Case Report Form (CRF) / Source Data Verification (SDV)",
    unlockFieldIds: ["s6NA", ...SECTION6_SDV_QUESTION_IDS, ...SDV_COMMENT_IDS, "sdvRows"],
  },
  {
    id: "section7",
    label: "Essential Documents, ISF or TMF",
    unlockFieldIds: ["s11NA", ...SECTION10_ESSENTIAL_DOCS_QUESTION_IDS, ...ESSENTIAL_DOCS_COMMENT_IDS],
  },
  {
    id: "section8",
    label: "Investigational Medical Product (IMP)",
    unlockFieldIds: ["s8NA", ...SECTION10_IMP_QUESTION_IDS, ...IMP_COMMENT_IDS],
  },
  {
    id: "section9",
    label: "Biological Sample / Laboratory Sample Review",
    unlockFieldIds: ["s9NA", ...SECTION9_BIOLOGICAL_SAMPLE_QUESTION_IDS, ...BIO_SAMPLE_COMMENT_IDS],
  },
  {
    id: "section10",
    label: "Summary of the Visit",
    unlockFieldIds: ["summary"],
  },
  {
    id: "section11",
    label: "Signatures",
    unlockFieldIds: [
      "preparedByName",
      "preparedBySignature",
      "preparedByDate",
      "reviewedByName",
      "reviewedBySignature",
      "reviewedByDate",
    ],
  },
  { id: "studyTitle", label: "Study Title" },
  { id: "sponsor", label: "Sponsor" },
  { id: "studyType", label: "Type of Study" },
  { id: "site", label: "Site (Location)" },
  { id: "site", label: "Site Name" },
  { id: "pi", label: "Principal Investigator (PI)" },
  { id: "visitStartDate", label: "Start Visit Date" },
  { id: "visitEndDate", label: "End Visit Date" },
  { id: "prevVisitStartDate", label: "Start Date of Previous Visit" },
  { id: "prevVisitEndDate", label: "End Date of Previous Visit" },
  { id: "prevVisitNA", label: "N/A" },
  { id: "nextVisitStartDate", label: "Start Date of Next Visit" },
  { id: "nextVisitEndDate", label: "End Date of Next Visit" },
  { id: "nextVisitTbd", label: "TBD" },
  {
    id: "sitePersonnelRows",
    label: "Site Personnel",
    type: "table",
    columns: [
      { id: "name", label: "Name" },
      { id: "role", label: "Role" },
    ],
  },
  {
    id: "monitorPersonnelRows",
    label: "Monitor Personnel",
    type: "table",
    columns: [
      { id: "name", label: "Name" },
      { id: "role", label: "Role" },
    ],
  },
  {
    id: "otherPersonnelRows",
    label: "Other Personnel",
    type: "table",
    columns: [
      { id: "name", label: "Name" },
      { id: "role", label: "Role" },
    ],
  },
  { id: "visitPurpose", label: "Purpose of This Visit" },
  { id: "ptScreened", label: "Participants Screened" },
  { id: "ptEnrolled", label: "Participants Enrolled" },
  { id: "ptActive", label: "Participants Active" },
  { id: "ptDropouts", label: "Participants Drop-outs" },
  { id: "ptCompleted", label: "Participants Completed Study" },
  { id: "q22", label: "Study progress discussed with site staff?" },
  { id: "s2Comments", label: "Comments (Section 2)" },
  { id: "q31", label: "Have there been any changes in the study team since the last visit?" },
  { id: "q32", label: "Were CVs and GCP certificates adequate and filed as required?" },
  { id: "q33", label: "Was the delegation log up-to-date, legible, and complete?" },
  {
    id: "q34",
    label: "Have all study staff been trained on the current protocol / CRF / PIC / IB (training log updated)?",
  },
  { id: "q35", label: "Have all tasks been performed by authorised personnel?" },
  { id: "s3Comments", label: "Comments (Section 3)" },
  ...SECTION4_SITE_MANAGEMENT_QUESTIONS.map((q) => ({ id: q.id, label: q.label })),
  ...SECTION4_CONSENT_QUESTIONS.map((q) => ({ id: q.id, label: q.label })),
  {
    id: "icfRows",
    label: "ICF Review Table",
    type: "table",
    columns: [
      { id: "screeningNo", label: "Subject screening No." },
      { id: "correctIcfVersion", label: "ICF Version Used (Version No. & Date)" },
      { id: "consentBeforeProcedures", label: "Consent Obtained Before Procedures" },
      { id: "subjectSignatureDate", label: "Subject Signature Date" },
      { id: "personObtainingConsent", label: "Consent obtained by" },
      { id: "piSignatureDate", label: "Investigator Signature Date" },
      { id: "comments", label: "Comments" },
    ],
  },
  ...SECTION6_SDV_QUESTIONS.map((q) => ({ id: q.id, label: q.label })),
  {
    id: "sdvRows",
    label: "SDV Review Table",
    type: "table",
    columns: [
      { id: "screeningNo", label: "Subject Screening No." },
      { id: "subjectId", label: "Subject ID" },
      { id: "visitCycle", label: "Visit / Cycle" },
      { id: "comments", label: "Comments" },
    ],
  },
  ...SECTION10_ESSENTIAL_DOCS_QUESTIONS.map((q) => ({ id: q.id, label: q.label })),
  ...SECTION10_IMP_QUESTIONS.map((q) => ({ id: q.id, label: q.label })),
  ...SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS.map((q) => ({ id: q.id, label: q.label })),
  ...QUESTION_COMMENT_FIELD_IDS.map((id) => ({ id, label: `Comment (${id.replace(/Comment$/, "")})` })),
  { id: "summary", label: "Summary of the Visit" },
  { id: "preparedByName", label: "Prepared by — Name of CRA" },
  { id: "preparedBySignature", label: "Prepared by — Signature" },
  { id: "preparedByDate", label: "Prepared by — Date" },
  { id: "reviewedByName", label: "Reviewed & Approved by — Name" },
  { id: "reviewedBySignature", label: "Reviewed & Approved by — Signature" },
  { id: "reviewedByDate", label: "Reviewed & Approved by — Date" },
];
