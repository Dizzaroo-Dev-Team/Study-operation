import type { MvrTemplateDto } from "../types/mvrTemplate";
import {
  buildLegacyCustomFieldsByAnchor,
  isLegacyStaticMvrTemplateSchema,
  legacyCustomFieldsAfter,
  legacyInsertedTemplateFields,
  shouldUseDynamicMvrShell,
} from "../legacyStaticMvrTemplateSchema";

export {
  buildLegacyCustomFieldsByAnchor,
  legacyCustomFieldsAfter,
  legacyInsertedTemplateFields,
};

const PAYLOAD_SYSTEM_KEYS = new Set([
  "reportStatus",
  "schemaVersion",
  "submissionData",
  "archivedData",
  "templateId",
  "templateVersion",
  "templateName",
  "templateSnapshot",
  "customTemplateFields",
  "rejectionReason",
  "revisionBaseline",
]);

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

const LEGACY_PAYLOAD_MARKERS = [
  "studyTitle",
  "site",
  "visitPurpose",
  "sitePersonnelRows",
  "staffRows",
  "q51",
  "q3",
  "q22",
  "summary",
  "preparedByName",
] as const;

/** CRA saved the built-in visit report (flat keys like studyTitle, q51), not submissionData-only dynamic MVR. */
export function payloadUsesLegacyLayout(payload: Record<string, unknown>): boolean {
  if (LEGACY_PAYLOAD_MARKERS.some((key) => key in payload)) {
    return true;
  }
  const flat = legacyFlatFieldValues(payload);
  return Object.keys(flat).length > 0;
}

export function legacyFlatFieldValues(payload: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (!PAYLOAD_SYSTEM_KEYS.has(key)) {
      out[key] = value;
    }
  }
  const archived = asRecord(payload.archivedData);
  for (const [key, value] of Object.entries(archived)) {
    if (!PAYLOAD_SYSTEM_KEYS.has(key) && !(key in out)) {
      out[key] = value;
    }
  }
  return out;
}

/** Use dynamic template renderer for true custom templates, even if old flat keys also exist. */
export function shouldUseDynamicReviewBody(
  template: MvrTemplateDto | null | undefined,
  payload: Record<string, unknown>,
): boolean {
  if (!template?.schema?.fields?.length) return false;
  if (isLegacyStaticMvrTemplateSchema(template.schema)) return false;
  if (!shouldUseDynamicMvrShell(template)) return false;

  const submission = asRecord(payload.submissionData);
  const custom = asRecord(payload.customTemplateFields);
  return (
    Object.keys(submission).length > 0 ||
    Object.keys(custom).length > 0 ||
    typeof payload.templateId === "string"
  );
}

/** Values keyed by template field id for the read-only dynamic review body. */
export function buildSubmissionDataForReview(
  payload: Record<string, unknown>,
  template: MvrTemplateDto | null | undefined,
): Record<string, unknown> {
  const submission = asRecord(payload.submissionData);
  const custom = asRecord(payload.customTemplateFields);
  const merged: Record<string, unknown> = { ...submission, ...custom };

  if (Object.keys(merged).length > 0 || !template?.schema?.fields?.length) {
    return merged;
  }

  const flat = legacyFlatFieldValues(payload);
  for (const field of template.schema.fields) {
    if (field.id in merged) continue;
    if (field.id in flat) {
      merged[field.id] = flat[field.id];
      continue;
    }
    const payloadKey = LEGACY_TEMPLATE_FIELD_TO_PAYLOAD_KEY[field.id];
    if (payloadKey && payloadKey in flat) {
      merged[field.id] = flat[payloadKey];
    }
  }
  return merged;
}

/** Values for revision comparison (baseline vs current). */
export function reportValuesForReview(
  payload: Record<string, unknown>,
  template: MvrTemplateDto | null | undefined,
): Record<string, unknown> {
  if (shouldUseDynamicReviewBody(template, payload)) {
    return buildSubmissionDataForReview(payload, template);
  }
  return { ...legacyFlatFieldValues(payload), ...asRecord(payload.customTemplateFields) };
}

const LEGACY_TEMPLATE_FIELD_TO_PAYLOAD_KEY: Record<string, string> = {
  legacy_s1_study_title: "studyTitle",
  legacy_s1_sponsor: "sponsor",
  legacy_s1_study_type: "studyType",
  legacy_s1_site: "site",
  legacy_s1_pi: "pi",
  legacy_s1_visit_start_date: "visitStartDate",
  legacy_s1_visit_end_date: "visitEndDate",
  legacy_s1_prev_visit_date: "prevVisitDate",
  legacy_s1_next_visit_date: "nextVisitDate",
  legacy_s1_visit_purpose: "visitPurpose",
  legacy_s1_staff: "sitePersonnelRows",
  legacy_s2_pt_screened: "ptScreened",
  legacy_s2_pt_enrolled: "ptEnrolled",
  legacy_s2_pt_active: "ptActive",
  legacy_s2_pt_dropouts: "ptDropouts",
  legacy_s2_pt_completed: "ptCompleted",
  legacy_s2_q22: "q22",
  legacy_s2_comments: "s2Comments",
  legacy_s3_q31: "q31",
  legacy_s3_q32: "q32",
  legacy_s3_q33: "q33",
  legacy_s3_q34: "q34",
  legacy_s3_q35: "q35",
  legacy_s3_comments: "s3Comments",
  legacy_s_site_q401: "q401",
  legacy_s_site_q402: "q402",
  legacy_s_site_q403: "q403",
  legacy_s_site_q404: "q404",
  legacy_s_site_q405: "q405",
  legacy_s_site_q406: "q406",
  legacy_s_site_q407: "q407",
  legacy_s_site_q408: "q408",
  legacy_s_site_q409: "q409",
  legacy_s_site_q410: "q410",
  legacy_s4_q51: "q51",
  legacy_s4_q52: "q52",
  legacy_s4_q53: "q53",
  legacy_s4_q54: "q54",
  legacy_s4_q55: "q55",
  legacy_s4_q56: "q56",
  legacy_s4_q57: "q57",
  legacy_s4_q58: "q58",
  legacy_s4_q59: "q59",
  legacy_s4_q510: "q510",
  legacy_s4_q511: "q511",
  legacy_s4_icf: "icfRows",
  legacy_s5_q61: "q61",
  legacy_s5_q62: "q62",
  legacy_s5_q63: "q63",
  legacy_s5_q64: "q64",
  legacy_s5_q65: "q65",
  legacy_s5_q66: "q66",
  legacy_s5_q67: "q67",
  legacy_s5_q68: "q68",
  legacy_s5_sdv: "sdvRows",
  legacy_s7_q81: "q81",
  legacy_s7_q82: "q82",
  legacy_s7_q83: "q83",
  legacy_s7_q84: "q84",
  legacy_s7_q85: "q85",
  legacy_s7_q86: "q86",
  legacy_s8_q91: "q91",
  legacy_s8_q92: "q92",
  legacy_s10_q111: "q111",
  legacy_s10_q112: "q112",
  legacy_s10_q113: "q113",
  legacy_s10_q114: "q114",
  legacy_s10_q115: "q115",
  legacy_s10_q116: "q116",
  legacy_s10_q117: "q117",
  legacy_s10_q118: "q118",
  legacy_s10_q119: "q119",
  legacy_s13_summary: "summary",
  legacy_s14_prepared_name: "preparedByName",
  legacy_s14_prepared_sig: "preparedBySignature",
  legacy_s14_prepared_date: "preparedByDate",
  legacy_s14_reviewed_name: "reviewedByName",
  legacy_s14_reviewed_sig: "reviewedBySignature",
  legacy_s14_reviewed_date: "reviewedByDate",
  legacy_s14_monitor: "preparedByName",
  legacy_s14_reviewer: "reviewedByName",
};
