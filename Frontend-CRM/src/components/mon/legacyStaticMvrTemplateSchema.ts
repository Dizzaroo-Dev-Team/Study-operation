/**
 * MVR builder schema mirroring the structured sections and prompts from the built-in
 * legacy static visit report (`VisitReportLegacyTab` in VisitReportTab.tsx).
 */
import type { MvrFieldDef, MvrTemplateDto, MvrTemplateSchema } from "./types/mvrTemplate";
import { SECTION4_CONSENT_QUESTIONS } from "./components/views/visit-detail/visitReportSection4Questions";
import { SECTION4_SITE_MANAGEMENT_QUESTIONS } from "./components/views/visit-detail/visitReportSection4SiteManagementQuestions";
import { SECTION6_SDV_QUESTIONS } from "./components/views/visit-detail/visitReportSection6SdvQuestions";
import { SECTION10_ESSENTIAL_DOCS_QUESTIONS } from "./components/views/visit-detail/visitReportSection10EssentialDocsQuestions";
import { SECTION10_IMP_QUESTIONS } from "./components/views/visit-detail/visitReportSection10ImpQuestions";
import { SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS } from "./components/views/visit-detail/visitReportSection9BiologicalSampleQuestions";

const YN_OPTS = ["Yes", "No", "N/A"] as const;

function yn(id: string, label: string): MvrFieldDef {
  return { id, type: "radio", label, options: [...YN_OPTS], required: false };
}

function txt(id: string, label: string, placeholder = ""): MvrFieldDef {
  return { id, type: "text", label, placeholder, required: false };
}

function area(id: string, label: string, placeholder = ""): MvrFieldDef {
  return { id, type: "textarea", label, placeholder, required: false };
}

function dt(id: string, label: string): MvrFieldDef {
  return { id, type: "date", label, required: false };
}

function sec(id: string, title: string, content: string): MvrFieldDef {
  return { id, type: "section", label: title, content };
}

function tbl(id: string, label: string, columns: { id: string; label: string }[]): MvrFieldDef {
  return { id, type: "table", label, columns, required: false };
}

/** Default name suggested when creating a draft from this layout. */
export const LEGACY_STATIC_MVR_TEMPLATE_DEFAULT_NAME = "Standard MVR (built-in layout)";
export const LEGACY_STATIC_MVR_TEMPLATE_LAYOUT = "legacy-static-standard";

const LEGACY_STATIC_REQUIRED_FIELD_IDS = [
  "legacy_s1",
  "legacy_s1_study_title",
  "legacy_s1_visit_start_date",
  "legacy_s1_visit_end_date",
  "legacy_s13_summary",
  "legacy_s14_monitor",
];

export function isLegacyStaticMvrTemplateSchema(schema: MvrTemplateSchema | undefined | null): boolean {
  const fields = Array.isArray(schema?.fields) ? schema.fields : [];
  if (schema?.layout === LEGACY_STATIC_MVR_TEMPLATE_LAYOUT) return true;
  if (fields.length < 20) return false;
  const ids = new Set(fields.map((f) => f.id));
  return LEGACY_STATIC_REQUIRED_FIELD_IDS.every((id) => ids.has(id));
}

/** Custom templates use the dynamic visit report shell; legacy-static extends the built-in form. */
export function shouldUseDynamicMvrShell(template: MvrTemplateDto | null | undefined): boolean {
  const fields = template?.schema?.fields;
  if (!Array.isArray(fields) || fields.length === 0) return false;
  return !isLegacyStaticMvrTemplateSchema(template?.schema);
}

export function getLegacyStaticMvrTemplateSchema(): MvrTemplateSchema {
  const fields: MvrFieldDef[] = [
    sec("legacy_s1", "1. Study and Visit Details", ""),
    txt("legacy_s1_study_title", "Study Title"),
    txt("legacy_s1_sponsor", "Sponsor"),
    txt("legacy_s1_study_type", "Type of Study", "e.g. Interventional"),
    txt("legacy_s1_site", "Site (Location)"),
    txt("legacy_s1_pi", "Principal Investigator (PI)"),
    dt("legacy_s1_visit_start_date", "Start Visit Date"),
    dt("legacy_s1_visit_end_date", "End Visit Date"),
    dt("legacy_s1_prev_visit_date", "Date(s) of Previous Visit"),
    txt(
      "legacy_s1_prev_visit_note",
      "Previous visit — notes",
      "In the legacy form this field paired with an N/A checkbox; use this line if not applicable.",
    ),
    dt("legacy_s1_next_visit_date", "Planned Date(s) of Next Visit"),
    txt("legacy_s1_next_visit_note", "Next visit — notes", 'Use "TBD" here when dates are not yet scheduled.'),
    tbl("legacy_s1_staff", "Study Staff Present", [
      { id: "name", label: "Name" },
      { id: "function", label: "Function" },
      { id: "contact", label: "Contact Information" },
    ]),
    area(
      "legacy_s1_visit_purpose",
      "Main Purpose of This Visit",
      "Describe monitoring activities performed (e.g. SDV, review of informed consent process, ISF, resolution of queries, safety, drug accountability)…",
    ),

    sec("legacy_s2", "2. Participant Status", ""),
    txt("legacy_s2_pt_screened", "Participants Screened"),
    txt("legacy_s2_pt_enrolled", "Participants Enrolled"),
    txt("legacy_s2_pt_active", "Participants Active"),
    txt("legacy_s2_pt_dropouts", "Participants Drop-outs"),
    txt("legacy_s2_pt_completed", "Participants Completed Study"),
    yn("legacy_s2_q22", "2.1 Study progress discussed with site staff?"),
    area("legacy_s2_comments", "Comments (Section 2)", "E.g. measures to enhance recruitment or limit drop-out…"),

    sec("legacy_s3", "3. Site Team", ""),
    yn("legacy_s3_q31", "3.1 Have there been any changes in the study team since the last visit?"),
    yn("legacy_s3_q32", "3.2 Were CVs and GCP certificates adequate and filed as required?"),
    yn("legacy_s3_q33", "3.3 Was the delegation log up-to-date, legible, and complete?"),
    yn(
      "legacy_s3_q34",
      "3.4 Have all study staff been trained on the current protocol / CRF / PIC / IB (training log updated)?",
    ),
    yn("legacy_s3_q35", "3.5 Have all tasks been performed by authorised personnel?"),
    area("legacy_s3_comments", "Comments (Section 3)", ""),

    sec(
      "legacy_s_reg",
      "Regulatory documents & approvals",
      "Mirrors legacy payload fields (q41–q44, document register) that still sync with saved reports even when not shown on the old static screen.",
    ),
    yn("legacy_s_reg_q41ec", "R.1 Protocol / CIP — EC approval adequate and filed?"),
    yn("legacy_s_reg_q41ra", "R.2 Protocol / CIP — RA approval adequate and filed?"),
    yn("legacy_s_reg_q42ec", "R.3 PIC / IB — EC approval adequate and filed?"),
    yn("legacy_s_reg_q42ra", "R.4 PIC / IB — RA approval adequate and filed?"),
    yn("legacy_s_reg_q43", "R.5 Are regulatory binders / registers complete and current (as applicable)?"),
    yn("legacy_s_reg_q44", "R.6 Any findings related to essential documents?"),
    area("legacy_s_reg_comments", "Comments (regulatory documents)", ""),
    tbl("legacy_s_reg_doc_table", "Essential documents tracking table", [
      { id: "type", label: "Document type" },
      { id: "version", label: "Version" },
      { id: "ecDate", label: "EC date" },
      { id: "raDate", label: "RA date" },
    ]),

    sec("legacy_s_site", "4. Site Management & General Site Assessment", ""),
    ...SECTION4_SITE_MANAGEMENT_QUESTIONS.map((q, i) =>
      yn(`legacy_s_site_${q.id}`, `4.${i + 1} ${q.label}`),
    ),

    sec("legacy_s4", "5. Participants Informed Consent / Enrolment", ""),
    ...SECTION4_CONSENT_QUESTIONS.map((q, i) =>
      yn(`legacy_s4_${q.id}`, `5.${i + 1} ${q.label}`),
    ),
    tbl("legacy_s4_icf", "ICF Review Table", [
      { id: "screeningNo", label: "Subject screening No." },
      { id: "correctIcfVersion", label: "ICF Version Used (Version No. & Date)" },
      { id: "consentBeforeProcedures", label: "Consent Obtained Before Procedures" },
      { id: "subjectSignatureDate", label: "Subject Signature Date" },
      { id: "personObtainingConsent", label: "Consent obtained by" },
      { id: "piSignatureDate", label: "Investigator Signature Date" },
      { id: "comments", label: "Comments" },
    ]),

    sec("legacy_s5", "6. Case Report Form (CRF) / Source Data Verification (SDV)", ""),
    ...SECTION6_SDV_QUESTIONS.map((q, i) =>
      yn(`legacy_s5_${q.id}`, `6.${i + 1} ${q.label}`),
    ),
    tbl("legacy_s5_sdv", "SDV Review Table", [
      { id: "screeningNo", label: "Subject Screening No." },
      { id: "subjectId", label: "Subject ID" },
      { id: "visitCycle", label: "Visit / Cycle" },
      { id: "comments", label: "Comments" },
    ]),

    sec("legacy_s10", "7. Essential Documents, ISF or TMF", ""),
    ...SECTION10_ESSENTIAL_DOCS_QUESTIONS.map((q, i) =>
      yn(`legacy_s10_${q.id}`, `7.${i + 1} ${q.label}`),
    ),

    sec(
      "legacy_s7",
      "8. Investigational Medical Product (IMP)",
      "Legacy form supports marking this section N/A; note applicability here if needed.",
    ),
    ...SECTION10_IMP_QUESTIONS.map((q, i) =>
      yn(`legacy_s7_${q.id}`, `8.${i + 1} ${q.label}`),
    ),

    sec(
      "legacy_s8",
      "9. Biological Sample / Laboratory Sample Review",
      "Legacy form supports marking this section N/A; note applicability here if needed.",
    ),
    ...SECTION9_BIOLOGICAL_SAMPLE_QUESTIONS.map((q, i) =>
      yn(`legacy_s8_${q.id}`, `9.${i + 1} ${q.label}`),
    ),

    sec("legacy_s13", "10. Summary of the Visit", ""),
    area(
      "legacy_s13_summary",
      "Summary",
      "Conclusions of the monitoring visit and general comments…",
    ),

    sec("legacy_s14", "11. Signatures", ""),
    txt("legacy_s14_prepared_name", "Prepared by — Name of CRA", "Full name"),
    txt("legacy_s14_prepared_sig", "Prepared by — Signature", "Signature"),
    dt("legacy_s14_prepared_date", "Prepared by — Date"),
    txt("legacy_s14_reviewed_name", "Reviewed & Approved by — Name", "Full name"),
    txt("legacy_s14_reviewed_sig", "Reviewed & Approved by — Signature", "Signature"),
    dt("legacy_s14_reviewed_date", "Reviewed & Approved by — Date"),
  ];

  return { layout: LEGACY_STATIC_MVR_TEMPLATE_LAYOUT, fields };
}

/** Field ids from the built-in legacy static schema (excludes org-inserted custom fields). */
export const LEGACY_STATIC_MVR_FIELD_IDS = new Set(
  getLegacyStaticMvrTemplateSchema().fields.map((f) => f.id),
);

/** Custom fields inserted into a legacy-static template (shown inline on the CRA form). */
export function legacyInsertedTemplateFields(
  template: MvrTemplateDto | null | undefined,
): MvrFieldDef[] {
  const fields = template?.schema?.fields ?? [];
  return fields.filter((f) => !LEGACY_STATIC_MVR_FIELD_IDS.has(f.id));
}

/**
 * Maps each legacy-static anchor field id → custom fields inserted immediately after it
 * (same algorithm as VisitReportLegacyTab).
 */
export function buildLegacyCustomFieldsByAnchor(
  template: MvrTemplateDto | null | undefined,
): Map<string, MvrFieldDef[]> {
  const map = new Map<string, MvrFieldDef[]>();
  let anchorId = "__template_start__";
  for (const field of template?.schema?.fields ?? []) {
    if (LEGACY_STATIC_MVR_FIELD_IDS.has(field.id)) {
      anchorId = field.id;
      continue;
    }
    const existing = map.get(anchorId) ?? [];
    existing.push(field);
    map.set(anchorId, existing);
  }
  return map;
}

export function legacyCustomFieldsAfter(
  byAnchor: Map<string, MvrFieldDef[]>,
  ...anchorIds: string[]
): MvrFieldDef[] {
  return anchorIds.flatMap((anchorId) => byAnchor.get(anchorId) ?? []);
}
